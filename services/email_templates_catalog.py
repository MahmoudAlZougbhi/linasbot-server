"""Linas AI transactional email copy (EN primary; AR/FR localization-ready)."""

from __future__ import annotations

from typing import Any

SUPPORTED_LOCALES = frozenset({"en", "ar", "fr"})

# Template id -> locale -> {subject, preview, heading, body_lines, cta_label, footer_note}
_TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "verify_email": {
        "en": {
            "subject": "Verify your Linas AI email",
            "preview": "Confirm your email to finish setting up Linas AI.",
            "heading": "Verify your email",
            "body_lines": [
                "Thanks for creating a Linas AI account.",
                "Confirm this email address to activate your account. This link expires in 48 hours.",
            ],
            "cta_label": "Verify email",
            "footer_note": "If you did not create this account, you can ignore this email.",
        },
        "ar": {
            "subject": "تأكيد بريدك في Linas AI",
            "preview": "أكد بريدك لإكمال إعداد حساب Linas AI.",
            "heading": "تأكيد البريد الإلكتروني",
            "body_lines": [
                "شكرًا لإنشاء حساب Linas AI.",
                "أكد هذا البريد لتفعيل حسابك. تنتهي صلاحية الرابط خلال 48 ساعة.",
            ],
            "cta_label": "تأكيد البريد",
            "footer_note": "إذا لم تنشئ هذا الحساب، يمكنك تجاهل هذه الرسالة.",
        },
        "fr": {
            "subject": "Vérifiez votre e-mail Linas AI",
            "preview": "Confirmez votre e-mail pour finaliser Linas AI.",
            "heading": "Vérifiez votre e-mail",
            "body_lines": [
                "Merci d'avoir créé un compte Linas AI.",
                "Confirmez cette adresse pour activer votre compte. Ce lien expire dans 48 heures.",
            ],
            "cta_label": "Vérifier l'e-mail",
            "footer_note": "Si vous n'avez pas créé ce compte, ignorez cet e-mail.",
        },
    },
    "reset_password": {
        "en": {
            "subject": "Reset your Linas AI password",
            "preview": "Use this one-time link to reset your password.",
            "heading": "Reset your password",
            "body_lines": [
                "We received a request to reset your Linas AI password.",
                "This one-time link expires in 1 hour.",
            ],
            "cta_label": "Reset password",
            "footer_note": "If you did not request this, you can ignore this email.",
        },
        "ar": {
            "subject": "إعادة تعيين كلمة مرور Linas AI",
            "preview": "استخدم هذا الرابط لمرة واحدة لإعادة التعيين.",
            "heading": "إعادة تعيين كلمة المرور",
            "body_lines": [
                "استلمنا طلبًا لإعادة تعيين كلمة مرور Linas AI.",
                "ينتهي صلاحية هذا الرابط خلال ساعة واحدة.",
            ],
            "cta_label": "إعادة التعيين",
            "footer_note": "إذا لم تطلب ذلك، تجاهل هذه الرسالة.",
        },
        "fr": {
            "subject": "Réinitialisez votre mot de passe Linas AI",
            "preview": "Utilisez ce lien unique pour réinitialiser votre mot de passe.",
            "heading": "Réinitialiser le mot de passe",
            "body_lines": [
                "Nous avons reçu une demande de réinitialisation de mot de passe Linas AI.",
                "Ce lien unique expire dans 1 heure.",
            ],
            "cta_label": "Réinitialiser",
            "footer_note": "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.",
        },
    },
    "password_changed": {
        "en": {
            "subject": "Your Linas AI password was changed",
            "preview": "Security notice: password updated.",
            "heading": "Password changed",
            "body_lines": [
                "Your Linas AI password was changed successfully.",
                "If this was not you, reset your password immediately and contact support.",
            ],
            "cta_label": "Sign in",
            "footer_note": "This is a security notification for your account.",
        },
        "ar": {
            "subject": "تم تغيير كلمة مرور Linas AI",
            "preview": "تنبيه أمني: تم تحديث كلمة المرور.",
            "heading": "تم تغيير كلمة المرور",
            "body_lines": [
                "تم تغيير كلمة مرور حساب Linas AI بنجاح.",
                "إذا لم تكن أنت، أعد التعيين فورًا وتواصل مع الدعم.",
            ],
            "cta_label": "تسجيل الدخول",
            "footer_note": "هذا إشعار أمني لحسابك.",
        },
        "fr": {
            "subject": "Votre mot de passe Linas AI a été modifié",
            "preview": "Alerte sécurité : mot de passe mis à jour.",
            "heading": "Mot de passe modifié",
            "body_lines": [
                "Votre mot de passe Linas AI a été modifié avec succès.",
                "Si ce n'était pas vous, réinitialisez immédiatement et contactez le support.",
            ],
            "cta_label": "Se connecter",
            "footer_note": "Ceci est une notification de sécurité.",
        },
    },
    "email_change_confirm": {
        "en": {
            "subject": "Confirm your new Linas AI email",
            "preview": "Confirm the new address for your account.",
            "heading": "Confirm new email",
            "body_lines": [
                "Confirm this new email address for your Linas AI account.",
                "This link expires in 24 hours.",
            ],
            "cta_label": "Confirm email",
            "footer_note": "If you did not request this change, ignore this email.",
        },
        "ar": {
            "subject": "تأكيد بريد Linas AI الجديد",
            "preview": "أكد العنوان الجديد لحسابك.",
            "heading": "تأكيد البريد الجديد",
            "body_lines": [
                "أكد عنوان البريد الجديد لحساب Linas AI.",
                "ينتهي صلاحية الرابط خلال 24 ساعة.",
            ],
            "cta_label": "تأكيد البريد",
            "footer_note": "إذا لم تطلب التغيير، تجاهل الرسالة.",
        },
        "fr": {
            "subject": "Confirmez votre nouvel e-mail Linas AI",
            "preview": "Confirmez la nouvelle adresse de votre compte.",
            "heading": "Confirmer le nouvel e-mail",
            "body_lines": [
                "Confirmez cette nouvelle adresse pour votre compte Linas AI.",
                "Ce lien expire dans 24 heures.",
            ],
            "cta_label": "Confirmer",
            "footer_note": "Si vous n'avez pas demandé ce changement, ignorez cet e-mail.",
        },
    },
    "email_changed_notice": {
        "en": {
            "subject": "Your Linas AI email was changed",
            "preview": "Security notice: account email updated.",
            "heading": "Email address changed",
            "body_lines": [
                "The email on your Linas AI account was changed.",
                "If this was not you, contact support immediately.",
            ],
            "cta_label": "Contact support",
            "footer_note": "This notice was sent to your previous email address.",
        },
        "ar": {
            "subject": "تم تغيير بريد حساب Linas AI",
            "preview": "تنبيه أمني: تم تحديث بريد الحساب.",
            "heading": "تم تغيير البريد",
            "body_lines": [
                "تم تغيير البريد المرتبط بحساب Linas AI.",
                "إذا لم تكن أنت، تواصل مع الدعم فورًا.",
            ],
            "cta_label": "التواصل مع الدعم",
            "footer_note": "أُرسل هذا الإشعار إلى بريدك السابق.",
        },
        "fr": {
            "subject": "L'e-mail de votre compte Linas AI a changé",
            "preview": "Alerte sécurité : e-mail du compte mis à jour.",
            "heading": "Adresse e-mail modifiée",
            "body_lines": [
                "L'e-mail associé à votre compte Linas AI a été modifié.",
                "Si ce n'était pas vous, contactez immédiatement le support.",
            ],
            "cta_label": "Contacter le support",
            "footer_note": "Cet avis a été envoyé à votre ancienne adresse.",
        },
    },
    "welcome": {
        "en": {
            "subject": "Welcome to Linas AI",
            "preview": "Your account is ready.",
            "heading": "Welcome to Linas AI",
            "body_lines": [
                "Your Linas AI account is ready.",
                "Sign in to connect WhatsApp, Instagram, and manage your business messaging.",
            ],
            "cta_label": "Open Linas AI",
            "footer_note": "Need help? Reply to this email or contact support@linasaibot.com.",
        },
        "ar": {
            "subject": "مرحبًا بك في Linas AI",
            "preview": "حسابك جاهز.",
            "heading": "مرحبًا بك في Linas AI",
            "body_lines": [
                "حساب Linas AI جاهز.",
                "سجّل الدخول لربط واتساب وإنستغرام وإدارة رسائل عملك.",
            ],
            "cta_label": "فتح Linas AI",
            "footer_note": "تحتاج مساعدة؟ رد على هذه الرسالة أو راسل support@linasaibot.com.",
        },
        "fr": {
            "subject": "Bienvenue sur Linas AI",
            "preview": "Votre compte est prêt.",
            "heading": "Bienvenue sur Linas AI",
            "body_lines": [
                "Votre compte Linas AI est prêt.",
                "Connectez-vous pour lier WhatsApp, Instagram et gérer votre messagerie.",
            ],
            "cta_label": "Ouvrir Linas AI",
            "footer_note": "Besoin d'aide ? Répondez à cet e-mail ou contactez support@linasaibot.com.",
        },
    },
    "security_notice": {
        "en": {
            "subject": "Linas AI security notice",
            "preview": "Important account security update.",
            "heading": "Security notice",
            "body_lines": [
                "A security-sensitive change was made on your Linas AI account.",
                "If this was not you, secure your account and contact support.",
            ],
            "cta_label": "Review account",
            "footer_note": "This is an automated security notification.",
        },
        "ar": {
            "subject": "تنبيه أمني من Linas AI",
            "preview": "تحديث أمني مهم للحساب.",
            "heading": "تنبيه أمني",
            "body_lines": [
                "حدث تغيير أمني مهم على حساب Linas AI.",
                "إذا لم تكن أنت، أمّن حسابك وتواصل مع الدعم.",
            ],
            "cta_label": "مراجعة الحساب",
            "footer_note": "هذا إشعار أمني تلقائي.",
        },
        "fr": {
            "subject": "Avis de sécurité Linas AI",
            "preview": "Mise à jour de sécurité importante.",
            "heading": "Avis de sécurité",
            "body_lines": [
                "Une modification sensible a été effectuée sur votre compte Linas AI.",
                "Si ce n'était pas vous, sécurisez votre compte et contactez le support.",
            ],
            "cta_label": "Vérifier le compte",
            "footer_note": "Ceci est une notification de sécurité automatique.",
        },
    },
}

# Billing template ids (interfaces / ready copy — no fake charges).
BILLING_TEMPLATE_IDS = (
    "billing_subscription_started",
    "billing_plan_changed",
    "billing_payment_problem",
    "billing_subscription_ended",
    "billing_credits_purchased",
    "billing_refund",
)

for _bid, _en_subject, _en_heading, _en_line in (
    (
        "billing_subscription_started",
        "Your Linas AI subscription started",
        "Subscription started",
        "Your subscription is active.",
    ),
    ("billing_plan_changed", "Your Linas AI plan changed", "Plan updated", "Your subscription plan was updated."),
    (
        "billing_payment_problem",
        "Linas AI payment problem",
        "Payment needs attention",
        "We could not process a subscription payment.",
    ),
    (
        "billing_subscription_ended",
        "Your Linas AI subscription ended",
        "Subscription ended",
        "Your subscription is no longer active.",
    ),
    (
        "billing_credits_purchased",
        "Linas AI credits purchased",
        "Credits added",
        "Token credits were added to your account.",
    ),
    (
        "billing_refund",
        "Linas AI refund / credit adjustment",
        "Account adjustment",
        "A refund or credit adjustment was applied.",
    ),
):
    _TEMPLATES[_bid] = {
        "en": {
            "subject": _en_subject,
            "preview": _en_heading,
            "heading": _en_heading,
            "body_lines": [
                _en_line,
                "Open Linas AI for details. Store receipts remain authoritative for App Store / Play.",
            ],
            "cta_label": "Open billing",
            "footer_note": "Questions? Contact support@linasaibot.com.",
        },
        "ar": {
            "subject": _en_subject,
            "preview": _en_heading,
            "heading": _en_heading,
            "body_lines": [_en_line, "افتح Linas AI للتفاصيل. إيصالات المتاجر تبقى المرجع لـ App Store / Play."],
            "cta_label": "الفوترة",
            "footer_note": "أسئلة؟ راسل support@linasaibot.com.",
        },
        "fr": {
            "subject": _en_subject,
            "preview": _en_heading,
            "heading": _en_heading,
            "body_lines": [_en_line, "Ouvrez Linas AI pour les détails. Les reçus des stores restent la référence."],
            "cta_label": "Ouvrir la facturation",
            "footer_note": "Questions ? support@linasaibot.com.",
        },
    }


def normalize_locale(locale: str | None) -> str:
    raw = (locale or "en").strip().lower()
    if raw.startswith("ar"):
        return "ar"
    if raw.startswith("fr"):
        return "fr"
    return "en"


def get_template_copy(template_id: str, locale: str | None = None) -> dict[str, Any]:
    loc = normalize_locale(locale)
    bucket = _TEMPLATES.get(template_id)
    if not bucket:
        raise KeyError(f"unknown_email_template:{template_id}")
    return dict(bucket.get(loc) or bucket["en"])


def list_template_ids() -> list[str]:
    return sorted(_TEMPLATES.keys())
