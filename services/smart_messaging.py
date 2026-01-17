# Smart Messaging Service
# Implements requirement #11 from project specifications

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os

class SmartMessagingService:
    """
    Handles automated messaging:
    - 24h appointment reminders
    - Same-day check-ins
    - Post-session feedback
    - No-show follow-ups
    - 1-month follow-ups
    """
    
    def __init__(self):
        self.message_templates = self._load_templates()
        self.scheduled_messages = {}
        self.sent_messages_log = []
        
    def _load_templates(self) -> Dict:
        """Load message templates from JSON file or use defaults"""
        template_file = 'data/message_templates.json'
        
        if os.path.exists(template_file):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    templates_data = json.load(f)
                
                # Extract only the language templates (ar, en, fr) from each template
                templates = {}
                for template_id, template_data in templates_data.items():
                    templates[template_id] = {
                        'ar': template_data.get('ar', ''),
                        'en': template_data.get('en', ''),
                        'fr': template_data.get('fr', '')
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
    
    def schedule_message(
        self,
        customer_phone: str,
        message_type: str,
        send_at: datetime,
        placeholders: Dict[str, str],
        language: str = "ar",
        service_id: int = None,
        service_name: str = None
    ) -> str:
        """Schedule a message to be sent at specific time with service context"""

        message_id = f"{message_type}_{customer_phone}_{send_at.timestamp()}"

        # Check if smart messaging is enabled before scheduling
        if not self._is_smart_messaging_enabled():
            print(f"Smart messaging is disabled globally, not scheduling message {message_id}")
            return None

        # Check service-template mapping
        if service_id and not self._is_template_enabled_for_service(service_id, message_type):
            print(f"Template {message_type} not enabled for service {service_id}, skipping")
            return None

        self.scheduled_messages[message_id] = {
            "customer_phone": customer_phone,
            "message_type": message_type,
            "send_at": send_at,
            "placeholders": placeholders,
            "language": language,
            "service_id": service_id,
            "service_name": service_name or "Unknown Service",
            "status": "scheduled",
            "created_at": datetime.now()
        }

        # If preview mode is enabled, also add to preview queue
        if self._is_preview_mode_enabled():
            self._add_to_preview_queue(message_id)

        return message_id

    def _is_smart_messaging_enabled(self) -> bool:
        """Check if smart messaging is globally enabled"""
        try:
            settings_file = 'data/app_settings.json'
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
            settings_file = 'data/app_settings.json'
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
            mapping_file = 'data/service_template_mapping.json'
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
        
        if message_type not in self.message_templates:
            return None
        
        template = self.message_templates[message_type].get(language, 
                   self.message_templates[message_type]["en"])
        
        # Replace placeholders
        message = template
        for key, value in placeholders.items():
            placeholder = f"{{{{{key}}}}}"
            message = message.replace(placeholder, str(value))
        
        return message
    
    async def process_scheduled_messages(self) -> List[Dict]:
        """Process all due scheduled messages"""
        
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
                    messages_to_send.append({
                        "phone": message_data["customer_phone"],
                        "content": content,
                        "type": message_data["message_type"],
                        "message_id": message_id
                    })
                    
                    # Update status
                    self.scheduled_messages[message_id]["status"] = "sent"
                    self.scheduled_messages[message_id]["sent_at"] = current_time
                    
                    # Log sent message
                    self.sent_messages_log.append({
                        "message_id": message_id,
                        "phone": message_data["customer_phone"],
                        "type": message_data["message_type"],
                        "sent_at": current_time,
                        "content": content[:100] + "..."  # Log first 100 chars
                    })
        
        return messages_to_send
    
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

        placeholders = {
            "customer_name": customer_name,
            "appointment_date": appointment_date.strftime("%Y-%m-%d"),
            "appointment_time": appointment_date.strftime("%H:%M"),
            "branch_name": customer_data.get("branch", "الفرع الرئيسي"),
            "service_name": customer_data.get("service", "جلسة ليزر"),
            "phone_number": "01234567"  # Support phone
        }

        messages_scheduled = 0

        # Schedule 24h reminder
        reminder_24h_time = appointment_date - timedelta(hours=24)
        if reminder_24h_time > datetime.now():
            self.schedule_message(
                customer_phone,
                "reminder_24h",
                reminder_24h_time,
                placeholders,
                language
            )
            messages_scheduled += 1

        # Schedule same-day check-in (morning of appointment)
        checkin_time = appointment_date.replace(hour=9, minute=0, second=0)
        if checkin_time > datetime.now() and checkin_time < appointment_date:
            self.schedule_message(
                customer_phone,
                "same_day_checkin",
                checkin_time,
                placeholders,
                language
            )
            messages_scheduled += 1

        # Schedule post-session feedback (2 hours after appointment)
        feedback_time = appointment_date + timedelta(hours=2)
        self.schedule_message(
            customer_phone,
            "post_session_feedback",
            feedback_time,
            placeholders,
            language
        )
        messages_scheduled += 1

        # Schedule 1-month follow-up
        followup_time = appointment_date + timedelta(days=30)
        self.schedule_message(
            customer_phone,
            "one_month_followup",
            followup_time,
            placeholders,
            language
        )
        messages_scheduled += 1

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
            else:
                summary["sent"] += 1
            
            # Count by type
            msg_type = message_data["message_type"]
            summary["by_type"][msg_type] = summary["by_type"].get(msg_type, 0) + 1
        
        return summary
    
    def cancel_scheduled_messages(self, customer_phone: str, message_type: Optional[str] = None):
        """Cancel scheduled messages for a customer"""
        
        cancelled = []
        for message_id, message_data in list(self.scheduled_messages.items()):
            if message_data["customer_phone"] == customer_phone and message_data["status"] == "scheduled":
                if not message_type or message_data["message_type"] == message_type:
                    self.scheduled_messages[message_id]["status"] = "cancelled"
                    cancelled.append(message_id)
        
        return cancelled

# Global instance
smart_messaging = SmartMessagingService()