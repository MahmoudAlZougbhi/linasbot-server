# -*- coding: utf-8 -*-
"""
Event handlers module: Startup and shutdown events
Handles initialization of WhatsApp provider and scheduling services.
"""

import datetime
import asyncio
from typing import Any, Dict, Optional

from modules.core import app, PYDUB_AVAILABLE, AudioSegment
import config
from utils.utils import get_firestore_db, save_conversation_message_to_firestore
from services.api_integrations import send_appointment_reminders, get_missed_appointments, get_paused_appointments_between_dates, log_report_event
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from services.appointment_scheduler import (
    populate_scheduled_messages_from_appointments,
    populate_no_show_messages_from_missed_appointments,
    populate_one_month_followups,
    populate_missed_month_messages,
    populate_missed_yesterday_messages
)


@app.on_event("startup")
async def startup_event():
    """Initialize MontyMobile as the default WhatsApp provider on startup"""
    try:
        print("=" * 60)
        print("🚀 INITIALIZING WHATSAPP PROVIDER")
        print("=" * 60)
        
        # Use MontyMobile as the default provider (new endpoint)
        adapter = WhatsAppFactory.get_adapter("montymobile")
        print(f"✅ MontyMobile adapter initialized: {type(adapter).__name__}")
        print(f"✅ Current provider: {WhatsAppFactory.get_current_provider()}")
        print("=" * 60)
    except Exception as e:
        print(f"❌ ERROR initializing Qiscus adapter: {e}")
        print("⚠️ Bot will continue but WhatsApp functionality may not work")
        import traceback
        traceback.print_exc()
    
    # Initialize Smart Messaging Scheduler
    try:
        print("=" * 60)
        print("📅 INITIALIZING SMART MESSAGING SCHEDULER")
        print("=" * 60)
        
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.smart_messaging import smart_messaging
        from services.appointment_scheduler import (
            populate_scheduled_messages_from_appointments,
            populate_no_show_messages_from_missed_appointments,
            populate_one_month_followups,
            populate_missed_month_messages,
            populate_missed_yesterday_messages
        )
        
        scheduler = AsyncIOScheduler()
        
        # Job 0A: Populate scheduled messages from REAL appointments (via send_appointment_reminders endpoint)
        async def populate_messages_job():
            """Fetch real appointments from backend and populate scheduled messages"""
            try:
                print("🔄 POPULATING SCHEDULED MESSAGES FROM REAL APPOINTMENTS")
                print("=" * 80)
                result = await populate_scheduled_messages_from_appointments()
                if result.get('success'):
                    print(f"✅ {result.get('message')}")
                    print(f"   📊 Statistics:")
                    print(f"   - Appointments found: {result.get('total_appointments', 0)}")
                    print(f"   - Processed: {result.get('processed_appointments', 0)}")
                    print(f"   - Failed: {result.get('failed_appointments', 0)}")
                    print(f"   - Messages scheduled: {result.get('total_messages', 0)}")
                    print(f"   - Total in dict: {result.get('scheduled_messages_count', 0)}")
                else:
                    print(f"⚠️ Failed to populate messages: {result.get('message')}")
                print("=" * 80)
            except Exception as e:
                print(f"❌ Error populating scheduled messages: {e}")
                import traceback
                traceback.print_exc()
        
        # Job 0A2: Populate NO-SHOW follow-up messages from missed appointments endpoint
        async def populate_no_show_messages_job():
            """Fetch missed appointments from backend and populate no-show messages"""
            try:
                print("🚨 POPULATING NO-SHOW FOLLOW-UP MESSAGES FROM MISSED APPOINTMENTS")
                print("=" * 80)
                result = await populate_no_show_messages_from_missed_appointments()
                if result.get('success'):
                    print(f"✅ {result.get('message')}")
                    print(f"   📊 Statistics:")
                    print(f"   - Missed appointments found: {result.get('total_missed', 0)}")
                    print(f"   - Processed: {result.get('processed_missed', 0)}")
                    print(f"   - Failed: {result.get('failed_missed', 0)}")
                    print(f"   - No-show messages created: {result.get('total_messages', 0)}")
                    print(f"   - Total in dict: {result.get('scheduled_messages_count', 0)}")
                else:
                    print(f"⚠️ Failed to populate no-show messages: {result.get('message')}")
                print("=" * 80)
            except Exception as e:
                print(f"❌ Error populating no-show messages: {e}")
                import traceback
                traceback.print_exc()

        # Job 0A3: Populate 1-MONTH FOLLOW-UP messages (from last month's appointments)
        async def populate_one_month_job():
            """Fetch last month's appointments and populate 1-month follow-up messages"""
            try:
                print("📅 POPULATING 1-MONTH FOLLOW-UP MESSAGES")
                print("=" * 80)
                result = await populate_one_month_followups()
                if result.get('success'):
                    print(f"✅ {result.get('message')}")
                    print(f"   📊 Month: {result.get('month', 'N/A')}")
                    print(f"   - Appointments found: {result.get('total_appointments', 0)}")
                    print(f"   - Follow-ups scheduled: {result.get('total_messages', 0)}")
                else:
                    print(f"⚠️ Failed to populate 1-month messages: {result.get('message')}")
                print("=" * 80)
            except Exception as e:
                print(f"❌ Error populating 1-month messages: {e}")
                import traceback
                traceback.print_exc()

        # Job 0A4: Populate MISSED-MONTH messages (from this month's missed appointments)
        async def populate_missed_month_job():
            """Fetch this month's missed appointments and populate missed-month messages"""
            try:
                print("📅 POPULATING MISSED-MONTH MESSAGES")
                print("=" * 80)
                result = await populate_missed_month_messages()
                if result.get('success'):
                    print(f"✅ {result.get('message')}")
                    print(f"   📊 Month: {result.get('month', 'N/A')}")
                    print(f"   - Missed appointments found: {result.get('total_missed', 0)}")
                    print(f"   - Messages scheduled: {result.get('total_messages', 0)}")
                else:
                    print(f"⚠️ Failed to populate missed-month messages: {result.get('message')}")
                print("=" * 80)
            except Exception as e:
                print(f"❌ Error populating missed-month messages: {e}")
                import traceback
                traceback.print_exc()

        # Job 0A5: Populate MISSED-YESTERDAY messages (from yesterday's paused appointments)
        async def populate_missed_yesterday_job():
            """Fetch yesterday's paused appointments and populate missed-yesterday messages"""
            try:
                print("📅 POPULATING MISSED-YESTERDAY MESSAGES")
                print("=" * 80)
                result = await populate_missed_yesterday_messages()
                if result.get('success'):
                    print(f"✅ {result.get('message')}")
                    print(f"   📅 Date: {result.get('date', 'N/A')}")
                    print(f"   - Paused appointments found: {result.get('total_missed', 0)}")
                    print(f"   - Messages scheduled: {result.get('total_messages', 0)}")
                else:
                    print(f"⚠️ Failed to populate missed-yesterday messages: {result.get('message')}")
                print("=" * 80)
            except Exception as e:
                print(f"❌ Error populating missed-yesterday messages: {e}")
                import traceback
                traceback.print_exc()

        # Job 0B: Monitor Smart Messaging scheduled messages with global toggle & preview mode support
        async def monitor_smart_messages_job():
            """Monitor scheduled messages with smart controls"""
            try:
                import json
                import os

                # Check if smart messaging is globally enabled
                settings_file = 'data/app_settings.json'
                smart_messaging_enabled = True
                preview_mode_enabled = True

                if os.path.exists(settings_file):
                    try:
                        with open(settings_file, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                        smart_messaging_enabled = settings.get('smartMessaging', {}).get('enabled', True)
                        preview_mode_enabled = settings.get('smartMessaging', {}).get('previewBeforeSend', True)
                    except Exception as e:
                        print(f"Error reading settings: {e}")

                # If smart messaging is disabled globally, skip processing
                if not smart_messaging_enabled:
                    print("Smart Messaging is DISABLED globally. Skipping message processing.")
                    return

                # If preview mode is enabled, messages need manual approval
                if preview_mode_enabled:
                    print("PREVIEW MODE: Smart Messages require manual approval in dashboard")
                    print("=" * 80)

                    # Check preview queue for pending messages
                    try:
                        from services.message_preview_service import message_preview_service
                        pending_count = len(message_preview_service.get_pending_messages(status='pending_approval'))
                        approved_count = len(message_preview_service.get_pending_messages(status='approved'))

                        print(f"   Pending approval: {pending_count} messages")
                        print(f"   Approved (ready to send): {approved_count} messages")

                        # Process approved messages
                        if approved_count > 0:
                            approved_messages = message_preview_service.get_pending_messages(status='approved')
                            print(f"\n Sending {approved_count} approved messages...")

                            for msg in approved_messages:
                                try:
                                    phone = msg.get('customer_phone')
                                    content = msg.get('rendered_content')
                                    message_id = msg.get('message_id')
                                    template_id = msg.get('template_id', 'smart_message')
                                    customer_name = msg.get('customer_name', 'Customer')

                                    if phone and content:
                                        # Send using WhatsApp adapter
                                        from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
                                        adapter = WhatsAppFactory.get_adapter()
                                        result = await adapter.send_text_message(phone, content)

                                        if result.get('success'):
                                            message_preview_service.mark_as_sent(message_id)
                                            print(f"   Sent message {message_id} to {phone}")

                                            # Save to conversation history for continuous context
                                            await save_conversation_message_to_firestore(
                                                user_id=phone,
                                                role="ai",
                                                text=content,
                                                conversation_id=None,  # Will create/continue conversation
                                                user_name=customer_name,
                                                phone_number=phone,
                                                metadata={
                                                    "source": "smart_message",
                                                    "type": template_id,
                                                    "message_id": message_id
                                                }
                                            )
                                            print(f"   💾 Saved smart message to conversation history for {phone}")
                                        else:
                                            print(f"   Failed to send {message_id}: {result.get('error')}")
                                except Exception as send_error:
                                    print(f"   Error sending message: {send_error}")

                    except Exception as preview_error:
                        print(f"Error checking preview queue: {preview_error}")

                    print("=" * 80)
                    return

                # Direct send mode (when preview is disabled)
                print("SENDING Smart Messaging scheduled messages (preview disabled)")
                print("=" * 80)

                # Get messages that are ready to send
                messages_to_send = await smart_messaging.process_scheduled_messages()

                if not messages_to_send:
                    print("No pending Smart Messages ready to send at this time")
                    print("=" * 80)
                    return

                print(f"Found {len(messages_to_send)} messages READY TO SEND")
                print("=" * 80)

                # Send each message
                from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
                adapter = WhatsAppFactory.get_adapter()
                sent_count = 0
                failed_count = 0

                for i, msg in enumerate(messages_to_send, 1):
                    phone = msg.get('phone')
                    content = msg.get('content')
                    msg_type = msg.get('type')
                    message_id = msg.get('message_id')
                    customer_name = msg.get('customer_name', 'Customer')

                    print(f"\n📤 Sending Message #{i}:")
                    print(f"   ID: {message_id}")
                    print(f"   Type: {msg_type}")
                    print(f"   To: {phone}")
                    print(f"   Content: {content[:100]}{'...' if len(content) > 100 else ''}")

                    try:
                        # Actually send the message
                        result = await adapter.send_text_message(phone, content)

                        if result.get('success'):
                            sent_count += 1
                            smart_messaging.mark_message_sent(message_id)
                            print(f"   ✅ Sent successfully")

                            # Save to conversation history for continuous context
                            await save_conversation_message_to_firestore(
                                user_id=phone,
                                role="ai",
                                text=content,
                                conversation_id=None,
                                user_name=customer_name,
                                phone_number=phone,
                                metadata={
                                    "source": "smart_message",
                                    "type": msg_type,
                                    "message_id": message_id
                                }
                            )
                            print(f"   💾 Saved to conversation history")
                        else:
                            failed_count += 1
                            error_msg = result.get('error', 'Unknown error')
                            smart_messaging.mark_message_failed(message_id, error_msg)
                            print(f"   ❌ Failed to send: {error_msg}")

                    except Exception as send_error:
                        failed_count += 1
                        smart_messaging.mark_message_failed(message_id, str(send_error))
                        print(f"   ❌ Error sending: {send_error}")

                print("\n" + "=" * 80)
                print(f"Send complete: {sent_count} sent, {failed_count} failed")
                print("=" * 80)

            except Exception as e:
                print(f"Error in monitor smart messages job: {e}")
                import traceback
                traceback.print_exc()
        
        # Job 1: Trigger backend appointment reminders every 30 minutes
        async def send_appointment_reminders_job():
            try:
                print("📧 Running appointment reminders job...")
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                result = await send_appointment_reminders(date=today)
                if result.get('success'):
                    print(f"✅ Appointment reminders sent successfully")
                else:
                    print(f"⚠️ Appointment reminders failed: {result.get('message')}")
            except Exception as e:
                print(f"❌ Error in appointment reminders job: {e}")
        
        # Job 2: Send "missed yesterday" follow-ups daily at 10 AM
        async def send_missed_yesterday_followups():
            try:
                print("📨 Running missed yesterday follow-ups job...")

                # Check if smart messaging is globally enabled
                settings_file = 'data/app_settings.json'
                smart_messaging_enabled = True

                if os.path.exists(settings_file):
                    try:
                        with open(settings_file, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                        smart_messaging_enabled = settings.get('smartMessaging', {}).get('enabled', True)
                    except Exception as e:
                        print(f"Error reading settings: {e}")

                if not smart_messaging_enabled:
                    print("⏸️ Smart Messaging is DISABLED. Skipping missed yesterday follow-ups.")
                    return

                yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

                # Use the new paused appointments API with yesterday as both start and end
                result = await get_paused_appointments_between_dates(
                    start_date=yesterday,
                    end_date=yesterday,
                    service_id=None
                )

                paused_appointments = []
                if result.get('success'):
                    response_data = result.get('data', {})
                    if isinstance(response_data, dict):
                        paused_appointments = response_data.get('appointments', [])
                    elif isinstance(response_data, list):
                        paused_appointments = response_data

                if paused_appointments:
                    print(f"📋 Found {len(paused_appointments)} paused appointments from yesterday")

                    for appointment in paused_appointments:
                        try:
                            # New API response structure
                            customer_data = appointment.get('customer', {})
                            customer_phone = customer_data.get('phone')
                            customer_name = customer_data.get('name', 'عميلنا العزيز')
                            language = 'ar'  # Default language

                            if not customer_phone:
                                continue

                            placeholders = {
                                'customer_name': customer_name,
                                'phone_number': config.TRAINER_WHATSAPP_NUMBER or '+961 XX XXXXXX'
                            }

                            message_content = smart_messaging.get_message_content(
                                'missed_yesterday',
                                language,
                                placeholders
                            )

                            if message_content:
                                adapter = WhatsAppFactory.get_adapter()
                                await adapter.send_text_message(customer_phone, message_content)
                                print(f"✅ Sent missed yesterday message to {customer_phone}")

                                # Sync in-memory scheduled_messages dict
                                smart_messaging.mark_messages_sent_by_phone(customer_phone, "missed_yesterday")

                                # Save to conversation history for continuous context
                                await save_conversation_message_to_firestore(
                                    user_id=customer_phone,
                                    role="ai",
                                    text=message_content,
                                    conversation_id=None,
                                    user_name=customer_name,
                                    phone_number=customer_phone,
                                    metadata={
                                        "source": "smart_message",
                                        "type": "missed_yesterday"
                                    }
                                )
                                print(f"💾 Saved missed yesterday message to conversation history")

                                log_report_event(
                                    "scheduled_message_sent",
                                    customer_phone,
                                    "N/A",
                                    {"type": "missed_yesterday", "customer_name": customer_name}
                                )
                        except Exception as e:
                            print(f"❌ Error sending missed yesterday message: {e}")
                else:
                    print(f"ℹ️ No paused appointments from yesterday")
            except Exception as e:
                print(f"❌ Error in missed yesterday follow-ups job: {e}")
        
        # Job 3: Send "missed this month" follow-ups on 1st of each month at 11 AM
        async def send_missed_this_month_followups():
            try:
                print("📨 Running missed this month follow-ups job...")

                # Check if smart messaging is globally enabled
                settings_file = 'data/app_settings.json'
                smart_messaging_enabled = True

                if os.path.exists(settings_file):
                    try:
                        with open(settings_file, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                        smart_messaging_enabled = settings.get('smartMessaging', {}).get('enabled', True)
                    except Exception as e:
                        print(f"Error reading settings: {e}")

                if not smart_messaging_enabled:
                    print("⏸️ Smart Messaging is DISABLED. Skipping missed this month follow-ups.")
                    return

                first_day_of_month = datetime.datetime.now().replace(day=1).strftime('%Y-%m-%d')
                result = await get_missed_appointments(date=first_day_of_month)
                
                if result.get('success') and result.get('data'):
                    missed_appointments = result['data']
                    print(f"📋 Found {len(missed_appointments)} missed appointments this month")
                    
                    customers_contacted = set()
                    
                    for appointment in missed_appointments:
                        try:
                            customer_phone = appointment.get('customer_phone', appointment.get('phone'))
                            
                            if not customer_phone or customer_phone in customers_contacted:
                                continue
                            
                            customers_contacted.add(customer_phone)
                            
                            customer_name = appointment.get('customer_name', appointment.get('name', 'عميلنا العزيز'))
                            language = appointment.get('language', 'ar')
                            
                            placeholders = {
                                'customer_name': customer_name,
                                'phone_number': config.TRAINER_WHATSAPP_NUMBER or '+961 XX XXXXXX'
                            }
                            
                            message_content = smart_messaging.get_message_content(
                                'missed_this_month',
                                language,
                                placeholders
                            )
                            
                            if message_content:
                                adapter = WhatsAppFactory.get_adapter()
                                await adapter.send_text_message(customer_phone, message_content)
                                print(f"✅ Sent missed this month message to {customer_phone}")

                                # Sync in-memory scheduled_messages dict
                                smart_messaging.mark_messages_sent_by_phone(customer_phone, "missed_this_month")

                                # Save to conversation history for continuous context
                                await save_conversation_message_to_firestore(
                                    user_id=customer_phone,
                                    role="ai",
                                    text=message_content,
                                    conversation_id=None,
                                    user_name=customer_name,
                                    phone_number=customer_phone,
                                    metadata={
                                        "source": "smart_message",
                                        "type": "missed_this_month"
                                    }
                                )
                                print(f"💾 Saved missed this month message to conversation history")

                                log_report_event(
                                    "scheduled_message_sent",
                                    customer_phone,
                                    "N/A",
                                    {"type": "missed_this_month", "customer_name": customer_name}
                                )
                        except Exception as e:
                            print(f"❌ Error sending missed this month message: {e}")
                else:
                    print(f"ℹ️ No missed appointments this month")
            except Exception as e:
                print(f"❌ Error in missed this month follow-ups job: {e}")
        
        # Job 4: Send "attended yesterday" thank you messages daily at 9 PM
        async def send_attended_yesterday_messages():
            try:
                print("📨 Running attended yesterday thank you messages job...")

                # Check if smart messaging is globally enabled
                settings_file = 'data/app_settings.json'
                smart_messaging_enabled = True

                if os.path.exists(settings_file):
                    try:
                        with open(settings_file, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                        smart_messaging_enabled = settings.get('smartMessaging', {}).get('enabled', True)
                    except Exception as e:
                        print(f"Error reading settings: {e}")

                if not smart_messaging_enabled:
                    print("⏸️ Smart Messaging is DISABLED. Skipping attended yesterday messages.")
                    return

                yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%d/%m/%Y')
                
                db = get_firestore_db()
                if not db:
                    print("⚠️ Firebase not initialized, skipping attended yesterday messages")
                    return
                
                app_id_for_firestore = "linas-ai-bot-backend"
                users_collection = db.collection("artifacts").document(app_id_for_firestore).collection("users")
                
                users_docs = list(users_collection.stream())
                print(f"📋 Checking {len(users_docs)} users for attended appointments yesterday")
                
                customers_contacted = set()
                
                for user_doc in users_docs:
                    try:
                        user_id = user_doc.id
                        
                        if user_id in customers_contacted:
                            continue
                        
                        user_data = user_doc.to_dict()
                        phone_number = user_data.get('phone_number') or config.user_data_whatsapp.get(user_id, {}).get('phone_number')
                        
                        if not phone_number:
                            print(f"⚠️ No phone number found for user {user_id}, skipping")
                            continue
                        
                        phone_clean = str(phone_number).replace("+", "").replace(" ", "").replace("-", "")
                        if phone_clean.startswith("961"):
                            phone_clean = phone_clean[3:]
                        
                        from services.api_integrations import get_customer_appointments
                        appointments_result = await get_customer_appointments(phone_clean)
                        
                        if not appointments_result.get('success') or not appointments_result.get('data'):
                            continue
                        
                        appointments = appointments_result['data']
                        
                        attended_yesterday = False
                        next_appointment_date = None
                        
                        for appointment in appointments:
                            if appointment.get('date') == yesterday and appointment.get('status') == 'Done':
                                attended_yesterday = True
                                for next_apt in appointments:
                                    if next_apt.get('status') == 'Available':
                                        next_appointment_date = next_apt.get('date')
                                        break
                                break
                        
                        if attended_yesterday:
                            customers_contacted.add(user_id)
                            
                            customer_name = config.user_names.get(user_id, "عميلنا العزيز")
                            language = config.user_data_whatsapp.get(user_id, {}).get('user_preferred_lang', 'ar')
                            
                            placeholders = {
                                'customer_name': customer_name,
                                'phone_number': config.TRAINER_WHATSAPP_NUMBER or '+961 XX XXXXXX',
                                'next_appointment_date': next_appointment_date or 'سيتم تحديده قريباً'
                            }
                            
                            message_content = smart_messaging.get_message_content(
                                'attended_yesterday',
                                language,
                                placeholders
                            )
                            
                            if message_content:
                                adapter = WhatsAppFactory.get_adapter()
                                await adapter.send_text_message(user_id, message_content)
                                print(f"✅ Sent attended yesterday message to {user_id}")

                                # Sync in-memory scheduled_messages dict
                                smart_messaging.mark_messages_sent_by_phone(user_id, "attended_yesterday")

                                # Save to conversation history for continuous context
                                await save_conversation_message_to_firestore(
                                    user_id=user_id,
                                    role="ai",
                                    text=message_content,
                                    conversation_id=None,
                                    user_name=customer_name,
                                    phone_number=phone_number,
                                    metadata={
                                        "source": "smart_message",
                                        "type": "attended_yesterday"
                                    }
                                )
                                print(f"💾 Saved attended yesterday message to conversation history")

                                log_report_event(
                                    "scheduled_message_sent",
                                    user_id,
                                    "N/A",
                                    {"type": "attended_yesterday", "customer_name": customer_name}
                                )
                    except Exception as e:
                        print(f"❌ Error processing user {user_doc.id}: {e}")
                
                print(f"✅ Sent attended yesterday messages to {len(customers_contacted)} customers")
                
            except Exception as e:
                print(f"❌ Error in attended yesterday messages job: {e}")
                import traceback
                traceback.print_exc()
        
        # Job 5: Daily refresh - clear stale messages and re-populate fresh ones
        async def daily_refresh_messages_job():
            """
            Runs at midnight each day to:
            1. Clear stale messages from previous days (except 1-month and missed-month)
            2. Re-populate all message categories with fresh data
            """
            try:
                print("\n" + "=" * 80)
                print("🌅 DAILY MESSAGE REFRESH - Clearing stale messages and re-populating")
                print("=" * 80)

                # Step 1: Clear stale messages
                result = smart_messaging.clear_daily_messages()
                print(f"   🧹 Cleared {result['cleared']} stale messages, kept {result['kept']}")

                # Step 2: Re-populate all categories with fresh data
                print("   🔄 Re-populating scheduled messages...")
                await populate_messages_job()
                await populate_no_show_messages_job()
                await populate_one_month_job()
                await populate_missed_month_job()
                await populate_missed_yesterday_job()

                print("=" * 80)
                print("✅ DAILY REFRESH COMPLETE")
                print("=" * 80 + "\n")
            except Exception as e:
                print(f"❌ Error in daily refresh job: {e}")
                import traceback
                traceback.print_exc()

        # Schedule jobs
        # DAILY REFRESH: Clear stale messages and re-populate at midnight
        scheduler.add_job(
            daily_refresh_messages_job,
            'cron',
            hour=0,
            minute=1,
            id='daily_refresh_messages',
            name='Daily Refresh - Clear Stale Messages & Re-populate',
            replace_existing=True
        )

        # FIRST: Populate scheduled messages from real appointments (runs immediately on startup, then every 2 hours)
        scheduler.add_job(
            populate_messages_job,
            'interval',
            minutes=120,
            id='populate_appointments',
            name='Populate Scheduled Messages from Real Appointments',
            replace_existing=True
        )
        
        # FIRST-B: Populate NO-SHOW follow-up messages from missed appointments (runs immediately on startup, then every 1 hour)
        scheduler.add_job(
            populate_no_show_messages_job,
            'interval',
            minutes=60,
            id='populate_no_show_messages',
            name='Populate No-Show Follow-Up Messages from Missed Appointments',
            replace_existing=True
        )

        # FIRST-C: Populate 1-MONTH FOLLOW-UP messages (daily at 6 AM - from last month's appointments)
        scheduler.add_job(
            populate_one_month_job,
            'cron',
            hour=6,
            minute=0,
            id='populate_one_month_followups',
            name='Populate 1-Month Follow-Up Messages',
            replace_existing=True
        )

        # FIRST-D: Populate MISSED-MONTH messages (daily at 6:30 AM - from this month's missed appointments)
        scheduler.add_job(
            populate_missed_month_job,
            'cron',
            hour=6,
            minute=30,
            id='populate_missed_month_messages',
            name='Populate Missed-Month Messages',
            replace_existing=True
        )

        # FIRST-E: Populate MISSED-YESTERDAY messages (daily at 6:15 AM - from yesterday's paused appointments)
        scheduler.add_job(
            populate_missed_yesterday_job,
            'cron',
            hour=6,
            minute=15,
            id='populate_missed_yesterday_messages',
            name='Populate Missed-Yesterday Messages',
            replace_existing=True
        )

        # SECOND: Monitor Smart Messaging scheduled messages every 10 minutes (VERIFICATION MODE - NOT SENDING)
        scheduler.add_job(
            monitor_smart_messages_job,
            'interval',
            minutes=10,
            id='monitor_smart_messages',
            name='Monitor Smart Messaging Scheduled Messages (NOT SENDING)',
            replace_existing=True
        )
        
        scheduler.add_job(
            send_appointment_reminders_job,
            'interval',
            minutes=30,
            id='appointment_reminders',
            name='Send Appointment Reminders',
            replace_existing=True
        )
        
        scheduler.add_job(
            send_missed_yesterday_followups,
            'cron',
            hour=10,
            minute=0,
            id='missed_yesterday',
            name='Send Missed Yesterday Follow-ups',
            replace_existing=True
        )
        
        scheduler.add_job(
            send_missed_this_month_followups,
            'cron',
            day=1,
            hour=11,
            minute=0,
            id='missed_this_month',
            name='Send Missed This Month Follow-ups',
            replace_existing=True
        )
        
        scheduler.add_job(
            send_attended_yesterday_messages,
            'cron',
            hour=21,
            minute=0,
            id='attended_yesterday',
            name='Send Attended Yesterday Thank You',
            replace_existing=True
        )
        
        scheduler.start()

        # OPTIMIZATION: Run populate_messages in BACKGROUND (don't block startup)
        # These API calls can take 10-30 seconds, so run them asynchronously
        print("\n🚀 SCHEDULING INITIAL APPOINTMENT POPULATION (running in background)...")
        asyncio.create_task(populate_messages_job())
        print("🚨 SCHEDULING INITIAL NO-SHOW MESSAGES POPULATION (running in background)...")
        asyncio.create_task(populate_no_show_messages_job())
        print("📅 SCHEDULING INITIAL 1-MONTH FOLLOW-UP POPULATION (running in background)...")
        asyncio.create_task(populate_one_month_job())
        print("📅 SCHEDULING INITIAL MISSED-MONTH POPULATION (running in background)...")
        asyncio.create_task(populate_missed_month_job())
        print("📅 SCHEDULING INITIAL MISSED-YESTERDAY POPULATION (running in background)...")
        asyncio.create_task(populate_missed_yesterday_job())
        print("✅ Background tasks scheduled - startup will complete immediately")

        print("✅ Smart Messaging Scheduler started successfully")
        print("📅 Scheduled jobs:")
        print("   - Daily refresh (clear stale + re-populate): Daily at 00:01 AM")
        print("   - Populate messages from appointments: Every 2 hours (+ on startup)")
        print("   - Populate no-show messages from missed: Every 1 hour (+ on startup)")
        print("   - Populate 1-month follow-ups: Daily at 6 AM (+ on startup)")
        print("   - Populate missed-yesterday messages: Daily at 6:15 AM (+ on startup)")
        print("   - Populate missed-month messages: Daily at 6:30 AM (+ on startup)")
        print("   - Monitor messages: Every 10 minutes")
        print("   - Appointment reminders: Every 30 minutes")
        print("   - Missed yesterday follow-ups: Daily at 10:00 AM")
        print("   - Missed this month follow-ups: 1st of month at 11:00 AM")
        print("   - Attended yesterday thank you: Daily at 9:00 PM")
        print("=" * 60)
        
        app.state.scheduler = scheduler
        
    except Exception as e:
        print(f"❌ ERROR initializing Smart Messaging Scheduler: {e}")
        print("⚠️ Smart messaging will not work")
        import traceback
        traceback.print_exc()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        if hasattr(app.state, 'scheduler'):
            print("🛑 Shutting down Smart Messaging Scheduler...")
            app.state.scheduler.shutdown()
            print("✅ Scheduler shut down successfully")
    except Exception as e:
        print(f"❌ Error shutting down scheduler: {e}")
