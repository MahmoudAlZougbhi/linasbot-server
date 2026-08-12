"""Appointment scheduler missed-month populate jobs (LOC split)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from services.api_integrations import (
    get_paused_appointments_between_dates,
    send_appointment_reminders,
)
from services.appointment_scheduler_parse import parse_appointment_date
from services.smart_messaging import smart_messaging
from services.user_persistence_service import user_persistence

logger = logging.getLogger(__name__)


async def populate_no_show_messages_from_missed_appointments() -> Any:
    """Removed: no_show_followup template is no longer used."""
    return {
        "success": True,
        "message": "no_show_followup removed from product",
        "total_messages": 0,
        "no_show_messages_count": 0,
    }


async def populate_missed_month_messages() -> Any:
    """
    Fetch all paused appointments for the current month using the
    appointments/paused/between-dates endpoint.

    Date range is dynamic based on current month:
    - start_date: First day of current month (e.g., 2026-01-01)
    - end_date: First day of next month (e.g., 2026-02-01)
    """
    from services.product_features import boc_appointment_jobs_allowed, boc_job_skipped_response

    if not boc_appointment_jobs_allowed():
        return boc_job_skipped_response(operation="populate_missed_month_messages")

    try:
        import calendar

        today = datetime.now()

        # Calculate dynamic date range for current month
        first_of_month = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        last_of_month = today.replace(day=last_day)

        start_date = first_of_month.strftime("%Y-%m-%d")
        end_date = last_of_month.strftime("%Y-%m-%d")

        logger.info(f"🔄 Fetching paused appointments from {start_date} to {end_date} for missed-month messages...")

        # Single API call to get all paused appointments for the month
        result = await get_paused_appointments_between_dates(
            start_date=start_date,
            end_date=end_date,
            service_id=None,  # Get all services
        )

        all_missed = []
        if result.get("success"):
            response_data = result.get("data", {})
            if isinstance(response_data, dict):
                all_missed = response_data.get("appointments", [])
            elif isinstance(response_data, list):
                all_missed = response_data

        if not all_missed:
            logger.info("ℹ️ No missed appointments found for this month")
            return {
                "success": True,
                "message": "No missed appointments found",
                "month": first_of_month.strftime("%B %Y"),
                "total_missed": 0,
                "total_messages": 0,
            }

        logger.info(f"✅ Found {len(all_missed)} missed appointments this month")

        # ============================================================
        # Fetch all DONE appointments for the same month
        # We need the DATE of each Done appointment to compare with missed dates
        # Only skip if Done is AFTER the missed appointment
        # ============================================================
        customer_done_dates: dict[str, Any] = {}  # phone -> list of done appointment datetimes

        print("\n   🔍 Fetching Done appointments to check against missed dates...")

        # Fetch Done appointments for each day of the month (up to today)
        async def fetch_done_for_date(date: Any) -> Any:
            query_date = date.strftime("%Y-%m-%d")
            done_result = await send_appointment_reminders(date=query_date, status="Done")
            if done_result.get("success"):
                data = done_result.get("data", {})
                return data.get("appointments", []) if isinstance(data, dict) else data
            return []

        import asyncio

        dates_to_check = []
        current_date = first_of_month
        while current_date <= min(last_of_month, today):
            dates_to_check.append(current_date)
            current_date += timedelta(days=1)

        done_results = await asyncio.gather(*[fetch_done_for_date(d) for d in dates_to_check], return_exceptions=True)

        for done_list in done_results:
            if isinstance(done_list, list):
                for done_apt in done_list:
                    phone = done_apt.get("phone")
                    apt_details = done_apt.get("appointment_details", {})
                    done_date_str = apt_details.get("date") if apt_details else None

                    if phone and done_date_str:
                        # Normalize phone for comparison
                        phone_normalized = str(phone).replace("+", "").replace(" ", "").replace("-", "")
                        if phone_normalized.startswith("961"):
                            phone_normalized = phone_normalized[3:]

                        # Parse the done appointment date
                        done_datetime = parse_appointment_date(done_date_str)
                        if done_datetime:
                            if phone_normalized not in customer_done_dates:
                                customer_done_dates[phone_normalized] = []
                            customer_done_dates[phone_normalized].append(done_datetime)

        print(f"   ✅ Found {len(customer_done_dates)} customers with completed appointments this month")

        total_messages = 0
        customers_already_scheduled = set()  # Track to avoid duplicate messages per customer

        # Track skip reasons
        skipped_missing_data = 0
        skipped_duplicate = 0
        skipped_parse_error = 0
        skipped_has_done = 0
        skipped_past = 0
        skipped_schedule_failed = 0

        for apt in all_missed:
            try:
                # New API response structure from appointments/paused/between-dates:
                # {
                #   "appointment_id": 11425,
                #   "date": "02/01/2026 10:00:00 AM",
                #   "customer": { "id": 10497, "name": "Maya homsi", "phone": "03920591", "user_code": "LMH10497" },
                #   "service": "Laser Hair Removal Women",
                #   "machine": "Quadro",
                #   "branch": "Beirut"
                # }
                customer_data = apt.get("customer", {})
                customer_phone = customer_data.get("phone")
                customer_name = customer_data.get("name", "عميلنا العزيز")
                apt_datetime_str = apt.get("date")
                service_name = apt.get("service", "جلسة ليزر")
                branch_name = apt.get("branch", "الفرع الرئيسي")

                if not customer_phone or not apt_datetime_str:
                    skipped_missing_data += 1
                    continue

                # Normalize phone for comparison
                phone_normalized = str(customer_phone).replace("+", "").replace(" ", "").replace("-", "")
                if phone_normalized.startswith("961"):
                    phone_normalized = phone_normalized[3:]

                # Skip if we already scheduled a message for this customer (avoid duplicates)
                if phone_normalized in customers_already_scheduled:
                    skipped_duplicate += 1
                    continue

                apt_datetime = parse_appointment_date(apt_datetime_str)
                if not apt_datetime:
                    skipped_parse_error += 1
                    continue

                # Skip if customer has a completed appointment AFTER this missed appointment
                # e.g., Missed Jan 7, Done Jan 12 → Skip (customer came back)
                # e.g., Done Jan 1, Missed Jan 7 → Don't skip (missed after attending)
                if phone_normalized in customer_done_dates:
                    done_dates = customer_done_dates[phone_normalized]
                    has_done_after_missed = any(done_dt > apt_datetime for done_dt in done_dates)
                    if has_done_after_missed:
                        skipped_has_done += 1
                        continue

                # Missed-month message: scheduled for end of month at 9 PM
                # Use the last day of the month the appointment was in
                apt_month_last_day = calendar.monthrange(apt_datetime.year, apt_datetime.month)[1]
                send_time = apt_datetime.replace(day=apt_month_last_day, hour=21, minute=0, second=0, microsecond=0)

                # Skip if send time is in the past (month already ended)
                if send_time < datetime.now():
                    skipped_past += 1
                    continue

                placeholders = {
                    "customer_name": customer_name,
                    "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
                    "appointment_time": apt_datetime.strftime("%H:%M"),
                    "branch_name": branch_name,
                    "service_name": service_name,
                    "phone_number": "01234567",
                }

                message_id = smart_messaging.schedule_message(
                    customer_phone,
                    "sent_for_pause",
                    send_time,
                    placeholders,
                    user_persistence.get_user_language(customer_phone),
                    service_id=None,
                    service_name=service_name,
                    metadata={"source": "appointment_scheduler"},
                )

                if message_id:
                    total_messages += 1
                    customers_already_scheduled.add(phone_normalized)
                else:
                    skipped_schedule_failed += 1

            except Exception as e:
                logger.debug(f"⚠️ Error processing missed appointment: {e}")
                continue

        total_skipped = (
            skipped_missing_data
            + skipped_duplicate
            + skipped_parse_error
            + skipped_has_done
            + skipped_past
            + skipped_schedule_failed
        )

        print(f"\n{'=' * 80}")
        print("✅ MISSED-MONTH MESSAGES POPULATION COMPLETE")
        print(f"   📊 Month: {first_of_month.strftime('%B %Y')}")
        print(f"   📅 Date range: {start_date} to {end_date}")
        print(f"   - Paused appointments found: {len(all_missed)}")
        print(f"   - Messages scheduled: {total_messages}")
        print("   ─────────────────────────────────")
        print(f"   📋 Skip reasons ({total_skipped} total):")
        if skipped_duplicate > 0:
            print(f"      - Duplicate (same customer): {skipped_duplicate}")
        if skipped_has_done > 0:
            print(f"      - Has Done after missed: {skipped_has_done}")
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
            "message": "✅ Populated missed-month messages",
            "month": first_of_month.strftime("%B %Y"),
            "start_date": start_date,
            "end_date": end_date,
            "total_missed": len(all_missed),
            "total_messages": total_messages,
            "skipped": {
                "duplicate": skipped_duplicate,
                "has_done_after": skipped_has_done,
                "missing_data": skipped_missing_data,
                "parse_error": skipped_parse_error,
                "past": skipped_past,
                "schedule_failed": skipped_schedule_failed,
            },
        }

    except Exception as e:
        logger.error(f"❌ Error in missed-month population: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}
