# Smart Messaging Service
# Implements requirement #11 from project specifications

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import json
import os
from pathlib import Path

from services.message_logs_service import message_logs_service
from services.smart_messaging_catalog import normalize_template_id

_BASE_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _BASE_DIR / "data"

class SmartMessagingService:
    """
    Handles automated messaging:
    - 24h appointment reminders
    - Same-day check-ins
    - Post-session feedback
    - No-show follow-ups
    - 1-month follow-ups
    """
    
    SENT_MESSAGES_FILE = str(_DATA_DIR / "sent_smart_messages.json")

    def __init__(self):
        self.templates_file = str(_DATA_DIR / "message_templates.json")
        self.settings_file = str(_DATA_DIR / "app_settings.json")
        self.mapping_file = str(_DATA_DIR / "service_template_mapping.json")
        self.message_templates = self._load_templates()
        self.scheduled_messages = {}
        self.sent_messages_log = []
        self._load_sent_messages()
        
    # ------------------------------------------------------------------
    # Persistence helpers — keep sent messages across server restarts
    # ------------------------------------------------------------------

    def _load_sent_messages(self):
        """Load previously sent messages from disk into scheduled_messages dict."""
        if not os.path.exists(self.SENT_MESSAGES_FILE):
            return
        try:
            with open(self.SENT_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            loaded = 0
            for message_id, entry in entries.items():
                # Convert ISO strings back to datetime objects
                for key in ('send_at', 'sent_at', 'created_at', 'last_attempt'):
                    if entry.get(key):
                        try:
                            entry[key] = datetime.fromisoformat(entry[key])
                        except (ValueError, TypeError):
                            pass
                self.scheduled_messages[message_id] = entry
                loaded += 1
            print(f"✅ Loaded {loaded} sent messages from {self.SENT_MESSAGES_FILE}")
        except Exception as e:
            print(f"⚠️ Could not load sent messages: {e}")

    def _persist_sent_messages(self):
        """Save all sent messages to disk so they survive restarts."""
        try:
            entries = {}
            for message_id, msg in self.scheduled_messages.items():
                if msg.get("status") not in ("sent", "would_send"):
                    continue
                # Shallow copy and serialise datetimes
                entry = dict(msg)
                for key in ('send_at', 'sent_at', 'created_at', 'last_attempt'):
                    if isinstance(entry.get(key), datetime):
                        entry[key] = entry[key].isoformat()
                entries[message_id] = entry
            os.makedirs(os.path.dirname(self.SENT_MESSAGES_FILE), exist_ok=True)
            with open(self.SENT_MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Could not persist sent messages: {e}")

    def _load_templates(self) -> Dict:
        """Load message templates from JSON file or use defaults"""
        template_file = self.templates_file
        
        if os.path.exists(template_file):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    templates_data = json.load(f)
                
                # Extract only the language templates (ar, en, fr) from each template
                templates = {}
                for template_id, template_data in templates_data.items():
                    canonical_id = normalize_template_id(template_id)
                    if canonical_id in {"same_day_checkin", "no_show_followup"}:
                        # Deprecated templates stay editable in file, but are not loaded into runtime.
                        continue

                    current = templates.get(canonical_id, {})
                    normalized = {
                        'ar': template_data.get('ar', ''),
                        'en': template_data.get('en', ''),
                        'fr': template_data.get('fr', '')
                    }
                    # Preserve whichever variant has richer text per language.
                    templates[canonical_id] = {
                        "ar": normalized["ar"] or current.get("ar", ""),
                        "en": normalized["en"] or current.get("en", ""),
                        "fr": normalized["fr"] or current.get("fr", ""),
                    }
                
                print(f"✅ Loaded {len(templates)} message templates from {template_file}")
                return templates
            except Exception as e:
                print(f"❌ Error loading templates from file: {e}, using defaults")
        else:
            print(f"⚠️ Template file not found: {template_file}, using default templates")
        
        # Return default templates if file not found or error
        return {
            "reminder_24h": {
                "ar": """🔔 تذكير بموعدك

مرحباً {{customer_name}}! 
نذكرك بموعدك غداً في مركز لينا ليزر:

📅 التاريخ: {{appointment_date}}
⏰ ��لوقت: {{appointment_time}}
📍 الفرع: {{branch_name}}
💆 الخدمة: {{service_name}}

للتأكيد: أرسل "نعم"
لإعادة الجدولة: أرسل "تأجيل"
للإلغاء: أرسل "إلغاء"

نتطلع لرؤيتك! 💜""",

                "en": """🔔 Appointment Reminder

Hi {{customer_name}}!
This is a reminder of your appointment tomorrow at Lina's Laser Center:

📅 Date: {{appointment_date}}
⏰ Time: {{appointment_time}}
📍 Branch: {{branch_name}}
💆 Service: {{service_name}}

To confirm: Reply "Yes"
To reschedule: Reply "Postpone"
To cancel: Reply "Cancel"

Looking forward to seeing you! 💜""",

                "fr": """🔔 Rappel de Rendez-vous

Bonjour {{customer_name}}!
Ceci est un rappel de votre rendez-vous demain au Centre Laser Lina:

📅 Date: {{appointment_date}}
⏰ Heure: {{appointment_time}}
📍 Branche: {{branch_name}}
💆 Service: {{service_name}}

Pour confirmer: Répondez "Oui"
Pour reporter: Répondez "Reporter"
Pour annuler: Répondez "Annuler"

Au plaisir de vous voir! 💜"""
            },
            
            "same_day_checkin": {
                "ar": """🌟 يوم موعدك!

صباح الخير {{customer_name}}!
موعدك اليوم الساعة {{appointment_time}}.

ن��ائح مهمة:
✅ احضر قبل الموعد بـ 10 دقائق
✅ تجنب الكافيين قبل الجلسة
✅ ارتدي ملابس مريحة

هل تحتاج لأي مساعدة؟ نحن هنا! 😊""",

                "en": """🌟 It's Your Appointment Day!

Good morning {{customer_name}}!
Your appointment is today at {{appointment_time}}.

Important tips:
✅ Arrive 10 minutes early
✅ Avoid caffeine before session
✅ Wear comfortable clothes

Need any help? We're here! 😊""",

                "fr": """🌟 C'est le Jour de Votre Rendez-vous!

Bonjour {{customer_name}}!
Votre rendez-vous est aujourd'hui à {{appointment_time}}.

Conseils importants:
✅ Arrivez 10 minutes en avance
✅ Évitez la caféine avant la séance
✅ Portez des vêtements confortables

Besoin d'aide? Nous sommes là! 😊"""
            },
            
            "post_session_feedback": {
                "ar": """💜 شكراً لزيارتك!

{{customer_name}} العزيز/ة،
نأمل أن تكون راضياً عن جلستك اليوم.

كيف كانت تجربتك؟
⭐⭐⭐⭐⭐ ممتازة
⭐⭐⭐⭐ جيدة جداً
⭐⭐⭐ جيدة
⭐⭐ مقبولة
⭐ تحتاج تحسين

أرسل رقم النجوم لتقييمك!
ملاحظاتك تهمنا 🙏""",

                "en": """💜 Thank You for Your Visit!

Dear {{customer_name}},
We hope you're satisfied with today's session.

How was your experience?
⭐⭐⭐⭐⭐ Excellent
⭐⭐⭐⭐ Very Good
⭐⭐⭐ Good
⭐⭐ Fair
⭐ Needs Improvement

Send the number of stars for your rating!
Your feedback matters 🙏""",

                "fr": """💜 Merci de Votre Visite!

Cher(e) {{customer_name}},
Nous espérons que vous êtes satisfait de votre séance.

Comment était votre expérience?
⭐⭐⭐⭐⭐ Excellente
⭐⭐⭐⭐ Très Bien
⭐⭐⭐ Bien
⭐⭐ Passable
⭐ À Améliorer

Envoyez le nombre d'étoiles!
Vos commentaires comptent 🙏"""
            },
            
            "no_show_followup": {
                "ar": """😔 افتقدناك اليوم

{{customer_name}} العزيز/ة،
لاحظنا أنك لم تحضر موعدك اليوم.

نتمنى أن يكون كل شيء على ما يرام!

لإعادة جدولة موعدك:
📱 اتصل: {{phone_number}}
💬 أو أرسل "موعد جديد"

دمت بخير 🌸""",

                "en": """😔 We Missed You Today

Dear {{customer_name}},
We noticed you missed your appointment today.

We hope everything is okay!

To reschedule:
📱 Call: {{phone_number}}
💬 Or reply "New appointment"

Take care 🌸""",

                "fr": """😔 Vous Nous Avez Manqué

Cher(e) {{customer_name}},
Nous avons remarqué votre absence aujourd'hui.

Nous espérons que tout va bien!

Pour reprogrammer:
📱 Appelez: {{phone_number}}
💬 Ou répondez "Nouveau rendez-vous"

Prenez soin de vous 🌸"""
            },
            
            "one_month_followup": {
                "ar": """🌟 كيف حالك؟

{{customer_name}} العزيز/ة،
مضى شهر على آخر جلسة لك!

كيف النتائج؟ 
نود أن نطمئن عليك ونذكرك:

✨ قد تحتاج لجلسة متابعة
✨ لدينا عروض خاصة هذا الشهر
✨ استشارة مجانية متاحة

للحجز: أرسل "حجز"
رعايتك أولويتنا 💜""",

                "en": """🌟 How Are You?

Dear {{customer_name}},
It's been a month since your last session!

How are the results?
We'd like to check on you and remind you:

✨ You might need a follow-up session
✨ We have special offers this month
✨ Free consultation available

To book: Reply "Book"
Your care is our priority 💜""",

                "fr": """🌟 Comment Allez-Vous?

Cher(e) {{customer_name}},
Cela fait un mois depuis votre dernière séance!

Comment sont les résultats?
Nous aimerions prendre de vos nouvelles:

��� Vous pourriez avoir besoin d'un suivi
✨ Offres spéciales ce mois
✨ Consultation gratuite disponible

Pour réserver: Répondez "Réserver"
Votre bien-être est notre priorité 💜"""
            },
            
            "missed_yesterday": {
                "ar": """💙 نتمنى أن تكون بخير

{{customer_name}} العزيز/ة،
لاحظنا أنك لم تتمكن من الحضور بالأمس.

نأمل أن يكون كل شيء على ما يرام! 🌸

هل ترغب في إعادة جدولة موعدك؟
📱 اتصل بنا: {{phone_number}}
💬 أو أرسل "موعد جديد"

نحن هنا لخدمتك دائماً 💜""",

                "en": """💙 Hope You're Well

Dear {{customer_name}},
We noticed you couldn't make it yesterday.

We hope everything is okay! 🌸

Would you like to reschedule?
📱 Call us: {{phone_number}}
💬 Or reply "New appointment"

We're always here for you 💜""",

                "fr": """💙 Nous Espérons Que Vous Allez Bien

Cher(e) {{customer_name}},
Nous avons remarqué votre absence hier.

Nous espérons que tout va bien! 🌸

Souhaitez-vous reprogrammer?
📱 Appelez-nous: {{phone_number}}
💬 Ou répondez "Nouveau rendez-vous"

Nous sommes toujours là pour vous 💜"""
            },
            
            "missed_this_month": {
                "ar": """🌺 نفتقدك في مركز لينا ليزر

{{customer_name}} العزيز/ة،
لم نراك هذا الشهر ونفتقد وجودك معنا!

نود أن نطمئن عليك ونذكرك:
✨ جلساتك المنتظمة مهمة للحصول على أفضل النتائج
✨ لدينا مواعيد متاحة هذا الأسبوع
✨ فريقنا جاهز لخدمتك

للحجز: أرسل "حجز"
أو اتصل: {{phone_number}}

نتطلع لرؤيتك قريباً 💜""",

                "en": """🌺 We Miss You at Lina's Laser

Dear {{customer_name}},
We haven't seen you this month and we miss you!

We'd like to remind you:
✨ Regular sessions are important for best results
✨ We have appointments available this week
✨ Our team is ready to serve you

To book: Reply "Book"
Or call: {{phone_number}}

Looking forward to seeing you soon 💜""",

                "fr": """🌺 Vous Nous Manquez Chez Lina's Laser

Cher(e) {{customer_name}},
Nous ne vous avons pas vu ce mois-ci!

Nous aimerions vous rappeler:
✨ Les séances régulières sont importantes
✨ Nous avons des disponibilités cette semaine
✨ Notre équipe est prête à vous servir

Pour réserver: Répondez "Réserver"
Ou appelez: {{phone_number}}

Au plaisir de vous revoir bientôt 💜"""
            },
            
            "attended_yesterday": {
                "ar": """💜 شكراً لزيارتك!

{{customer_name}} العزيز/ة،
شكراً لحضورك بالأمس! 🌟

نأمل أن تكون راضياً عن الخدمة.

نصائح مهمة بعد الجلسة:
✅ تجنب التعرض للشمس لمدة 48 ساعة
✅ استخدم واقي الشمس SPF 50+
✅ رطب البشرة جيداً
✅ تجنب الماء الساخن لمدة 24 ساعة

موعدك القادم: {{next_appointment_date}}

أي استفسار؟ نحن هنا! 💬
{{phone_number}}""",

                "en": """💜 Thank You for Your Visit!

Dear {{customer_name}},
Thank you for coming yesterday! 🌟

We hope you're satisfied with the service.

Important post-session tips:
✅ Avoid sun exposure for 48 hours
✅ Use SPF 50+ sunscreen
✅ Keep skin well moisturized
✅ Avoid hot water for 24 hours

Your next appointment: {{next_appointment_date}}

Any questions? We're here! 💬
{{phone_number}}""",

                "fr": """💜 Merci de Votre Visite!

Cher(e) {{customer_name}},
Merci d'être venu(e) hier! 🌟

Nous espérons que vous êtes satisfait(e).

Conseils importants après la séance:
✅ Évitez le soleil pendant 48 heures
✅ Utilisez SPF 50+ crème solaire
✅ Hydratez bien la peau
✅ Évitez l'eau chaude pendant 24 heures

Votre prochain rendez-vous: {{next_appointment_date}}

Des questions? Nous sommes là! 💬
{{phone_number}}"""
            }
        }

    def _resolve_template_key(self, template_id: str) -> str:
        """
        Resolve canonical template IDs with backwards-compatible fallbacks.
        """
        canonical = normalize_template_id(template_id)
        if canonical in self.message_templates:
            return canonical

        legacy_fallbacks = {
            "twenty_day_followup": "one_month_followup",
            "missed_paused_appointment": "missed_this_month",
        }
        fallback = legacy_fallbacks.get(canonical)
        if fallback and fallback in self.message_templates:
            return fallback

        return canonical
    
    def schedule_message(
        self,
        customer_phone: str,
        message_type: str,
        send_at: datetime,
        placeholders: Dict[str, str],
        language: str = "ar",
        service_id: int = None,
        service_name: str = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Schedule a message to be sent at specific time with service context"""

        canonical_type = normalize_template_id(message_type)
        message_id = f"{canonical_type}_{customer_phone}_{send_at.timestamp()}"

        # Check service-template mapping
        if service_id and not self._is_template_enabled_for_service(service_id, canonical_type):
            print(f"Template {canonical_type} not enabled for service {service_id}, skipping")
            return None

        self.scheduled_messages[message_id] = {
            "customer_phone": customer_phone,
            "message_type": canonical_type,
            "send_at": send_at,
            "placeholders": placeholders,
            "language": language,
            "service_id": service_id,
            "service_name": service_name or "Unknown Service",
            "status": "scheduled",
            "created_at": datetime.now(),
            "metadata": metadata or {},
        }

        # If preview mode is enabled, also add to preview queue
        if self._is_preview_mode_enabled():
            self._add_to_preview_queue(message_id)

        return message_id

    def _is_smart_messaging_enabled(self) -> bool:
        """Check if smart messaging is globally enabled"""
        try:
            settings_file = self.settings_file
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                return settings.get('smartMessaging', {}).get('enabled', True)
        except Exception as e:
            print(f"Error checking smart messaging status: {e}")
        return True

    def _is_preview_mode_enabled(self) -> bool:
        """Check if preview before send is enabled"""
        try:
            settings_file = self.settings_file
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                return settings.get('smartMessaging', {}).get('previewBeforeSend', True)
        except Exception as e:
            print(f"Error checking preview mode: {e}")
        return True

    def _is_template_enabled_for_service(self, service_id: int, template_id: str) -> bool:
        """Check if template is enabled for a specific service"""
        try:
            template_id = normalize_template_id(template_id)
            mapping_file = self.mapping_file
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
                service_key = str(service_id)
                service_mapping = mappings.get('service_mappings', {}).get(service_key, {})
                templates = service_mapping.get('templates', {})
                return templates.get(template_id, True)
        except Exception as e:
            print(f"Error checking service-template mapping: {e}")
        return True

    def _add_to_preview_queue(self, message_id: str):
        """Add scheduled message to preview queue"""
        try:
            from services.message_preview_service import message_preview_service

            msg_data = self.scheduled_messages.get(message_id)
            if msg_data:
                # Update status to pending_approval
                self.scheduled_messages[message_id]['status'] = 'pending_approval'

                # Add to preview service
                message_preview_service.add_to_preview_queue({
                    'message_id': message_id,
                    'customer_phone': msg_data.get('customer_phone'),
                    'customer_name': msg_data.get('placeholders', {}).get('customer_name', 'Unknown'),
                    'template_id': msg_data.get('message_type'),
                    'language': msg_data.get('language', 'ar'),
                    'placeholders': msg_data.get('placeholders', {}),
                    'service_id': msg_data.get('service_id'),
                    'service_name': msg_data.get('service_name', 'Unknown Service'),
                    'scheduled_send_time': msg_data.get('send_at')
                })
        except Exception as e:
            print(f"Error adding to preview queue: {e}")
    
    def get_message_content(
        self,
        message_type: str,
        language: str,
        placeholders: Dict[str, str]
    ) -> str:
        """Get message content with placeholders replaced"""

        template_key = self._resolve_template_key(message_type)
        if template_key not in self.message_templates:
            return None

        template = self.message_templates[template_key].get(
            language,
            self.message_templates[template_key].get("en", ""),
        )
        
        # Replace placeholders (templates use single braces: {customer_name})
        message = template
        for key, value in placeholders.items():
            placeholder = f"{{{key}}}"
            message = message.replace(placeholder, str(value))
        
        return message
    
    async def process_scheduled_messages(self) -> List[Dict]:
        """
        Find all due scheduled messages and mark them as 'sending'.
        The caller is responsible for calling mark_message_sent() or
        mark_message_failed() after the actual send attempt.
        """

        # Don't send messages if smart messaging is disabled
        if not self._is_smart_messaging_enabled():
            print("Smart messaging is disabled, skipping message sending")
            return []

        current_time = datetime.now()
        messages_to_send = []

        for message_id, message_data in list(self.scheduled_messages.items()):
            if message_data["status"] == "scheduled" and message_data["send_at"] <= current_time:
                # Get message content
                content = self.get_message_content(
                    message_data["message_type"],
                    message_data["language"],
                    message_data["placeholders"]
                )

                if content:
                    canonical_type = normalize_template_id(message_data["message_type"])
                    messages_to_send.append({
                        "phone": message_data["customer_phone"],
                        "content": content,
                        "type": canonical_type,
                        "message_id": message_id,
                        "customer_name": message_data.get("placeholders", {}).get("customer_name", "Customer")
                    })

                    # Mark as 'sending' to prevent duplicate processing,
                    # but do NOT mark 'sent' yet — caller does that after
                    # confirming the WhatsApp send succeeded.
                    self.scheduled_messages[message_id]["status"] = "sending"

        return messages_to_send

    def mark_message_dry_run(self, message_id: str):
        """Mark message as dry-run (would send) – used when ENABLE_SENDING=false or local sandbox."""
        if message_id in self.scheduled_messages:
            self.scheduled_messages[message_id]["status"] = "would_send"
            self.scheduled_messages[message_id]["sent_at"] = datetime.now()
            msg_data = self.scheduled_messages[message_id]
            canonical_type = normalize_template_id(msg_data.get("message_type", ""))
            content_preview = self.get_message_content(
                canonical_type,
                msg_data.get("language", "ar"),
                msg_data.get("placeholders") or {}
            ) or ""
            self.sent_messages_log.append({
                "message_id": message_id,
                "phone": msg_data.get("customer_phone", ""),
                "type": canonical_type,
                "sent_at": datetime.now(),
                "content": "(dry-run) " + (content_preview[:80] + "..." if len(content_preview) > 80 else content_preview)
            })
            self._persist_sent_messages()
            print(f"   📋 Marked {message_id} as would_send (dry-run)")

    def mark_message_sent(self, message_id: str):
        """Mark a single message as successfully sent (called after WhatsApp confirms)."""
        if message_id in self.scheduled_messages:
            self.scheduled_messages[message_id]["status"] = "sent"
            self.scheduled_messages[message_id]["sent_at"] = datetime.now()

            msg_data = self.scheduled_messages[message_id]
            metadata = msg_data.get("metadata", {}) if isinstance(msg_data.get("metadata"), dict) else {}
            canonical_type = normalize_template_id(msg_data["message_type"])
            content = self.get_message_content(
                canonical_type,
                msg_data["language"],
                msg_data["placeholders"]
            ) or ""
            self.sent_messages_log.append({
                "message_id": message_id,
                "phone": msg_data["customer_phone"],
                "type": canonical_type,
                "sent_at": datetime.now(),
                "content": content[:100] + "..."
            })

            reference_date = (
                metadata.get("reference_date")
                or msg_data.get("placeholders", {}).get("reference_date")
                or msg_data.get("placeholders", {}).get("appointment_date")
            )
            appointment_id = metadata.get("appointment_id") or msg_data.get("placeholders", {}).get("appointment_id")
            customer_id = metadata.get("customer_id") or msg_data.get("customer_phone")
            campaign_id = metadata.get("campaign_id")

            try:
                if not message_logs_service.was_message_sent(
                    customer_id=customer_id,
                    template_type=canonical_type,
                    reference_date=reference_date,
                    appointment_id=appointment_id,
                    campaign_id=campaign_id,
                ):
                    message_logs_service.log_message(
                        customer_id=customer_id,
                        template_type=canonical_type,
                        appointment_id=appointment_id,
                        campaign_id=campaign_id,
                        reference_date=reference_date,
                        extra={
                            "phone": msg_data.get("customer_phone"),
                            "service_name": msg_data.get("service_name"),
                            "source": metadata.get("source", "scheduler"),
                        },
                    )
            except Exception as log_exc:
                print(f"⚠️ Failed to write message log for {message_id}: {log_exc}")

            self._persist_sent_messages()

    def mark_message_failed(self, message_id: str, error: str = ""):
        """Revert a message back to 'scheduled' so it can be retried next cycle."""
        if message_id in self.scheduled_messages:
            msg = self.scheduled_messages[message_id]
            msg["status"] = "scheduled"
            msg["last_error"] = error
            msg["last_attempt"] = datetime.now()
            print(f"   [RETRY] {message_id} reverted to 'scheduled' — {error}")
    
    def schedule_appointment_reminders(
        self,
        appointment_date: datetime,
        customer_data: Dict
    ) -> int:
        """Schedule all reminders for an appointment

        Returns:
            int: Number of messages scheduled
        """

        customer_phone = customer_data.get("phone")
        customer_name = customer_data.get("name", "عميلنا العزيز")
        language = customer_data.get("language", "ar")
        service_id = customer_data.get("service_id")
        service_name = customer_data.get("service", "جلسة ليزر")

        placeholders = {
            "customer_name": customer_name,
            "appointment_date": appointment_date.strftime("%Y-%m-%d"),
            "appointment_time": appointment_date.strftime("%H:%M"),
            "branch_name": customer_data.get("branch", "الفرع الرئيسي"),
            "service_name": service_name,
            "phone_number": "01234567"  # Support phone
        }

        messages_scheduled = 0
        now = datetime.now()

        print(f"\n📋 Scheduling reminders for {customer_name} ({customer_phone})")
        print(f"   Appointment: {appointment_date}")
        print(f"   Current time: {now}")

        # Schedule 24h reminder
        reminder_24h_time = appointment_date - timedelta(hours=24)
        if reminder_24h_time > now:
            result = self.schedule_message(
                customer_phone,
                "reminder_24h",
                reminder_24h_time,
                placeholders,
                language,
                service_id=service_id,
                service_name=service_name
            )
            if result:
                messages_scheduled += 1
                print(f"   ✅ reminder_24h scheduled for {reminder_24h_time}")
            else:
                print(f"   ❌ reminder_24h FAILED (returned None)")
        else:
            print(f"   ⏭️ reminder_24h SKIPPED (time {reminder_24h_time} is in the past)")

        # NOTE: same_day_checkin/no_show_followup are deprecated.
        # NOTE: post_session_feedback is handled by fixed-time daily jobs.

        # Schedule 20-day follow-up (legacy one_month_followup replacement)
        followup_time = appointment_date + timedelta(days=20)
        result = self.schedule_message(
            customer_phone,
            "twenty_day_followup",
            followup_time,
            placeholders,
            language,
            service_id=service_id,
            service_name=service_name
        )
        if result:
            messages_scheduled += 1
            print(f"   ✅ twenty_day_followup scheduled for {followup_time}")
        else:
            print(f"   ❌ twenty_day_followup FAILED (returned None)")

        # NOTE: attended_yesterday is NOT scheduled here anymore
        # It's only scheduled in Phase 2 of populate_scheduled_messages_from_appointments()
        # which fetches DONE appointments from yesterday via the API
        # This ensures we only send thank-you messages to customers who actually attended

        print(f"   📊 Total scheduled: {messages_scheduled}\n")

        return messages_scheduled
    
    def handle_no_show(self, customer_data: Dict):
        """Handle no-show scenario"""
        
        customer_phone = customer_data.get("phone")
        customer_name = customer_data.get("name", "عميلنا العزيز")
        language = customer_data.get("language", "ar")
        
        placeholders = {
            "customer_name": customer_name,
            "phone_number": "01234567"  # Support phone
        }
        
        # Send no-show follow-up immediately
        self.schedule_message(
            customer_phone,
            "no_show_followup",
            datetime.now(),
            placeholders,
            language
        )
    
    def get_scheduled_messages_summary(self) -> Dict:
        """Get summary of scheduled messages"""
        
        summary = {
            "total": len(self.scheduled_messages),
            "scheduled": 0,
            "sent": 0,
            "would_send": 0,
            "by_type": {},
            "next_message": None
        }
        
        next_send_time = None
        
        for message_data in self.scheduled_messages.values():
            if message_data["status"] == "scheduled":
                summary["scheduled"] += 1
                
                # Find next message to be sent
                if not next_send_time or message_data["send_at"] < next_send_time:
                    next_send_time = message_data["send_at"]
                    summary["next_message"] = {
                        "type": message_data["message_type"],
                        "send_at": message_data["send_at"].isoformat(),
                        "phone": message_data["customer_phone"]
                    }
            elif message_data["status"] == "would_send":
                summary["would_send"] += 1
            else:
                summary["sent"] += 1
            
            # Count by type
            msg_type = message_data["message_type"]
            summary["by_type"][msg_type] = summary["by_type"].get(msg_type, 0) + 1
        
        return summary
    
    def mark_messages_sent_by_phone(self, customer_phone: str, message_type: str) -> int:
        """
        Mark all scheduled messages matching customer_phone + message_type as sent.
        Called by cron send jobs after successfully sending a message.

        Returns:
            int: Number of messages marked as sent
        """
        updated = 0
        now = datetime.now()

        # Normalize the input phone for comparison
        phone_clean = str(customer_phone).replace("+", "").replace(" ", "").replace("-", "")

        normalized_type = normalize_template_id(message_type)

        for message_id, msg_data in self.scheduled_messages.items():
            if normalize_template_id(msg_data.get("message_type")) != normalized_type:
                continue
            if msg_data.get("status") not in ("scheduled", "pending_approval"):
                continue

            # Normalize stored phone for comparison
            stored_phone = str(msg_data.get("customer_phone", "")).replace("+", "").replace(" ", "").replace("-", "")

            if stored_phone == phone_clean or stored_phone.endswith(phone_clean) or phone_clean.endswith(stored_phone):
                msg_data["status"] = "sent"
                msg_data["sent_at"] = now
                updated += 1
                metadata = msg_data.get("metadata", {}) if isinstance(msg_data.get("metadata"), dict) else {}
                reference_date = (
                    metadata.get("reference_date")
                    or msg_data.get("placeholders", {}).get("reference_date")
                    or msg_data.get("placeholders", {}).get("appointment_date")
                )
                appointment_id = metadata.get("appointment_id")
                customer_id = metadata.get("customer_id") or customer_phone
                campaign_id = metadata.get("campaign_id")

                try:
                    if not message_logs_service.was_message_sent(
                        customer_id=customer_id,
                        template_type=normalized_type,
                        reference_date=reference_date,
                        appointment_id=appointment_id,
                        campaign_id=campaign_id,
                    ):
                        message_logs_service.log_message(
                            customer_id=customer_id,
                            template_type=normalized_type,
                            appointment_id=appointment_id,
                            campaign_id=campaign_id,
                            reference_date=reference_date,
                            extra={
                                "phone": msg_data.get("customer_phone"),
                                "service_name": msg_data.get("service_name"),
                                "source": metadata.get("source", "sync_mark_sent"),
                            },
                        )
                except Exception as log_exc:
                    print(f"⚠️ Failed to write message log while syncing {message_id}: {log_exc}")
                print(f"   [SYNC] Marked {message_id} as sent in scheduled_messages dict")

        if updated == 0:
            print(f"   [SYNC] No matching scheduled message found for {customer_phone} / {message_type}")
        else:
            self._persist_sent_messages()

        return updated

    def clear_daily_messages(self) -> Dict:
        """
        Clear stale messages from previous days.
        Called at the start of each day to refresh the dashboard.

        Rules:
        - Remove all messages where send_at date < today for MOST categories
        - KEEP all twenty_day_followup and missed_paused_appointment messages (they show
          cumulative data for the entire month)
        - KEEP messages sent today (so user can see what was sent)
        - Persist sent messages before clearing so history is not lost
        """
        preserved_types = {"twenty_day_followup", "missed_paused_appointment"}
        today = datetime.now().date()

        # Persist sent messages first so they survive the cleanup
        self._persist_sent_messages()

        cleared = 0
        kept = 0
        new_scheduled = {}

        for message_id, msg_data in self.scheduled_messages.items():
            msg_type = msg_data.get("message_type", "")

            # Always keep long-horizon follow-up and campaign messages
            if msg_type in preserved_types:
                new_scheduled[message_id] = msg_data
                kept += 1
                continue

            # Keep messages that were sent or dry-run today (so user can see today's activity)
            status = msg_data.get("status", "")
            sent_at = msg_data.get("sent_at")
            if status in ("sent", "would_send") and sent_at:
                sent_date = sent_at.date() if isinstance(sent_at, datetime) else None
                if sent_date and sent_date >= today:
                    new_scheduled[message_id] = msg_data
                    kept += 1
                    continue

            # Keep messages whose send_at is today or in the future
            send_at = msg_data.get("send_at")
            if send_at:
                send_date = send_at.date() if isinstance(send_at, datetime) else None
                if send_date and send_date >= today:
                    new_scheduled[message_id] = msg_data
                    kept += 1
                    continue

            # Otherwise, discard (stale message from a previous day)
            cleared += 1

        self.scheduled_messages = new_scheduled

        print(f"🧹 Daily cleanup: cleared {cleared} stale messages, kept {kept}")
        return {"cleared": cleared, "kept": kept}

    def cancel_scheduled_messages(self, customer_phone: str, message_type: Optional[str] = None):
        """Cancel scheduled messages for a customer"""
        
        cancelled = []
        for message_id, message_data in list(self.scheduled_messages.items()):
            if message_data["customer_phone"] == customer_phone and message_data["status"] == "scheduled":
                if not message_type or message_data["message_type"] == message_type:
                    self.scheduled_messages[message_id]["status"] = "cancelled"
                    cancelled.append(message_id)
        
        return cancelled


# Mapping of message types to friendly names
message_type_names = {
    "reminder_24h": "24-Hour Appointment Reminder",
    "post_session_feedback": "Post-Session Feedback",
    "twenty_day_followup": "20-Day Follow-up",
    "missed_yesterday": "Missed Yesterday Follow-up",
    "missed_paused_appointment": "Missed Paused Appointment Campaign",
    "attended_yesterday": "Thank You - Attended Yesterday"
}


async def get_sent_smart_messages_from_firestore(
    message_type: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
    limit: int = 200
) -> List[Dict]:
    """
    Query Firestore for sent smart messages by scanning conversations.

    Args:
        message_type: Filter by message type (e.g., "twenty_day_followup")
        start_date: Filter messages sent after this date
        end_date: Filter messages sent before this date
        limit: Maximum number of messages to return

    Returns:
        List of sent message dicts with customer info
    """
    from utils.utils import get_firestore_db

    db = get_firestore_db()
    if not db:
        return []

    app_id = "linas-ai-bot-backend"
    users_collection = db.collection("artifacts").document(app_id).collection("users")

    sent_messages = []

    try:
        # Get all users
        users_docs = await asyncio.to_thread(lambda: list(users_collection.stream()))

        for user_doc in users_docs:
            try:
                user_id = user_doc.id
                user_data = user_doc.to_dict() or {}

                conversations_collection = users_collection.document(user_id).collection("conversations")
                conversations_docs = await asyncio.to_thread(lambda uid=user_id: list(
                    users_collection.document(uid).collection("conversations").stream()
                ))

                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict() or {}
                    messages = conv_data.get("messages", [])
                    customer_info = conv_data.get("customer_info", {})

                    for msg in messages:
                        metadata = msg.get("metadata", {})

                        # Filter by source - only smart messages
                        if metadata.get("source") != "smart_message":
                            continue

                        # Filter by type if specified
                        if message_type and metadata.get("type") != message_type:
                            continue

                        # Only AI messages (sent by bot)
                        if msg.get("role") != "ai":
                            continue

                        # Parse timestamp
                        timestamp = msg.get("timestamp")
                        msg_datetime = None

                        if hasattr(timestamp, 'isoformat'):
                            # Firestore timestamp object
                            msg_datetime = timestamp
                        elif isinstance(timestamp, str):
                            try:
                                msg_datetime = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            except:
                                continue
                        else:
                            continue

                        # Apply date range filter
                        if start_date:
                            # Handle timezone-aware vs naive datetime comparison
                            start_compare = start_date
                            msg_compare = msg_datetime
                            if hasattr(msg_datetime, 'tzinfo') and msg_datetime.tzinfo is not None:
                                if start_date.tzinfo is None:
                                    msg_compare = msg_datetime.replace(tzinfo=None)
                            if msg_compare < start_compare:
                                continue

                        if end_date:
                            end_compare = end_date
                            msg_compare = msg_datetime
                            if hasattr(msg_datetime, 'tzinfo') and msg_datetime.tzinfo is not None:
                                if end_date.tzinfo is None:
                                    msg_compare = msg_datetime.replace(tzinfo=None)
                            if msg_compare > end_compare:
                                continue

                        # Build message entry matching API format
                        msg_type = metadata.get("type", "smart_message")
                        text_content = msg.get("text", "")

                        sent_messages.append({
                            "message_id": metadata.get("message_id", f"firestore_{conv_doc.id}_{len(sent_messages)}"),
                            "customer_phone": customer_info.get("phone_full") or user_data.get("phone_full", ""),
                            "customer_name": customer_info.get("name") or user_data.get("name", "Unknown"),
                            "message_type": msg_type,
                            "language": msg.get("language", "ar"),
                            "status": "sent",
                            "reason": message_type_names.get(msg_type, msg_type),
                            "sent_at": msg_datetime.isoformat() if hasattr(msg_datetime, 'isoformat') else str(msg_datetime),
                            "content_preview": text_content[:100] + "..." if len(text_content) > 100 else text_content,
                            "full_content": text_content,
                            "template_data": {},
                            "source": "firestore"
                        })

            except Exception as e:
                print(f"Error processing user {user_doc.id}: {e}")
                continue

        # Sort by sent_at descending (newest first)
        sent_messages.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
        return sent_messages[:limit]

    except Exception as e:
        print(f"Error querying Firestore for sent messages: {e}")
        import traceback
        traceback.print_exc()
        return []


# Global instance
smart_messaging = SmartMessagingService()