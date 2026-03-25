# -*- coding: utf-8 -*-
"""
Event handlers module: Startup and shutdown events
Handles initialization of WhatsApp provider and scheduling services.
"""

import datetime
import asyncio
import os
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
from services.daily_template_dispatcher import daily_template_dispatcher


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
        from services.smart_messaging import smart_messaging, deliver_scheduled_smart_whatsapp
        from services.appointment_scheduler import (
            populate_scheduled_messages_from_appointments,
            populate_no_show_messages_from_missed_appointments,
            populate_one_month_followups,
            populate_missed_month_messages,
            populate_missed_yesterday_messages
        )
        
        scheduler = AsyncIOScheduler()
        dispatcher_interval_minutes = max(
            1,
            int(os.getenv("SMART_DISPATCHER_INTERVAL_MINUTES", "5")),
        )
        monitor_interval_minutes = max(
            1,
            int(os.getenv("SMART_MONITOR_INTERVAL_MINUTES", "5")),
        )
        
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
                from storage.persistent_storage import APP_SETTINGS_FILE
                settings_file = str(APP_SETTINGS_FILE)
                smart_messaging_enabled = True
                preview_mode_enabled = False

                if os.path.exists(settings_file):
                    try:
                        with open(settings_file, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                        smart_messaging_enabled = settings.get('smartMessaging', {}).get('enabled', True)
                        preview_mode_enabled = settings.get('smartMessaging', {}).get('previewBeforeSend', False)
                    except Exception as e:
                        print(f"Error reading settings: {e}")

                # If smart messaging is disabled globally, skip processing
                if not smart_messaging_enabled:
                    print(
                        "Smart Messaging is DISABLED globally (app_settings smartMessaging.enabled=false). "
                        "Skipping bot queue sends. Note: CRM/API may still send reminder_24h via "
                        "send_appointment_reminders — other templates need this toggle ON."
                    )
                    return

                print(
                    f"[smart_scheduler] queue_monitor tick scheduled_pool={len(smart_messaging.scheduled_messages)}"
                )

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
                                        # Send using WhatsApp adapter (template when configured — required outside 24h window)
                                        from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
                                        adapter = WhatsAppFactory.get_adapter()
                                        result = await deliver_scheduled_smart_whatsapp(
                                            adapter,
                                            phone=phone,
                                            template_id=template_id,
                                            language=msg.get("language") or "ar",
                                            placeholders=msg.get("placeholders") or {},
                                            rendered_text=content,
                                        )

                                        if result.get('success'):
                                            message_preview_service.mark_as_sent(message_id)
                                            smart_messaging.mark_messages_sent_by_phone(phone, template_id)
                                            print(f"   Sent message {message_id} to {phone}")

                                            _sched = smart_messaging.scheduled_messages.get(message_id) or {}
                                            _meta = _sched.get("metadata") if isinstance(_sched.get("metadata"), dict) else {}
                                            _ph = _sched.get("placeholders") or {}
                                            _apt_id = _meta.get("appointment_id") or _ph.get("appointment_id")

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
                                                    "message_id": message_id,
                                                    **({"appointment_id": _apt_id} if _apt_id is not None else {}),
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

                # Always process due rows with status=scheduled (automation exempts preview; CRM-style queue)
                print("SENDING due Smart Messaging (status=scheduled, preview-independent)")
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
                        result = await deliver_scheduled_smart_whatsapp(
                            adapter,
                            phone=phone,
                            template_id=msg_type,
                            language=msg.get("language") or "ar",
                            placeholders=msg.get("placeholders") or {},
                            rendered_text=content,
                        )

                        if result.get('dry_run'):
                            sent_count += 1
                            smart_messaging.mark_message_dry_run(message_id)
                            print(f"   📋 Dry-run (would send)")
                        elif result.get('success'):
                            sent_count += 1
                            smart_messaging.mark_message_sent(message_id)
                            print(f"   ✅ Sent successfully")

                            _sched = smart_messaging.scheduled_messages.get(message_id) or {}
                            _meta = _sched.get("metadata") if isinstance(_sched.get("metadata"), dict) else {}
                            _ph = _sched.get("placeholders") or {}
                            _apt_id = _meta.get("appointment_id") or _ph.get("appointment_id")

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
                                    "message_id": message_id,
                                    **({"appointment_id": _apt_id} if _apt_id is not None else {}),
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
                from storage.persistent_storage import APP_SETTINGS_FILE
                settings_file = str(APP_SETTINGS_FILE)
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
                                result = await deliver_scheduled_smart_whatsapp(
                                    adapter,
                                    phone=customer_phone,
                                    template_id="missed_yesterday",
                                    language=language,
                                    placeholders=placeholders,
                                    rendered_text=message_content,
                                )
                                if result.get('dry_run'):
                                    print(f"📋 [DRY-RUN] Would send missed yesterday to {customer_phone}")
                                elif result.get('success'):
                                    print(f"✅ Sent missed yesterday message to {customer_phone}")

                                    smart_messaging.mark_messages_sent_by_phone(customer_phone, "missed_yesterday")

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
                                else:
                                    print(
                                        f"❌ Missed yesterday send failed for {customer_phone}: "
                                        f"{result.get('error', 'unknown')}"
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
                from storage.persistent_storage import APP_SETTINGS_FILE
                settings_file = str(APP_SETTINGS_FILE)
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
                                result = await deliver_scheduled_smart_whatsapp(
                                    adapter,
                                    phone=customer_phone,
                                    template_id="missed_this_month",
                                    language=language,
                                    placeholders=placeholders,
                                    rendered_text=message_content,
                                )
                                if result.get('dry_run'):
                                    print(f"📋 [DRY-RUN] Would send missed this month to {customer_phone}")
                                elif result.get('success'):
                                    print(f"✅ Sent missed this month message to {customer_phone}")

                                    smart_messaging.mark_messages_sent_by_phone(customer_phone, "missed_this_month")

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
                                else:
                                    print(
                                        f"❌ Missed this month send failed for {customer_phone}: "
                                        f"{result.get('error', 'unknown')}"
                                    )
                        except Exception as e:
                            print(f"❌ Error sending missed this month message: {e}")
                else:
                    print(f"ℹ️ No missed appointments this month")
            except Exception as e:
                print(f"❌ Error in missed this month follow-ups job: {e}")
        
        # Job 5: Daily refresh - clear stale messages and re-populate fresh ones
        async def daily_refresh_messages_job():
            """
            Runs daily to clear stale queue entries while preserving
            long-horizon follow-ups and campaign messages.
            """
            try:
                print("\n" + "=" * 80)
                print("🌅 DAILY MESSAGE REFRESH - Clearing stale queue entries")
                print("=" * 80)

                result = smart_messaging.clear_daily_messages()
                print(f"   🧹 Cleared {result['cleared']} stale messages, kept {result['kept']}")

                print("=" * 80)
                print("✅ DAILY REFRESH COMPLETE")
                print("=" * 80 + "\n")
            except Exception as e:
                print(f"❌ Error in daily refresh job: {e}")
                import traceback
                traceback.print_exc()

        async def run_daily_template_dispatcher_job():
            """
            Minute-level runner that dispatches enabled template jobs
            when local time matches configured HH:MM.
            """
            try:
                dispatch_result = await daily_template_dispatcher.tick()
                run_count = dispatch_result.get("run_count", 0)
                if run_count:
                    print(f"📅 Daily template dispatcher ran {run_count} template job(s)")
                    for item in dispatch_result.get("jobs_run", []):
                        result = item.get("result", {})
                        print(
                            f"   - {item.get('template_id')}: "
                            f"{result.get('scheduled_count', 0)} queued "
                            f"(candidates={result.get('total_candidates', 0)})"
                        )
            except Exception as e:
                print(f"❌ Error in daily template dispatcher: {e}")
                import traceback
                traceback.print_exc()

        # Schedule jobs
        # DAILY REFRESH: Clear stale in-memory queue once a day
        scheduler.add_job(
            daily_refresh_messages_job,
            'cron',
            hour=0,
            minute=1,
            id='daily_refresh_messages',
            name='Daily Refresh - Clear Stale Scheduled Messages',
            replace_existing=True
        )

        # Template dispatcher cadence (default 5m). Dispatcher itself handles due windows safely.
        scheduler.add_job(
            run_daily_template_dispatcher_job,
            'interval',
            minutes=dispatcher_interval_minutes,
            id='daily_template_dispatcher',
            name='Daily Template Dispatcher (Config-Driven)',
            replace_existing=True
        )

        # Monitor queue and send due messages (default every 5m)
        scheduler.add_job(
            monitor_smart_messages_job,
            'interval',
            minutes=monitor_interval_minutes,
            id='monitor_smart_messages',
            name='Monitor Smart Messaging Scheduled Messages',
            replace_existing=True
        )

        scheduler.start()

        print("\n🚀 Running initial daily template dispatcher check...")
        asyncio.create_task(run_daily_template_dispatcher_job())
        print("✅ Initial dispatcher check queued")

        print("✅ Smart Messaging Scheduler started successfully")
        print("📅 Scheduled jobs:")
        print("   - Daily refresh: Daily at 00:01")
        print(f"   - Template dispatcher: Every {dispatcher_interval_minutes} minute(s)")
        print(f"   - Queue monitor/sender: Every {monitor_interval_minutes} minute(s)")
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
