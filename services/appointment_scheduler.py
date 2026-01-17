# -*- coding: utf-8 -*-
"""
Appointment Scheduler Service
Integrates real appointments from backend API endpoints with Smart Messaging system
Calls send_appointment_reminders() to get appointments and populates scheduled messages
"""

from datetime import datetime, timedelta
from services.api_integrations import send_appointment_reminders, get_missed_appointments
from services.smart_messaging import smart_messaging
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

        logger.info("🔄 Fetching appointments for next 7 days via backend API...")

        all_appointments = []
        today = datetime.now()

        # Query appointments for TOMORROW + next 6 days (total 7 days of future appointments)
        # Start from tomorrow to avoid fetching past appointments from today
        # Use asyncio.gather() to run API calls in PARALLEL instead of sequential
        async def fetch_date(days_ahead):
            query_date = (today + timedelta(days=days_ahead + 1)).strftime('%Y-%m-%d')  # +1 to start from tomorrow
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

        # Run all API calls in PARALLEL (much faster than sequential)
        results = await asyncio.gather(*[fetch_date(d) for d in range(7)], return_exceptions=True)

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

                # Only schedule future appointments (with some buffer)
                if apt_datetime < datetime.now() - timedelta(hours=1):
                    if idx < 3:
                        print(f"⏭️ Apt {idx}: Skipping past appointment: {apt_datetime_str} (parsed: {apt_datetime}, now: {datetime.now()})")
                    failed_count += 1
                    continue

                # DEBUG: Print first 3 that pass all checks
                if idx < 3:
                    print(f"🎉 Apt {idx}: PASSED ALL CHECKS, calling schedule_appointment_reminders")
                
                # Prepare customer data for smart_messaging
                customer_data = {
                    'phone': customer_phone,
                    'name': customer_name,
                    'language': 'ar',  # Default to Arabic
                    'service': service_name,
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
    Fetch missed appointments via get_missed_appointments() endpoint
    and populate smart_messaging dict with no-show follow-up messages.

    The backend's /agent/appointments/missed endpoint returns appointments that were missed.
    """
    try:
        import asyncio

        logger.info("🔄 Fetching missed appointments for no-show follow-ups...")

        all_missed_appointments = []
        today = datetime.now()

        # Query missed appointments for last 7 days (cover recent misses)
        # Use asyncio.gather() to run API calls in PARALLEL
        async def fetch_missed_date(days_back):
            query_date = (today - timedelta(days=days_back)).strftime('%Y-%m-%d')
            logger.debug(f"  Querying missed for: {query_date}")

            result = await get_missed_appointments(date=query_date)

            if not result.get('success'):
                logger.debug(f"  ⚠️ No missed appointments for {query_date}")
                return []

            # Extract missed appointments from response
            response_data = result.get('data', {})
            if isinstance(response_data, dict):
                appointments = response_data.get('appointments', [])
            elif isinstance(response_data, list):
                appointments = response_data
            else:
                appointments = []

            if appointments:
                logger.debug(f"  ✅ Found {len(appointments)} missed appointments for {query_date}")

            return appointments

        # Run all API calls in PARALLEL (much faster than sequential)
        results = await asyncio.gather(*[fetch_missed_date(d) for d in range(7)], return_exceptions=True)

        # Flatten results
        for result in results:
            if isinstance(result, list):
                all_missed_appointments.extend(result)
        
        if not all_missed_appointments:
            logger.info("ℹ️ No missed appointments found for last 7 days")
            return {
                "success": True,
                "message": "No missed appointments found",
                "total_missed": 0,
                "total_messages": 0,
                "no_show_messages_count": 0
            }
        
        logger.info(f"✅ Found {len(all_missed_appointments)} total missed appointments")
        
        total_messages = 0
        processed_count = 0
        failed_count = 0
        
        # For each missed appointment, schedule no-show follow-up
        for apt in all_missed_appointments:
            try:
                # Extract appointment details from backend response
                customer_phone = apt.get('phone')
                customer_name = apt.get('name', 'عميلنا العزيز')
                apt_details = apt.get('appointment_details', {})
                apt_datetime_str = apt_details.get('date')
                service_name = apt_details.get('service', 'جلسة ليزر')
                branch_name = apt_details.get('branch', 'الفرع الرئيسي')
                
                if not customer_phone or not apt_datetime_str:
                    failed_count += 1
                    continue
                
                # Parse appointment datetime
                apt_datetime = parse_appointment_date(apt_datetime_str)
                if not apt_datetime:
                    logger.debug(f"⚠️ Could not parse date: {apt_datetime_str}")
                    failed_count += 1
                    continue
                
                # Prepare customer data for smart_messaging
                customer_data = {
                    'phone': customer_phone,
                    'name': customer_name,
                    'language': 'ar',  # Default to Arabic
                    'service': service_name,
                    'branch': branch_name
                }
                
                # Schedule no-show follow-up message (1 hour after missed appointment)
                no_show_time = apt_datetime + timedelta(hours=1)
                
                message_id = smart_messaging.schedule_message(
                    customer_phone,
                    "no_show_followup",
                    no_show_time,
                    {
                        "customer_name": customer_name,
                        "appointment_date": apt_datetime.strftime("%Y-%m-%d"),
                        "appointment_time": apt_datetime.strftime("%H:%M"),
                        "branch_name": branch_name,
                        "service_name": service_name,
                        "phone_number": "01234567"  # Support phone
                    },
                    'ar'
                )
                
                if message_id:
                    total_messages += 1
                    processed_count += 1
                    logger.debug(f"✅ Scheduled no-show follow-up for {customer_name} ({customer_phone})")
                else:
                    failed_count += 1
                
            except Exception as e:
                logger.debug(f"⚠️ Error processing missed appointment: {e}")
                failed_count += 1
                continue
        
        logger.info(f"✅ Processed {processed_count} missed appointments, generated {total_messages} no-show messages")
        
        return {
            "success": True,
            "message": f"✅ Populated no-show follow-up messages from missed appointments",
            "total_missed": len(all_missed_appointments),
            "processed_missed": processed_count,
            "failed_missed": failed_count,
            "total_messages": total_messages,
            "no_show_messages_count": total_messages,
            "scheduled_messages_count": len(smart_messaging.scheduled_messages)
        }
        
    except Exception as e:
        logger.error(f"❌ Error in no-show population: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }
