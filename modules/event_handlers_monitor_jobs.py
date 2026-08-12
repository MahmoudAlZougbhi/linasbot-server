"""Smart messaging monitor and missed-followup jobs (LOC split)."""

from __future__ import annotations

import datetime
import json
import os

import config
from services.api_integrations import (
    get_missed_appointments,
    get_paused_appointments_between_dates,
    log_report_event,
    send_appointment_reminders,
)
from services.smart_messaging import deliver_scheduled_smart_whatsapp, smart_messaging
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from utils.utils import save_conversation_message_to_firestore


async def monitor_smart_messages_job() -> None:
    """Monitor scheduled messages with smart controls"""
    from services.durable_event_claim import release_job_lock, try_acquire_job_lock

    if not try_acquire_job_lock("monitor_smart_messages", ttl_seconds=max(60, max(1, int(os.getenv("SMART_MONITOR_INTERVAL_MINUTES", "5"))) * 60)):
        print("[smart_scheduler] monitor tick skipped — another instance holds the lock")
        return
    try:
        # Check if smart messaging is globally enabled
        from storage.persistent_storage import APP_SETTINGS_FILE

        settings_file = str(APP_SETTINGS_FILE)
        smart_messaging_enabled = True
        preview_mode_enabled = False

        if os.path.exists(settings_file):
            try:
                with open(settings_file, encoding="utf-8") as f:
                    settings = json.load(f)
                smart_messaging_enabled = settings.get("smartMessaging", {}).get("enabled", True)
                preview_mode_enabled = settings.get("smartMessaging", {}).get("previewBeforeSend", False)
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

        print(f"[smart_scheduler] queue_monitor tick scheduled_pool={len(smart_messaging.scheduled_messages)}")

        # If preview mode is enabled, messages need manual approval
        if preview_mode_enabled:
            print("PREVIEW MODE: Smart Messages require manual approval in dashboard")
            print("=" * 80)

            # Check preview queue for pending messages
            try:
                from services.message_preview_service import message_preview_service

                pending_count = len(message_preview_service.get_pending_messages(status="pending_approval"))
                approved_count = len(message_preview_service.get_pending_messages(status="approved"))

                print(f"   Pending approval: {pending_count} messages")
                print(f"   Approved (ready to send): {approved_count} messages")

                # Process approved messages
                if approved_count > 0:
                    approved_messages = message_preview_service.get_pending_messages(status="approved")
                    print(f"\n Sending {approved_count} approved messages...")

                    for msg in approved_messages:
                        try:
                            phone = str(msg.get("customer_phone") or "")
                            content = str(msg.get("rendered_content") or "")
                            message_id = str(msg.get("message_id") or "")
                            template_id = str(msg.get("template_id") or "smart_message")
                            customer_name = str(msg.get("customer_name") or "Customer")

                            if not (phone and content and message_id):
                                continue
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

                                if result.get("dry_run"):
                                    # Same shape as non-preview path: success=True + dry_run — not a real WhatsApp send.
                                    print(
                                        f"   📋 Dry-run for {message_id} (ENABLE_SENDING=false or local/sandbox "
                                        f"— no WhatsApp). Not saving to Live Chat."
                                    )
                                    if message_id in smart_messaging.scheduled_messages:
                                        smart_messaging.mark_message_dry_run(message_id)
                                    else:
                                        message_preview_service.mark_would_send(message_id)
                                elif result.get("success"):
                                    message_preview_service.mark_as_sent(message_id)
                                    # Only mark this row as sent. mark_messages_sent_by_phone would mark
                                    # every scheduled/pending message for the same phone + template as
                                    # sent without delivering them — Live Chat / dashboard then looks
                                    # "done" while WhatsApp only got the first one.
                                    smart_messaging.mark_message_sent(message_id)
                                    print(f"   Sent message {message_id} to ***{str(phone)[-4:] if phone else ''}")

                                    _sched = smart_messaging.scheduled_messages.get(message_id) or {}
                                    _meta_raw = _sched.get("metadata")
                                    _meta = _meta_raw if isinstance(_meta_raw, dict) else {}
                                    _ph_raw = _sched.get("placeholders")
                                    _ph = _ph_raw if isinstance(_ph_raw, dict) else {}
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
                                        },
                                    )
                                    print(f"   💾 Saved smart message to conversation history for ***{str(phone)[-4:] if phone else ''}")
                                else:
                                    print(f"   Failed to send {message_id}: {result.get('error')}")
                        except Exception as send_error:
                            print(f"   Error sending message: {send_error}")

            except Exception as preview_error:
                print(f"Error checking preview queue: {preview_error}")

            print("=" * 80)
            # Preview mode blocks automatic scheduled sends; only approved preview items send.
            print("PREVIEW MODE: skipping automatic status=scheduled sends")
            print("=" * 80)
            return

        # Preview off: process due rows with status=scheduled
        print("SENDING due Smart Messaging (status=scheduled)")
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
            phone = str(msg.get("phone") or "")
            content = str(msg.get("content") or "")
            msg_type = str(msg.get("type") or "")
            message_id = str(msg.get("message_id") or "")
            customer_name = str(msg.get("customer_name") or "Customer")

            if not (phone and content and message_id and msg_type):
                continue

            print(f"\n📤 Sending Message #{i}:")
            print(f"   ID: {message_id}")
            print(f"   Type: {msg_type}")
            print(f"   To: ***{str(phone)[-4:] if phone else ''}")
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

                if result.get("dry_run"):
                    sent_count += 1
                    smart_messaging.mark_message_dry_run(message_id)
                    print("   📋 Dry-run (would send)")
                elif result.get("success"):
                    sent_count += 1
                    smart_messaging.mark_message_sent(message_id)
                    print("   ✅ Sent successfully")

                    _sched = smart_messaging.scheduled_messages.get(message_id) or {}
                    _meta_raw = _sched.get("metadata")
                    _meta = _meta_raw if isinstance(_meta_raw, dict) else {}
                    _ph_raw = _sched.get("placeholders")
                    _ph = _ph_raw if isinstance(_ph_raw, dict) else {}
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
                        },
                    )
                    print("   💾 Saved to conversation history")
                else:
                    failed_count += 1
                    error_msg = result.get("error", "Unknown error")
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
    finally:
        release_job_lock("monitor_smart_messages")

async def send_appointment_reminders_job() -> None:
    try:
        print("📧 Running appointment reminders job...")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        result = await send_appointment_reminders(date=today)
        if result.get("success"):
            print("✅ Appointment reminders sent successfully")
        else:
            print(f"⚠️ Appointment reminders failed: {result.get('message')}")
    except Exception as e:
        print(f"❌ Error in appointment reminders job: {e}")

async def send_missed_yesterday_followups() -> None:
    try:
        print("📨 Running missed yesterday follow-ups job...")

        # Check if smart messaging is globally enabled
        from storage.persistent_storage import APP_SETTINGS_FILE

        settings_file = str(APP_SETTINGS_FILE)
        smart_messaging_enabled = True

        if os.path.exists(settings_file):
            try:
                with open(settings_file, encoding="utf-8") as f:
                    settings = json.load(f)
                smart_messaging_enabled = settings.get("smartMessaging", {}).get("enabled", True)
            except Exception as e:
                print(f"Error reading settings: {e}")

        if not smart_messaging_enabled:
            print("⏸️ Smart Messaging is DISABLED. Skipping missed yesterday follow-ups.")
            return

        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        # Use the new paused appointments API with yesterday as both start and end
        result = await get_paused_appointments_between_dates(
            start_date=yesterday, end_date=yesterday, service_id=None
        )

        paused_appointments = []
        if result.get("success"):
            response_data = result.get("data", {})
            if isinstance(response_data, dict):
                paused_appointments = response_data.get("appointments", [])
            elif isinstance(response_data, list):
                paused_appointments = response_data

        if paused_appointments:
            print(f"📋 Found {len(paused_appointments)} paused appointments from yesterday")

            for appointment in paused_appointments:
                try:
                    # New API response structure
                    customer_data = appointment.get("customer", {})
                    customer_phone = customer_data.get("phone")
                    customer_name = customer_data.get("name", "عميلنا العزيز")
                    language = "ar"  # Default language

                    if not customer_phone:
                        continue

                    placeholders = {
                        "customer_name": customer_name,
                        "phone_number": config.TRAINER_WHATSAPP_NUMBER or "+961 XX XXXXXX",
                    }

                    message_content = smart_messaging.get_message_content(
                        "missed_yesterday", language, placeholders
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
                        if result.get("dry_run"):
                            print(f"📋 [DRY-RUN] Would send missed yesterday to ***{str(customer_phone)[-4:] if customer_phone else ''}")
                        elif result.get("success"):
                            print(f"✅ Sent missed yesterday message to ***{str(customer_phone)[-4:] if customer_phone else ''}")

                            smart_messaging.mark_messages_sent_by_phone(customer_phone, "missed_yesterday")

                            await save_conversation_message_to_firestore(
                                user_id=customer_phone,
                                role="ai",
                                text=message_content,
                                conversation_id=None,
                                user_name=customer_name,
                                phone_number=customer_phone,
                                metadata={"source": "smart_message", "type": "missed_yesterday"},
                            )
                            print("💾 Saved missed yesterday message to conversation history")

                            log_report_event(
                                "scheduled_message_sent",
                                customer_phone,
                                "N/A",
                                {"type": "missed_yesterday", "customer_name": customer_name},
                            )
                        else:
                            print(
                                f"❌ Missed yesterday send failed for {customer_phone}: "
                                f"{result.get('error', 'unknown')}"
                            )
                except Exception as e:
                    print(f"❌ Error sending missed yesterday message: {e}")
        else:
            print("ℹ️ No paused appointments from yesterday")
    except Exception as e:
        print(f"❌ Error in missed yesterday follow-ups job: {e}")

async def send_missed_this_month_followups() -> None:
    try:
        print("📨 Running missed this month follow-ups job...")

        # Check if smart messaging is globally enabled
        from storage.persistent_storage import APP_SETTINGS_FILE

        settings_file = str(APP_SETTINGS_FILE)
        smart_messaging_enabled = True

        if os.path.exists(settings_file):
            try:
                with open(settings_file, encoding="utf-8") as f:
                    settings = json.load(f)
                smart_messaging_enabled = settings.get("smartMessaging", {}).get("enabled", True)
            except Exception as e:
                print(f"Error reading settings: {e}")

        if not smart_messaging_enabled:
            print("⏸️ Smart Messaging is DISABLED. Skipping missed this month follow-ups.")
            return

        first_day_of_month = datetime.datetime.now().replace(day=1).strftime("%Y-%m-%d")
        result = await get_missed_appointments(date=first_day_of_month)

        if result.get("success") and result.get("data"):
            missed_appointments = result["data"]
            print(f"📋 Found {len(missed_appointments)} missed appointments this month")

            customers_contacted = set()

            for appointment in missed_appointments:
                try:
                    customer_phone = appointment.get("customer_phone", appointment.get("phone"))

                    if not customer_phone or customer_phone in customers_contacted:
                        continue

                    customers_contacted.add(customer_phone)

                    customer_name = appointment.get("customer_name", appointment.get("name", "عميلنا العزيز"))
                    language = appointment.get("language", "ar")

                    placeholders = {
                        "customer_name": customer_name,
                        "phone_number": config.TRAINER_WHATSAPP_NUMBER or "+961 XX XXXXXX",
                    }

                    message_content = smart_messaging.get_message_content(
                        "sent_for_pause", language, placeholders
                    )

                    if message_content:
                        adapter = WhatsAppFactory.get_adapter()
                        result = await deliver_scheduled_smart_whatsapp(
                            adapter,
                            phone=customer_phone,
                            template_id="sent_for_pause",
                            language=language,
                            placeholders=placeholders,
                            rendered_text=message_content,
                        )
                        if result.get("dry_run"):
                            print(f"📋 [DRY-RUN] Would send missed this month to ***{str(customer_phone)[-4:] if customer_phone else ''}")
                        elif result.get("success"):
                            print(f"✅ Sent missed this month message to ***{str(customer_phone)[-4:] if customer_phone else ''}")

                            smart_messaging.mark_messages_sent_by_phone(customer_phone, "sent_for_pause")

                            await save_conversation_message_to_firestore(
                                user_id=customer_phone,
                                role="ai",
                                text=message_content,
                                conversation_id=None,
                                user_name=customer_name,
                                phone_number=customer_phone,
                                metadata={"source": "smart_message", "type": "sent_for_pause"},
                            )
                            print("💾 Saved missed this month message to conversation history")

                            log_report_event(
                                "scheduled_message_sent",
                                customer_phone,
                                "N/A",
                                {"type": "sent_for_pause", "customer_name": customer_name},
                            )
                        else:
                            print(
                                f"❌ Missed this month send failed for {customer_phone}: "
                                f"{result.get('error', 'unknown')}"
                            )
                except Exception as e:
                    print(f"❌ Error sending missed this month message: {e}")
        else:
            print("ℹ️ No missed appointments this month")
    except Exception as e:
        print(f"❌ Error in missed this month follow-ups job: {e}")
