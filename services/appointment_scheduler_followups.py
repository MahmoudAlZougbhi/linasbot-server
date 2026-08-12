"""Appointment scheduler follow-up populate jobs (LOC split)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from services.api_integrations import send_appointment_reminders
from services.appointment_scheduler_parse import parse_appointment_date
from services.smart_messaging import smart_messaging
from services.user_persistence_service import user_persistence

logger = logging.getLogger(__name__)


async def populate_missed_yesterday_messages() -> Any:
    """
    Fetch appointments from YESTERDAY with status "Available" (not attended)
    and populate smart_messaging dict with missed yesterday follow-up messages.

    Uses /appointments/reminders?status=Available&date=yesterday
    """
    from services.product_features import boc_appointment_jobs_allowed, boc_job_skipped_response

    if not boc_appointment_jobs_allowed():
        return boc_job_skipped_response(operation="populate_missed_yesterday_messages")

    try:
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        print(f"\n{'=' * 80}")
        print("🔍 MISSED YESTERDAY: Fetching appointments with status=Available")
        print(f"   API call: /appointments/reminders?status=Available&date={yesterday_str}")
        print(f"{'=' * 80}")

        # Call reminders API with status=Available for yesterday
        result = await send_appointment_reminders(date=yesterday_str, status="Available")

        all_available = []
        if result.get("success"):
            response_data = result.get("data", {})
            if isinstance(response_data, dict):
                all_available = response_data.get("appointments", [])
            elif isinstance(response_data, list):
                all_available = response_data

        if not all_available:
            print("   ℹ️ No appointments with status=Available found for yesterday")
            return {
                "success": True,
                "message": "No missed appointments found for yesterday",
                "date": yesterday_str,
                "total_missed": 0,
                "total_messages": 0,
            }

        print(f"   ✅ Found {len(all_available)} appointments with status=Available (not attended)")

        total_messages = 0
        skipped_missing_data = 0
        skipped_parse_error = 0
        skipped_past = 0
        skipped_schedule_failed = 0

        for apt in all_available:
            try:
                # API response structure from /appointments/reminders:
                # {
                #   "user_id": 123,
                #   "phone": "03567519",
                #   "name": "Customer Name",
                #   "appointment_details": {
                #     "id": 29051,
                #     "date": "27/01/2026 04:00:00 PM",
                #     "service": "Laser Hair Removal Men",
                #     "machine": "Quadro",
                #     "branch": "Antelias"
                #   }
                # }
                customer_phone = apt.get("phone")
                customer_name = apt.get("name", "عميلنا العزيز")
                apt_details = apt.get("appointment_details", {})
                apt_datetime_str = apt_details.get("date")
                service_name = apt_details.get("service", "جلسة ليزر")
                branch_name = apt_details.get("branch", "الفرع الرئيسي")

                if not customer_phone or not apt_datetime_str:
                    skipped_missing_data += 1
                    continue

                apt_datetime = parse_appointment_date(apt_datetime_str)
                if not apt_datetime:
                    skipped_parse_error += 1
                    continue

                # Missed yesterday message: scheduled 24 hours after the missed appointment
                send_time = apt_datetime + timedelta(hours=24)

                # Skip if send time is in the past
                if send_time < datetime.now():
                    skipped_past += 1
                    continue

                message_id = smart_messaging.schedule_message(
                    customer_phone,
                    "missed_yesterday",
                    send_time,
                    {
                        "customer_name": customer_name,
                        "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
                        "appointment_time": apt_datetime.strftime("%H:%M"),
                        "branch_name": branch_name,
                        "service_name": service_name,
                        "phone_number": "01234567",
                    },
                    user_persistence.get_user_language(customer_phone),
                    service_id=None,
                    service_name=service_name,
                    metadata={"source": "appointment_scheduler"},
                )

                if message_id:
                    total_messages += 1
                else:
                    skipped_schedule_failed += 1

            except Exception as e:
                logger.debug(f"⚠️ Error processing available appointment: {e}")
                continue

        total_skipped = skipped_missing_data + skipped_parse_error + skipped_past + skipped_schedule_failed

        print(f"\n{'=' * 80}")
        print("✅ MISSED YESTERDAY MESSAGES POPULATION COMPLETE")
        print(f"   📅 Date: {yesterday_str}")
        print(f"   - Appointments with status=Available: {len(all_available)}")
        print(f"   - Messages scheduled: {total_messages}")
        if total_skipped > 0:
            print("   ─────────────────────────────────")
            print(f"   📋 Skip reasons ({total_skipped} total):")
            if skipped_missing_data > 0:
                print(f"      - Missing phone/date: {skipped_missing_data}")
            if skipped_parse_error > 0:
                print(f"      - Date parse error: {skipped_parse_error}")
            if skipped_past > 0:
                print(f"      - Send time in past: {skipped_past}")
            if skipped_schedule_failed > 0:
                print(f"      - Schedule failed: {skipped_schedule_failed}")
        print(f"{'=' * 80}\n")

        return {
            "success": True,
            "message": "✅ Populated missed yesterday messages",
            "date": yesterday_str,
            "total_available": len(all_available),
            "total_messages": total_messages,
            "skipped": {
                "missing_data": skipped_missing_data,
                "parse_error": skipped_parse_error,
                "past": skipped_past,
                "schedule_failed": skipped_schedule_failed,
            },
        }

    except Exception as e:
        logger.error(f"❌ Error in missed yesterday population: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}


async def populate_one_month_followups() -> Any:
    """
    Fetch all appointments from LAST month to populate 1-month follow-up messages
    that will be sent THIS month.

    Example: In January 2026, fetch all December 2025 appointments.
    Those appointments + 30 days = January 2026 follow-ups.
    """
    from services.product_features import boc_appointment_jobs_allowed, boc_job_skipped_response

    if not boc_appointment_jobs_allowed():
        return boc_job_skipped_response(operation="populate_one_month_followups")

    try:
        import asyncio

        today = datetime.now()

        # Calculate last month's date range
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        first_of_last_month = last_of_last_month.replace(day=1)

        logger.info(
            f"🔄 Fetching appointments from {first_of_last_month.strftime('%Y-%m-%d')} to {last_of_last_month.strftime('%Y-%m-%d')} for 1-month follow-ups..."
        )

        all_appointments = []

        async def fetch_date(date: Any) -> Any:
            query_date = date.strftime("%Y-%m-%d")
            result = await send_appointment_reminders(date=query_date)

            if not result.get("success"):
                return []

            response_data = result.get("data", {})
            if isinstance(response_data, dict):
                appointments = response_data.get("appointments", [])
            elif isinstance(response_data, list):
                appointments = response_data
            else:
                appointments = []

            return appointments

        # Generate all dates in last month
        dates_to_fetch = []
        current_date = first_of_last_month
        while current_date <= last_of_last_month:
            dates_to_fetch.append(current_date)
            current_date += timedelta(days=1)

        # Fetch all dates in parallel
        results = await asyncio.gather(*[fetch_date(d) for d in dates_to_fetch], return_exceptions=True)

        for gather_result in results:
            if isinstance(gather_result, list):
                all_appointments.extend(gather_result)

        if not all_appointments:
            logger.info("ℹ️ No appointments found for 1-month follow-ups")
            return {"success": True, "message": "No appointments found", "total_appointments": 0, "total_messages": 0}

        logger.info(f"✅ Found {len(all_appointments)} appointments from last month")

        # Group by customer phone and keep only the MOST RECENT appointment per customer
        customer_latest_apt: dict[str, Any] = {}  # phone -> appointment data with parsed datetime

        for apt in all_appointments:
            try:
                customer_phone = apt.get("phone")
                apt_details = apt.get("appointment_details", {})
                apt_datetime_str = apt_details.get("date") if apt_details else None

                if not customer_phone or not apt_datetime_str:
                    continue

                apt_datetime = parse_appointment_date(apt_datetime_str)
                if not apt_datetime:
                    continue

                # Normalize phone for comparison
                phone_normalized = str(customer_phone).replace("+", "").replace(" ", "").replace("-", "")

                # Check if this is more recent than existing entry for this customer
                if (
                    phone_normalized not in customer_latest_apt
                    or apt_datetime > customer_latest_apt[phone_normalized]["datetime"]
                ):
                    customer_latest_apt[phone_normalized] = {
                        "phone": customer_phone,
                        "name": apt.get("name", "عميلنا العزيز"),
                        "datetime": apt_datetime,
                        "service_name": apt_details.get("service", "جلسة ليزر") if apt_details else "جلسة ليزر",
                        "service_id": apt_details.get("service_id") if apt_details else None,
                        "branch_name": apt_details.get("branch", "الفرع الرئيسي") if apt_details else "الفرع الرئيسي",
                    }

            except Exception as e:
                logger.debug(f"⚠️ Error parsing appointment for 1-month: {e}")
                continue

        print(f"   📊 Unique customers with appointments: {len(customer_latest_apt)}")

        total_messages = 0

        # Schedule ONE message per customer based on their most recent appointment
        for phone_normalized, apt_data in customer_latest_apt.items():
            try:
                apt_datetime = apt_data["datetime"]

                # 1-month follow-up: 30 days after most recent appointment
                followup_time = apt_datetime + timedelta(days=17)

                # Only schedule if send time is in the future (today onwards)
                if followup_time < datetime.now():
                    continue

                placeholders = {
                    "customer_name": apt_data["name"],
                    "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
                    "appointment_time": apt_datetime.strftime("%H:%M"),
                    "branch_name": apt_data["branch_name"],
                    "service_name": apt_data["service_name"],
                    "phone_number": "01234567",
                }

                message_id = smart_messaging.schedule_message(
                    apt_data["phone"],
                    "sent_17_days_after_last_session_new",
                    followup_time,
                    placeholders,
                    user_persistence.get_user_language(apt_data["phone"]),
                    service_id=apt_data["service_id"],
                    service_name=apt_data["service_name"],
                    metadata={"source": "appointment_scheduler"},
                )

                if message_id:
                    total_messages += 1
                    print(
                        f"   ✅ {apt_data['name']} - apt {apt_datetime.strftime('%m/%d')} → followup {followup_time.strftime('%m/%d')}"
                    )

            except Exception as e:
                logger.debug(f"⚠️ Error scheduling 1-month for {phone_normalized}: {e}")
                continue

        print(f"\n{'=' * 80}")
        print("✅ 1-MONTH FOLLOW-UPS POPULATION COMPLETE")
        print(f"   📊 Last month: {first_of_last_month.strftime('%B %Y')}")
        print(f"   - Total appointments found: {len(all_appointments)}")
        print(f"   - Unique customers: {len(customer_latest_apt)}")
        print(f"   - Follow-ups scheduled: {total_messages}")
        print(f"{'=' * 80}\n")

        return {
            "success": True,
            "message": "✅ Populated 1-month follow-up messages",
            "month": first_of_last_month.strftime("%B %Y"),
            "total_appointments": len(all_appointments),
            "unique_customers": len(customer_latest_apt),
            "total_messages": total_messages,
        }

    except Exception as e:
        logger.error(f"❌ Error in 1-month follow-ups population: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}
