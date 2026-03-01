# -*- coding: utf-8 -*-
"""
Appointment Scheduler Service
Integrates real appointments from backend API endpoints with Smart Messaging system
Calls send_appointment_reminders() to get appointments and populates scheduled messages
"""

from datetime import datetime, timedelta
from services.api_integrations import send_appointment_reminders, get_paused_appointments_between_dates, get_missed_appointments
from services.smart_messaging import smart_messaging
from services.user_persistence_service import user_persistence
import logging

logger = logging.getLogger(__name__)


def parse_appointment_date(date_str):
    """
    Parse appointment date from backend format
    Backend returns: "27/10/2025 05:00:00 PM"  (DD/MM/YYYY HH:MM:SS AM/PM)
    """
    if not date_str:
        return None
    
    try:
        # Format from backend: "27/10/2025 05:00:00 PM"
        return datetime.strptime(date_str, '%d/%m/%Y %I:%M:%S %p')
    except ValueError:
        # Try other formats
        for fmt in ['%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y']:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None


async def populate_scheduled_messages_from_appointments():
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

        all_appointments = []
        today = datetime.now()

        # Query appointments for YESTERDAY (-1) and TOMORROW (+1) only
        # Yesterday: for thank-you and feedback messages scheduled to be sent today
        # Tomorrow: for 24h reminders, same-day check-ins, etc.
        # Use asyncio.gather() to run API calls in PARALLEL
        async def fetch_date(days_offset):
            query_date = (today + timedelta(days=days_offset)).strftime('%Y-%m-%d')
            logger.debug(f"  Querying: {query_date}")

            result = await send_appointment_reminders(date=query_date)

            if not result.get('success'):
                logger.debug(f"  ⚠️ No data for {query_date}")
                return []

            # Extract appointments from nested response structure
            response_data = result.get('data', {})
            if isinstance(response_data, dict):
                appointments = response_data.get('appointments', [])
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
        for result in results:
            if isinstance(result, list):
                all_appointments.extend(result)
        
        if not all_appointments:
            logger.info("ℹ️ No appointments found for next 7 days")
            return {
                "success": True,
                "message": "No appointments found",
                "total_appointments": 0,
                "total_messages": 0,
                "scheduled_messages_count": len(smart_messaging.scheduled_messages)
            }

        logger.info(f"✅ Found {len(all_appointments)} total appointments for next 7 days")

        total_messages = 0
        processed_count = 0
        failed_count = 0

        # DEBUG: Print first appointment to understand structure
        print(f"\n{'='*80}")
        print(f"🔍 APPOINTMENT PROCESSING DEBUG")
        print(f"   Total appointments to process: {len(all_appointments)}")
        if all_appointments:
            print(f"   First appointment sample:")
            print(f"   {all_appointments[0]}")
        else:
            print(f"   ❌ Appointments list is EMPTY!")
        print(f"{'='*80}\n")

        # For each appointment, populate smart_messaging
        for idx, apt in enumerate(all_appointments):
            try:

                # Extract appointment details from backend response
                customer_phone = apt.get('phone')
                customer_name = apt.get('name', 'عميلنا العزيز')
                apt_details = apt.get('appointment_details', {})
                apt_datetime_str = apt_details.get('date') if apt_details else None
                service_name = apt_details.get('service', 'جلسة ليزر') if apt_details else 'جلسة ليزر'
                service_id = apt_details.get('service_id') if apt_details else None
                branch_name = apt_details.get('branch', 'الفرع الرئيسي') if apt_details else 'الفرع الرئيسي'

                if not customer_phone or not apt_datetime_str:
                    if idx < 3:  # Log first 3 failures for debugging
                        print(f"⚠️ Appointment {idx} missing data: phone={customer_phone}, date={apt_datetime_str}")
                    failed_count += 1
                    continue

                # DEBUG: Print first 3 successful extractions
                if idx < 3:
                    print(f"✅ Apt {idx}: phone={customer_phone}, date={apt_datetime_str}")
                
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
                    'phone': customer_phone,
                    'name': customer_name,
                    'language': user_persistence.get_user_language(customer_phone),
                    'service': service_name,
                    'service_id': service_id,
                    'branch': branch_name
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
        today_str = today.strftime('%Y-%m-%d')

        print(f"\n{'='*80}")
        print(f"🔍 PHASE 3: FETCHING 'DONE' APPOINTMENTS FROM TODAY FOR FEEDBACK")
        print(f"   API call: /appointments/reminders?status=Done&date={today_str}")
        print(f"{'='*80}")

        feedback_appointments_found = 0
        feedback_messages_scheduled = 0

        # Fetch Done appointments from today
        feedback_result = await send_appointment_reminders(date=today_str, status='Done')

        if feedback_result.get('success'):
            response_data = feedback_result.get('data', {})
            if isinstance(response_data, dict):
                feedback_appointments = response_data.get('appointments', [])
            elif isinstance(response_data, list):
                feedback_appointments = response_data
            else:
                feedback_appointments = []

            feedback_appointments_found = len(feedback_appointments)
            print(f"   ✅ Found {feedback_appointments_found} completed appointments today")

            for apt in feedback_appointments:
                try:
                    customer_phone = apt.get('phone')
                    customer_name = apt.get('name', 'عميلنا العزيز')
                    apt_details = apt.get('appointment_details', {})
                    apt_datetime_str = apt_details.get('date')
                    service_name = apt_details.get('service', 'جلسة ليزر')
                    branch_name = apt_details.get('branch', 'الفرع الرئيسي')

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
                        "phone_number": "01234567"
                    }

                    result = smart_messaging.schedule_message(
                        customer_phone,
                        "post_session_feedback",
                        feedback_time,
                        placeholders,
                        user_persistence.get_user_language(customer_phone),
                        service_id=None,
                        service_name=service_name
                    )

                    if result:
                        feedback_messages_scheduled += 1
                        print(f"   ✅ {customer_name} ({customer_phone}) - apt {apt_datetime.strftime('%H:%M')} - feedback at {feedback_time.strftime('%H:%M')}")

                except Exception as e:
                    logger.debug(f"Error processing feedback appointment: {e}")
                    continue
        else:
            print(f"   ❌ Failed to fetch Done appointments for today: {feedback_result.get('message', 'Unknown error')}")

        print(f"\n   📊 Phase 3 Results:")
        print(f"   - Done appointments today: {feedback_appointments_found}")
        print(f"   - Feedback messages scheduled: {feedback_messages_scheduled}")
        print(f"{'='*80}")

        total_messages += feedback_messages_scheduled

        # Ensure this output is always visible
        print(f"\n{'='*80}")
        print(f"✅ APPOINTMENT POPULATION COMPLETE")
        print(f"   📊 Statistics:")
        print(f"   - Appointments found: {len(all_appointments)}")
        print(f"   - Processed: {processed_count}")
        print(f"   - Failed: {failed_count}")
        print(f"   - Messages scheduled: {total_messages}")
        print(f"   - Total in dict: {len(smart_messaging.scheduled_messages)}")
        print(f"{'='*80}\n")

        return {
            "success": True,
            "message": f"✅ Populated scheduled messages from real appointments",
            "total_appointments": len(all_appointments),
            "processed_appointments": processed_count,
            "failed_appointments": failed_count,
            "total_messages": total_messages,
            "scheduled_messages_count": len(smart_messaging.scheduled_messages)
        }
        
    except Exception as e:
        logger.error(f"❌ Error in appointment population: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


async def populate_no_show_messages_from_missed_appointments():
    """
    Fetch appointments from TODAY with status "Available" (not attended)
    and populate smart_messaging dict with no-show follow-up messages.

    Uses /appointments/reminders?status=Available&date=today
    Schedules messages for exactly 2 hours after appointment time.
    Skips if 2-hour window has passed (those get caught by missed-yesterday next day).
    """
    try:
        today = datetime.now()
        today_str = today.strftime('%Y-%m-%d')

        print(f"\n{'='*80}")
        print(f"🔍 NO-SHOW: Fetching appointments with status=Available")
        print(f"   API call: /appointments/reminders?status=Available&date={today_str}")
        print(f"{'='*80}")

        # Call reminders API with status=Available for today
        result = await send_appointment_reminders(date=today_str, status='Available')

        all_available = []
        if result.get('success'):
            response_data = result.get('data', {})
            if isinstance(response_data, dict):
                all_available = response_data.get('appointments', [])
            elif isinstance(response_data, list):
                all_available = response_data

        if not all_available:
            print(f"   ℹ️ No appointments with status=Available found for today")
            return {
                "success": True,
                "message": "No missed appointments found for today",
                "date": today_str,
                "total_missed": 0,
                "total_messages": 0,
                "no_show_messages_count": 0
            }

        print(f"   ✅ Found {len(all_available)} appointments with status=Available")

        now = datetime.now()
        total_messages = 0

        # Track skip reasons
        skipped_missing_data = 0
        skipped_parse_error = 0
        skipped_future = 0
        skipped_grace_period = 0
        skipped_window_passed = 0
        skipped_schedule_failed = 0

        for apt in all_available:
            try:
                # API response structure from /appointments/reminders:
                customer_phone = apt.get('phone')
                customer_name = apt.get('name', 'عميلنا العزيز')
                apt_details = apt.get('appointment_details', {})
                apt_datetime_str = apt_details.get('date')
                service_name = apt_details.get('service', 'جلسة ليزر')
                branch_name = apt_details.get('branch', 'الفرع الرئيسي')

                if not customer_phone or not apt_datetime_str:
                    skipped_missing_data += 1
                    continue

                apt_datetime = parse_appointment_date(apt_datetime_str)
                if not apt_datetime:
                    skipped_parse_error += 1
                    continue

                grace_period_end = apt_datetime + timedelta(hours=1)  # 1hr grace period
                no_show_time = apt_datetime + timedelta(hours=2)  # Send 2hrs after appointment

                # Skip future appointments (haven't happened yet)
                if apt_datetime > now:
                    skipped_future += 1
                    continue

                # Skip if 1-hour grace period hasn't passed (not confirmed no-show)
                if grace_period_end > now:
                    skipped_grace_period += 1
                    continue

                # Schedule for 2 hours after appointment, or now if that time passed
                send_at = no_show_time if no_show_time > now else now

                message_id = smart_messaging.schedule_message(
                    customer_phone,
                    "no_show_followup",
                    send_at,
                    {
                        "customer_name": customer_name,
                        "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
                        "appointment_time": apt_datetime.strftime("%H:%M"),
                        "branch_name": branch_name,
                        "service_name": service_name,
                        "phone_number": "01234567"
                    },
                    user_persistence.get_user_language(customer_phone),
                    service_id=None,
                    service_name=service_name
                )

                if message_id:
                    total_messages += 1
                else:
                    skipped_schedule_failed += 1

            except Exception as e:
                logger.debug(f"⚠️ Error processing available appointment: {e}")
                continue

        total_skipped = skipped_missing_data + skipped_parse_error + skipped_future + skipped_grace_period + skipped_window_passed + skipped_schedule_failed

        print(f"\n{'='*80}")
        print(f"✅ NO-SHOW MESSAGES POPULATION COMPLETE")
        print(f"   📅 Date: {today_str} (current time: {now.strftime('%H:%M')})")
        print(f"   - Appointments with status=Available: {len(all_available)}")
        print(f"   - Messages scheduled: {total_messages}")
        if total_skipped > 0:
            print(f"   ─────────────────────────────────")
            print(f"   📋 Skip reasons ({total_skipped} total):")
            if skipped_future > 0:
                print(f"      - Future appointment: {skipped_future}")
            if skipped_grace_period > 0:
                print(f"      - Grace period not over: {skipped_grace_period}")
            if skipped_window_passed > 0:
                print(f"      - 2hr window passed: {skipped_window_passed}")
            if skipped_missing_data > 0:
                print(f"      - Missing phone/date: {skipped_missing_data}")
            if skipped_parse_error > 0:
                print(f"      - Date parse error: {skipped_parse_error}")
            if skipped_schedule_failed > 0:
                print(f"      - Schedule failed: {skipped_schedule_failed}")
        print(f"{'='*80}\n")

        return {
            "success": True,
            "message": f"✅ Populated no-show follow-up messages",
            "date": today_str,
            "total_available": len(all_available),
            "total_messages": total_messages,
            "skipped": {
                "future": skipped_future,
                "grace_period": skipped_grace_period,
                "window_passed": skipped_window_passed,
                "missing_data": skipped_missing_data,
                "parse_error": skipped_parse_error,
                "schedule_failed": skipped_schedule_failed
            }
        }

    except Exception as e:
        logger.error(f"❌ Error in no-show population: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


async def populate_missed_yesterday_messages():
    """
    Fetch appointments from YESTERDAY with status "Available" (not attended)
    and populate smart_messaging dict with missed yesterday follow-up messages.

    Uses /appointments/reminders?status=Available&date=yesterday
    """
    try:
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y-%m-%d')

        print(f"\n{'='*80}")
        print(f"🔍 MISSED YESTERDAY: Fetching appointments with status=Available")
        print(f"   API call: /appointments/reminders?status=Available&date={yesterday_str}")
        print(f"{'='*80}")

        # Call reminders API with status=Available for yesterday
        result = await send_appointment_reminders(date=yesterday_str, status='Available')

        all_available = []
        if result.get('success'):
            response_data = result.get('data', {})
            if isinstance(response_data, dict):
                all_available = response_data.get('appointments', [])
            elif isinstance(response_data, list):
                all_available = response_data

        if not all_available:
            print(f"   ℹ️ No appointments with status=Available found for yesterday")
            return {
                "success": True,
                "message": "No missed appointments found for yesterday",
                "date": yesterday_str,
                "total_missed": 0,
                "total_messages": 0
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
                customer_phone = apt.get('phone')
                customer_name = apt.get('name', 'عميلنا العزيز')
                apt_details = apt.get('appointment_details', {})
                apt_datetime_str = apt_details.get('date')
                service_name = apt_details.get('service', 'جلسة ليزر')
                branch_name = apt_details.get('branch', 'الفرع الرئيسي')

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
                        "phone_number": "01234567"
                    },
                    user_persistence.get_user_language(customer_phone),
                    service_id=None,
                    service_name=service_name
                )

                if message_id:
                    total_messages += 1
                else:
                    skipped_schedule_failed += 1

            except Exception as e:
                logger.debug(f"⚠️ Error processing available appointment: {e}")
                continue

        total_skipped = skipped_missing_data + skipped_parse_error + skipped_past + skipped_schedule_failed

        print(f"\n{'='*80}")
        print(f"✅ MISSED YESTERDAY MESSAGES POPULATION COMPLETE")
        print(f"   📅 Date: {yesterday_str}")
        print(f"   - Appointments with status=Available: {len(all_available)}")
        print(f"   - Messages scheduled: {total_messages}")
        if total_skipped > 0:
            print(f"   ─────────────────────────────────")
            print(f"   📋 Skip reasons ({total_skipped} total):")
            if skipped_missing_data > 0:
                print(f"      - Missing phone/date: {skipped_missing_data}")
            if skipped_parse_error > 0:
                print(f"      - Date parse error: {skipped_parse_error}")
            if skipped_past > 0:
                print(f"      - Send time in past: {skipped_past}")
            if skipped_schedule_failed > 0:
                print(f"      - Schedule failed: {skipped_schedule_failed}")
        print(f"{'='*80}\n")

        return {
            "success": True,
            "message": f"✅ Populated missed yesterday messages",
            "date": yesterday_str,
            "total_available": len(all_available),
            "total_messages": total_messages,
            "skipped": {
                "missing_data": skipped_missing_data,
                "parse_error": skipped_parse_error,
                "past": skipped_past,
                "schedule_failed": skipped_schedule_failed
            }
        }

    except Exception as e:
        logger.error(f"❌ Error in missed yesterday population: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


async def populate_one_month_followups():
    """
    Fetch all appointments from LAST month to populate 1-month follow-up messages
    that will be sent THIS month.

    Example: In January 2026, fetch all December 2025 appointments.
    Those appointments + 30 days = January 2026 follow-ups.
    """
    try:
        import asyncio

        today = datetime.now()

        # Calculate last month's date range
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        first_of_last_month = last_of_last_month.replace(day=1)

        logger.info(f"🔄 Fetching appointments from {first_of_last_month.strftime('%Y-%m-%d')} to {last_of_last_month.strftime('%Y-%m-%d')} for 1-month follow-ups...")

        all_appointments = []

        async def fetch_date(date):
            query_date = date.strftime('%Y-%m-%d')
            result = await send_appointment_reminders(date=query_date)

            if not result.get('success'):
                return []

            response_data = result.get('data', {})
            if isinstance(response_data, dict):
                appointments = response_data.get('appointments', [])
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

        for result in results:
            if isinstance(result, list):
                all_appointments.extend(result)

        if not all_appointments:
            logger.info("ℹ️ No appointments found for 1-month follow-ups")
            return {
                "success": True,
                "message": "No appointments found",
                "total_appointments": 0,
                "total_messages": 0
            }

        logger.info(f"✅ Found {len(all_appointments)} appointments from last month")

        # Group by customer phone and keep only the MOST RECENT appointment per customer
        customer_latest_apt = {}  # phone -> appointment data with parsed datetime

        for apt in all_appointments:
            try:
                customer_phone = apt.get('phone')
                apt_details = apt.get('appointment_details', {})
                apt_datetime_str = apt_details.get('date') if apt_details else None

                if not customer_phone or not apt_datetime_str:
                    continue

                apt_datetime = parse_appointment_date(apt_datetime_str)
                if not apt_datetime:
                    continue

                # Normalize phone for comparison
                phone_normalized = str(customer_phone).replace("+", "").replace(" ", "").replace("-", "")

                # Check if this is more recent than existing entry for this customer
                if phone_normalized not in customer_latest_apt or apt_datetime > customer_latest_apt[phone_normalized]['datetime']:
                    customer_latest_apt[phone_normalized] = {
                        'phone': customer_phone,
                        'name': apt.get('name', 'عميلنا العزيز'),
                        'datetime': apt_datetime,
                        'service_name': apt_details.get('service', 'جلسة ليزر') if apt_details else 'جلسة ليزر',
                        'service_id': apt_details.get('service_id') if apt_details else None,
                        'branch_name': apt_details.get('branch', 'الفرع الرئيسي') if apt_details else 'الفرع الرئيسي'
                    }

            except Exception as e:
                logger.debug(f"⚠️ Error parsing appointment for 1-month: {e}")
                continue

        print(f"   📊 Unique customers with appointments: {len(customer_latest_apt)}")

        total_messages = 0

        # Schedule ONE message per customer based on their most recent appointment
        for phone_normalized, apt_data in customer_latest_apt.items():
            try:
                apt_datetime = apt_data['datetime']

                # 1-month follow-up: 30 days after most recent appointment
                followup_time = apt_datetime + timedelta(days=17)

                # Only schedule if send time is in the future (today onwards)
                if followup_time < datetime.now():
                    continue

                placeholders = {
                    "customer_name": apt_data['name'],
                    "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
                    "appointment_time": apt_datetime.strftime("%H:%M"),
                    "branch_name": apt_data['branch_name'],
                    "service_name": apt_data['service_name'],
                    "phone_number": "01234567"
                }

                message_id = smart_messaging.schedule_message(
                    apt_data['phone'],
                    "one_month_followup",
                    followup_time,
                    placeholders,
                    user_persistence.get_user_language(apt_data['phone']),
                    service_id=apt_data['service_id'],
                    service_name=apt_data['service_name']
                )

                if message_id:
                    total_messages += 1
                    print(f"   ✅ {apt_data['name']} - apt {apt_datetime.strftime('%m/%d')} → followup {followup_time.strftime('%m/%d')}")

            except Exception as e:
                logger.debug(f"⚠️ Error scheduling 1-month for {phone_normalized}: {e}")
                continue

        print(f"\n{'='*80}")
        print(f"✅ 1-MONTH FOLLOW-UPS POPULATION COMPLETE")
        print(f"   📊 Last month: {first_of_last_month.strftime('%B %Y')}")
        print(f"   - Total appointments found: {len(all_appointments)}")
        print(f"   - Unique customers: {len(customer_latest_apt)}")
        print(f"   - Follow-ups scheduled: {total_messages}")
        print(f"{'='*80}\n")

        return {
            "success": True,
            "message": f"✅ Populated 1-month follow-up messages",
            "month": first_of_last_month.strftime('%B %Y'),
            "total_appointments": len(all_appointments),
            "unique_customers": len(customer_latest_apt),
            "total_messages": total_messages
        }

    except Exception as e:
        logger.error(f"❌ Error in 1-month follow-ups population: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


async def populate_missed_month_messages():
    """
    Fetch all paused appointments for the current month using the
    appointments/paused/between-dates endpoint.

    Date range is dynamic based on current month:
    - start_date: First day of current month (e.g., 2026-01-01)
    - end_date: First day of next month (e.g., 2026-02-01)
    """
    try:
        from dateutil.relativedelta import relativedelta
        import calendar

        today = datetime.now()

        # Calculate dynamic date range for current month
        first_of_month = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        last_of_month = today.replace(day=last_day)

        start_date = first_of_month.strftime('%Y-%m-%d')
        end_date = last_of_month.strftime('%Y-%m-%d')

        logger.info(f"🔄 Fetching paused appointments from {start_date} to {end_date} for missed-month messages...")

        # Single API call to get all paused appointments for the month
        result = await get_paused_appointments_between_dates(
            start_date=start_date,
            end_date=end_date,
            service_id=None  # Get all services
        )

        all_missed = []
        if result.get('success'):
            response_data = result.get('data', {})
            if isinstance(response_data, dict):
                all_missed = response_data.get('appointments', [])
            elif isinstance(response_data, list):
                all_missed = response_data

        if not all_missed:
            logger.info("ℹ️ No missed appointments found for this month")
            return {
                "success": True,
                "message": "No missed appointments found",
                "month": first_of_month.strftime('%B %Y'),
                "total_missed": 0,
                "total_messages": 0
            }

        logger.info(f"✅ Found {len(all_missed)} missed appointments this month")

        # ============================================================
        # Fetch all DONE appointments for the same month
        # We need the DATE of each Done appointment to compare with missed dates
        # Only skip if Done is AFTER the missed appointment
        # ============================================================
        customer_done_dates = {}  # phone -> list of done appointment datetimes

        print(f"\n   🔍 Fetching Done appointments to check against missed dates...")

        # Fetch Done appointments for each day of the month (up to today)
        async def fetch_done_for_date(date):
            query_date = date.strftime('%Y-%m-%d')
            done_result = await send_appointment_reminders(date=query_date, status='Done')
            if done_result.get('success'):
                data = done_result.get('data', {})
                return data.get('appointments', []) if isinstance(data, dict) else data
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
                    phone = done_apt.get('phone')
                    apt_details = done_apt.get('appointment_details', {})
                    done_date_str = apt_details.get('date') if apt_details else None

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
                customer_data = apt.get('customer', {})
                customer_phone = customer_data.get('phone')
                customer_name = customer_data.get('name', 'عميلنا العزيز')
                customer_user_code = customer_data.get('user_code')

                apt_datetime_str = apt.get('date')
                service_name = apt.get('service', 'جلسة ليزر')
                branch_name = apt.get('branch', 'الفرع الرئيسي')
                appointment_id = apt.get('appointment_id')
                machine_name = apt.get('machine')

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
                    "phone_number": "01234567"
                }

                message_id = smart_messaging.schedule_message(
                    customer_phone,
                    "missed_this_month",
                    send_time,
                    placeholders,
                    user_persistence.get_user_language(customer_phone),
                    service_id=None,
                    service_name=service_name
                )

                if message_id:
                    total_messages += 1
                    customers_already_scheduled.add(phone_normalized)
                else:
                    skipped_schedule_failed += 1

            except Exception as e:
                logger.debug(f"⚠️ Error processing missed appointment: {e}")
                continue

        total_skipped = skipped_missing_data + skipped_duplicate + skipped_parse_error + skipped_has_done + skipped_past + skipped_schedule_failed

        print(f"\n{'='*80}")
        print(f"✅ MISSED-MONTH MESSAGES POPULATION COMPLETE")
        print(f"   📊 Month: {first_of_month.strftime('%B %Y')}")
        print(f"   📅 Date range: {start_date} to {end_date}")
        print(f"   - Paused appointments found: {len(all_missed)}")
        print(f"   - Messages scheduled: {total_messages}")
        print(f"   ─────────────────────────────────")
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
        print(f"{'='*80}\n")

        return {
            "success": True,
            "message": f"✅ Populated missed-month messages",
            "month": first_of_month.strftime('%B %Y'),
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
                "schedule_failed": skipped_schedule_failed
            }
        }

    except Exception as e:
        logger.error(f"❌ Error in missed-month population: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }
