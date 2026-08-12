"""
Appointment Scheduler Service
Integrates real appointments from backend API endpoints with Smart Messaging system
Calls send_appointment_reminders() to get appointments and populates scheduled messages
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from services.api_integrations import (
    send_appointment_reminders,
)
from services.appointment_scheduler_followups import (
    populate_missed_yesterday_messages,
    populate_one_month_followups,
)
from services.appointment_scheduler_missed import (
    populate_missed_month_messages,
    populate_no_show_messages_from_missed_appointments,
)
from services.appointment_scheduler_parse import parse_appointment_date
from services.smart_messaging import smart_messaging
from services.user_persistence_service import user_persistence

logger = logging.getLogger(__name__)


async def populate_scheduled_messages_from_appointments() -> Any:
    """
    Fetch appointments for multiple future days via send_appointment_reminders() endpoint
    and populate smart_messaging dict with scheduled messages.

    The backend's /agent/appointments/reminders endpoint returns appointments by date.
    We query today + next 7 days to get all upcoming appointments (reduced from 30 for performance).
    """
    try:
        import asyncio

        # Clear stale messages first (ensures fresh data even if midnight job didn't run)
        result = smart_messaging.clear_daily_messages()
        logger.info(f"🧹 Pre-populate cleanup: cleared {result['cleared']} stale messages, kept {result['kept']}")

        logger.info("🔄 Fetching appointments for yesterday and tomorrow via backend API...")

        all_appointments: list[Any] = []
        today = datetime.now()

        # Query appointments for YESTERDAY (-1) and TOMORROW (+1) only
        # Yesterday: for thank-you and feedback messages scheduled to be sent today
        # Tomorrow: for 24h reminders, same-day check-ins, etc.
        # Use asyncio.gather() to run API calls in PARALLEL
        async def fetch_date(days_offset: Any) -> Any:
            query_date = (today + timedelta(days=days_offset)).strftime("%Y-%m-%d")
            logger.debug(f"  Querying: {query_date}")

            result = await send_appointment_reminders(date=query_date)

            if not result.get("success"):
                logger.debug(f"  ⚠️ No data for {query_date}")
                return []

            # Extract appointments from nested response structure
            response_data = result.get("data", {})
            if isinstance(response_data, dict):
                appointments = response_data.get("appointments", [])
            elif isinstance(response_data, list):
                appointments = response_data
            else:
                appointments = []

            if appointments:
                logger.debug(f"  ✅ Found {len(appointments)} appointments for {query_date}")

            return appointments

        # Run all API calls in PARALLEL
        # Fetch yesterday (-1), today (0), and tomorrow (+1)
        # Yesterday: thank-you messages to be sent today
        # Today: feedback messages to be sent today
        # Tomorrow: 24h reminders, same-day check-ins
        results = await asyncio.gather(*[fetch_date(d) for d in [-1, 0, 1]], return_exceptions=True)

        # Flatten results
        for gather_result in results:
            if isinstance(gather_result, list):
                all_appointments.extend(gather_result)

        if not all_appointments:
            logger.info("ℹ️ No appointments found for next 7 days")
            return {
                "success": True,
                "message": "No appointments found",
                "total_appointments": 0,
                "total_messages": 0,
                "scheduled_messages_count": len(smart_messaging.scheduled_messages),
            }

        logger.info(f"✅ Found {len(all_appointments)} total appointments for next 7 days")

        total_messages = 0
        processed_count = 0
        failed_count = 0

        # DEBUG: Print first appointment to understand structure
        print(f"\n{'=' * 80}")
        print("🔍 APPOINTMENT PROCESSING DEBUG")
        print(f"   Total appointments to process: {len(all_appointments)}")
        if all_appointments:
            print("   First appointment sample:")
            print(f"   {all_appointments[0]}")
        else:
            print("   ❌ Appointments list is EMPTY!")
        print(f"{'=' * 80}\n")

        # For each appointment, populate smart_messaging
        for idx, apt in enumerate(all_appointments):
            try:
                # Extract appointment details from backend response
                customer_phone = apt.get("phone")
                customer_name = apt.get("name", "عميلنا العزيز")
                apt_details = apt.get("appointment_details", {})
                apt_datetime_str = apt_details.get("date") if apt_details else None
                service_name = apt_details.get("service", "جلسة ليزر") if apt_details else "جلسة ليزر"
                service_id = apt_details.get("service_id") if apt_details else None
                branch_name = apt_details.get("branch", "الفرع الرئيسي") if apt_details else "الفرع الرئيسي"
                appointment_id = (
                    apt.get("appointment_id")
                    or apt.get("id")
                    or (apt_details.get("appointment_id") if apt_details else None)
                    or (apt_details.get("id") if apt_details else None)
                )

                if not customer_phone or not apt_datetime_str:
                    if idx < 3:  # Log first 3 failures for debugging
                        print(
                            f"⚠️ Appointment {idx} missing data: phone=***{str(customer_phone)[-4:] if customer_phone else ''}, date={apt_datetime_str}"
                        )
                    failed_count += 1
                    continue

                # DEBUG: Print first 3 successful extractions
                if idx < 3:
                    print(
                        f"✅ Apt {idx}: phone=***{str(customer_phone)[-4:] if customer_phone else ''}, date={apt_datetime_str}"
                    )

                # Parse appointment datetime
                apt_datetime = parse_appointment_date(apt_datetime_str)
                if not apt_datetime:
                    if idx < 3:
                        print(f"❌ Apt {idx}: Could not parse date: {apt_datetime_str}")
                    failed_count += 1
                    continue

                # Allow past appointments (for thank-you/feedback messages)
                # Each message type has its own future check in schedule_appointment_reminders

                # DEBUG: Print first 3 that pass all checks
                if idx < 3:
                    print(f"🎉 Apt {idx}: PASSED ALL CHECKS, calling schedule_appointment_reminders")

                # Prepare customer data for smart_messaging
                customer_data = {
                    "phone": customer_phone,
                    "name": customer_name,
                    "language": user_persistence.get_user_language(customer_phone),
                    "service": service_name,
                    "service_id": service_id,
                    "branch": branch_name,
                    "appointment_id": appointment_id,
                }

                # Call schedule_appointment_reminders - populates scheduled_messages dict
                messages_count = smart_messaging.schedule_appointment_reminders(apt_datetime, customer_data)
                total_messages += messages_count
                processed_count += 1

            except Exception as e:
                print(f"❌ EXCEPTION processing appointment {idx}: {e}")
                import traceback

                traceback.print_exc()
                failed_count += 1
                continue

        logger.info(f"✅ Processed {processed_count} appointments, generated {total_messages} messages")

        # PHASE 2 (Thank-you) removed completely; no scheduling or sending.

        # ============================================================
        # PHASE 3: Fetch "Done" appointments from TODAY for feedback
        # Feedback is sent 2 hours after appointment time
        # ============================================================
        today_str = today.strftime("%Y-%m-%d")

        print(f"\n{'=' * 80}")
        print("🔍 PHASE 3: FETCHING 'DONE' APPOINTMENTS FROM TODAY FOR FEEDBACK")
        print(f"   API call: /appointments/reminders?status=Done&date={today_str}")
        print(f"{'=' * 80}")

        feedback_appointments_found = 0
        feedback_messages_scheduled = 0

        # Fetch Done appointments from today
        feedback_result = await send_appointment_reminders(date=today_str, status="Done")

        if feedback_result.get("success"):
            response_data = feedback_result.get("data", {})
            if isinstance(response_data, dict):
                feedback_appointments = response_data.get("appointments", [])
            elif isinstance(response_data, list):
                feedback_appointments = response_data
            else:
                feedback_appointments = []

            feedback_appointments_found = len(feedback_appointments)
            print(f"   ✅ Found {feedback_appointments_found} completed appointments today")

            for apt in feedback_appointments:
                try:
                    customer_phone = apt.get("phone")
                    customer_name = apt.get("name", "عميلنا العزيز")
                    apt_details = apt.get("appointment_details", {})
                    apt_datetime_str = apt_details.get("date")
                    service_name = apt_details.get("service", "جلسة ليزر")
                    branch_name = apt_details.get("branch", "الفرع الرئيسي")

                    if not customer_phone or not apt_datetime_str:
                        continue

                    # Parse appointment datetime
                    apt_datetime = parse_appointment_date(apt_datetime_str)
                    if not apt_datetime:
                        continue

                    # Schedule feedback for 2 hours after appointment, or now if past
                    feedback_time = apt_datetime + timedelta(hours=2)
                    if feedback_time < today:
                        feedback_time = today  # Send now if 2hr window passed

                    placeholders = {
                        "customer_name": customer_name,
                        "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
                        "appointment_time": apt_datetime.strftime("%H:%M"),
                        "branch_name": branch_name,
                        "service_name": service_name,
                        "phone_number": "01234567",
                    }

                    schedule_id = smart_messaging.schedule_message(
                        customer_phone,
                        "thank_you_message_sent_after_session",
                        feedback_time,
                        placeholders,
                        user_persistence.get_user_language(customer_phone),
                        service_id=None,
                        service_name=service_name,
                        metadata={"source": "appointment_scheduler"},
                    )

                    if schedule_id:
                        feedback_messages_scheduled += 1
                        print(
                            f"   ✅ {customer_name} ({customer_phone}) - apt {apt_datetime.strftime('%H:%M')} - feedback at {feedback_time.strftime('%H:%M')}"
                        )

                except Exception as e:
                    logger.debug(f"Error processing feedback appointment: {e}")
                    continue
        else:
            print(
                f"   ❌ Failed to fetch Done appointments for today: {feedback_result.get('message', 'Unknown error')}"
            )

        print("\n   📊 Phase 3 Results:")
        print(f"   - Done appointments today: {feedback_appointments_found}")
        print(f"   - Feedback messages scheduled: {feedback_messages_scheduled}")
        print(f"{'=' * 80}")

        total_messages += feedback_messages_scheduled

        # Ensure this output is always visible
        print(f"\n{'=' * 80}")
        print("✅ APPOINTMENT POPULATION COMPLETE")
        print("   📊 Statistics:")
        print(f"   - Appointments found: {len(all_appointments)}")
        print(f"   - Processed: {processed_count}")
        print(f"   - Failed: {failed_count}")
        print(f"   - Messages scheduled: {total_messages}")
        print(f"   - Total in dict: {len(smart_messaging.scheduled_messages)}")
        print(f"{'=' * 80}\n")

        return {
            "success": True,
            "message": "✅ Populated scheduled messages from real appointments",
            "total_appointments": len(all_appointments),
            "processed_appointments": processed_count,
            "failed_appointments": failed_count,
            "total_messages": total_messages,
            "scheduled_messages_count": len(smart_messaging.scheduled_messages),
        }

    except Exception as e:
        logger.error(f"❌ Error in appointment population: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}


__all__ = [
    "parse_appointment_date",
    "populate_scheduled_messages_from_appointments",
    "populate_no_show_messages_from_missed_appointments",
    "populate_missed_yesterday_messages",
    "populate_one_month_followups",
    "populate_missed_month_messages",
]
