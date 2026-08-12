"""Smart messaging template load/resolve mixin (LOC split)."""

from __future__ import annotations

import json
import os
from typing import Any, cast

from services.smart_messaging_catalog import normalize_template_id


class SmartMessagingTemplatesMixin:
    """Load JSON templates and render placeholder content."""

    def _load_templates(self) -> dict:
        """Load message templates from JSON file or use defaults"""
        template_file = self.templates_file

        if os.path.exists(template_file):
            try:
                with open(template_file, encoding="utf-8") as f:
                    templates_data = json.load(f)

                # Extract only the language templates (ar, en, fr) from each template
                templates: dict[str, Any] = {}
                for template_id, template_data in templates_data.items():
                    canonical_id = normalize_template_id(template_id)

                    current = templates.get(canonical_id, {})
                    normalized = {
                        "ar": template_data.get("ar", ""),
                        "en": template_data.get("en", ""),
                        "fr": template_data.get("fr", ""),
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

Au plaisir de vous voir! 💜""",
            },
            "thank_you_message_sent_after_session": {
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
Vos commentaires comptent 🙏""",
            },
            "sent_17_days_after_last_session_new": {
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
Votre bien-être est notre priorité 💜""",
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

Nous sommes toujours là pour vous 💜""",
            },
            "sent_for_pause": {
                "ar": """🌸 مرحباً {{customer_name}}

نذكرك بموعدك المؤجل في مركز لينا ليزر:

💆 الخدمة: {{service_name}}
📅 التاريخ: {{appointment_date}}
⏰ الوقت: {{appointment_time}}
📍 الفرع: {{branch_name}}

للحجز أو الاستفسار:
📱 {{phone_number}}
💬 يمكنك الرد على هذه الرسالة في أي وقت.

نتطلع لخدمتك 💜""",
                "en": """🌸 Hi {{customer_name}}

We're following up on your paused appointment at Lina's Laser Center:

💆 Service: {{service_name}}
📅 Date: {{appointment_date}}
⏰ Time: {{appointment_time}}
📍 Branch: {{branch_name}}

To book or ask anything:
📱 {{phone_number}}
💬 You can reply to this message anytime.

We're here for you 💜""",
                "fr": """🌸 Bonjour {{customer_name}}

Suite à votre rendez-vous en pause au Centre Laser Lina:

💆 Service: {{service_name}}
📅 Date: {{appointment_date}}
⏰ Heure: {{appointment_time}}
📍 Branche: {{branch_name}}

Pour réserver ou une question:
📱 {{phone_number}}
💬 Vous pouvez répondre à tout moment.

Au plaisir de vous accueillir 💜""",
            },
            "session_feedback": {
                "ar": """مرحباً {{customer_name}} 🌸
شكراً لزيارتك لنا.
يسعدنا جداً أن نعرف رأيك بجلسك الأخيرة، لأن تقييمك يساعدنا على تحسين تجربتك دائماً.
اضغطي على الزر بالأسفل لتقييم تجربتك معنا.""",
                "en": """Hi {{customer_name}} 🌸
Thank you for visiting us.
We'd love to hear about your last session—your feedback helps us keep improving your experience.
Tap the button below to rate your visit with us.""",
                "fr": """Bonjour {{customer_name}} 🌸
Merci pour votre visite.
Nous serions ravis d'avoir votre avis sur votre dernière séance — votre retour nous aide à améliorer votre expérience.
Appuyez sur le bouton ci-dessous pour évaluer votre visite.""",
            },
        }

    def _resolve_template_key(self, template_id: str) -> str:
        """
        Resolve canonical template IDs with backwards-compatible fallbacks.
        """
        canonical = normalize_template_id(template_id)
        if canonical in self.message_templates:
            return canonical

        legacy_fallbacks = {
            "whatsapp_lead_no_booking": "missed_yesterday",
        }
        fallback = legacy_fallbacks.get(canonical)
        if fallback and fallback in self.message_templates:
            return fallback

        return canonical

    def get_message_content(self, message_type: str, language: str, placeholders: dict[str, str]) -> str | None:
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

        return cast(str, message)
