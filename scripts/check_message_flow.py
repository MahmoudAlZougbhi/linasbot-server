#!/usr/bin/env python3
"""
تشخيص مسار الرسائل: من الويب هوك → الـ AI → الرد
تشغيل: python scripts/check_message_flow.py

يفحص: الـ provider، Firestore، OpenAI، ويحاكي رسالة ويب هوك لمعرفة أين يتوقف المسار.
"""
import os
import sys
import asyncio
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def _ok(msg):
    print(f"   ✅ {msg}")


def _fail(msg):
    print(f"   ❌ {msg}")


def _warn(msg):
    print(f"   ⚠️  {msg}")


def _step(n, title):
    print(f"\n--- {n}. {title} ---")


def check_env():
    """1. فحص المتغيرات والـ provider"""
    _step(1, "فحص الـ Provider و credentials")
    provider = os.getenv("MONTYMOBILE_API_KEY") and "montymobile" or "meta"
    if os.getenv("MONTYMOBILE_API_KEY"):
        _ok("MONTYMOBILE_API_KEY موجود")
    else:
        _fail("MONTYMOBILE_API_KEY غير موجود")
    if os.getenv("MONTYMOBILE_TENANT_ID"):
        _ok("MONTYMOBILE_TENANT_ID موجود")
    else:
        _fail("MONTYMOBILE_TENANT_ID غير موجود")
    if os.getenv("OPENAI_API_KEY"):
        _ok("OPENAI_API_KEY موجود")
    else:
        _fail("OPENAI_API_KEY غير موجود - الـ AI لن يرد")
    if os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN"):
        _ok("WHATSAPP_WEBHOOK_VERIFY_TOKEN موجود")
    else:
        _warn("WHATSAPP_WEBHOOK_VERIFY_TOKEN غير موجود - التحقق من الويب هوك قد يفشل")


def check_firestore():
    """2. فحص Firestore"""
    _step(2, "فحص Firestore")
    try:
        from utils.utils import get_firestore_db
        db = get_firestore_db()
        if db:
            _ok("Firestore متصل")
        else:
            _fail("Firestore غير مهيأ (get_firestore_db رجع None)")
    except Exception as e:
        _fail(f"Firestore خطأ: {e}")


def check_adapter_parse():
    """3. فحص تحليل الويب هوك (parse)"""
    _step(3, "فحص تحليل رسالة الويب هوك (parse)")
    try:
        from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
        adapter = WhatsAppFactory.get_adapter()
        # محاكاة صيغة Meta/MontyMobile
        fake_webhook = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": os.getenv("MONTYMOBILE_TENANT_ID", "test"),
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "9611234567", "phone_number_id": "123"},
                        "contacts": [{"wa_id": "9611234567", "profile": {"name": "Test"}}],
                        "messages": [{
                            "from": "9611234567",
                            "id": "wamid.test123",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "مرحبا"}
                        }]
                    }
                }]
            }]
        }
        parsed = adapter.parse_webhook_message(fake_webhook)
        if parsed and parsed.get("user_id") and parsed.get("type") == "text":
            _ok(f"الـ parse نجح: user_id={parsed.get('user_id')}, type={parsed.get('type')}")
        else:
            _fail(f"الـ parse فشل أو رجع صيغة غير متوقعة: {parsed}")
    except Exception as e:
        _fail(f"خطأ في الـ parse: {e}")
        import traceback
        traceback.print_exc()


def check_webhook_post():
    """5. فحص استقبال الويب هوك (يحتاج السيرفر شغال)"""
    _step(5, "فحص استقبال الويب هوك (POST /webhook)")
    try:
        import httpx
        base = os.getenv("WEBHOOK_TEST_URL", "http://localhost:8003")
        url = f"{base.rstrip('/')}/webhook"
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": os.getenv("MONTYMOBILE_TENANT_ID", "test"),
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "96178974402", "phone_number_id": "123"},
                        "contacts": [{"wa_id": "96178974402", "profile": {"name": "Test"}}],
                        "messages": [{
                            "from": "96178974402",
                            "id": "wamid.check_" + str(int(__import__("time").time())),
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "test webhook"}
                        }]
                    }
                }]
            }]
        }
        r = httpx.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                _ok(f"الويب هوك يستقبل: POST {url} → 200 OK")
            elif data.get("status") == "skipped" and "duplicate" in str(data.get("reason", "")):
                _ok(f"الويب هوك يستقبل (رسالة مكررة تم تجاهلها): POST {url} → 200")
            else:
                _ok(f"الويب هوك استجاب: {data}")
        else:
            _fail(f"الويب هوك رجع {r.status_code}: {r.text[:200]}")
    except httpx.ConnectError:
        _warn("لا يمكن الاتصال بالويب هوك – شغّل السيرفر أولاً: python3 main.py")
    except Exception as e:
        _fail(f"خطأ في فحص الويب هوك: {e}")


async def check_montymobile_send_async():
    """6. فحص إرسال MontyMobile (dry-run في local)"""
    _step(6, "فحص MontyMobile إرسال (محاكاة)")
    try:
        from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
        adapter = WhatsAppFactory.get_adapter()
        result = await adapter.send_text_message("9613000000", "Test من check_message_flow")
        if isinstance(result, dict) and result.get("success"):
            if result.get("dry_run"):
                _ok("MontyMobile adapter جاهز (dry-run – لم يرسل فعلياً)")
            else:
                _ok("MontyMobile أرسل بنجاح ✅")
        elif isinstance(result, dict) and not result.get("success"):
            _fail(f"MontyMobile API رفض: {result.get('error', 'Unknown')}")
        else:
            _ok("MontyMobile adapter جاهز")
    except Exception as e:
        _fail(f"خطأ في MontyMobile إرسال: {e}")


async def check_full_flow():
    """7. محاكاة رسالة كاملة: webhook → handle_message → AI → رد"""
    _step(7, "محاكاة مسار كامل (رسالة → AI → رد)")
    try:
        from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
        from modules.webhook_handlers import handle_message_whatsapp_with_adapter
        import config

        adapter = WhatsAppFactory.get_adapter()
        test_user = "9613000000"  # رقم اختبار
        test_msg = "مرحبا"

        # تهيئة حالة المستخدم للاختبار
        if test_user not in config.user_data_whatsapp:
            config.user_data_whatsapp[test_user] = {
                "user_preferred_lang": "ar",
                "current_conversation_id": None,
                "phone_number": test_user,
                "awaiting_gender": False,
                "awaiting_clarification": False,
                "awaiting_name": False,
            }
        config.user_gender[test_user] = "unknown"
        config.user_greeting_stage[test_user] = 1

        print(f"   إرسال رسالة اختبار: '{test_msg}' من {test_user}")
        print("   (جاري استدعاء handle_message_whatsapp_with_adapter...)")

        await handle_message_whatsapp_with_adapter(
            user_id=test_user,
            user_input_text=test_msg,
            user_name="Test User",
            adapter=adapter,
            phone_number=test_user,
        )

        _ok("handle_message انتهى بدون استثناء")
        _ok("إذا شفت رد على واتساب أو في الـ logs، المسار يعمل")
        _warn("في APP_MODE=local قد يكون الرد dry-run (لن يصل فعلياً للواتساب)")
    except Exception as e:
        _fail(f"خطأ في المسار الكامل: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("=" * 60)
    print("🔍 تشخيص مسار الرسائل: واتساب → AI → رد")
    print("=" * 60)

    # تهيئة Firestore و config قبل الفحوصات
    try:
        from utils.utils import initialize_firestore
        from storage.persistent_storage import migrate_from_legacy
        migrate_from_legacy()
        initialize_firestore()
        import config
        config.load_bot_assets()
        config.load_training_data()
        print("\n   ✅ تم تهيئة Firestore و config\n")
    except Exception as e:
        print(f"\n   ⚠️  تحذير عند التهيئة: {e}\n")

    check_env()
    check_firestore()
    check_adapter_parse()
    check_webhook_post()
    asyncio.run(check_montymobile_send_async())
    asyncio.run(check_full_flow())

    print("\n" + "=" * 60)
    print("📋 ملخص:")
    print("   - خطوة 5 (الويب هوك): شغّل السيرفر أولاً (python3 main.py) في terminal آخر")
    print("     ثم شغّل السكربت – أو استخدم WEBHOOK_TEST_URL=https://ngrok-xxx/webhook")
    print("   - خطوة 6 (MontyMobile): في APP_MODE=local يكون dry-run ولا يرسل فعلياً")
    print("   - إذا كل الفحوصات ✅: المسار يعمل. المشكلة غالباً رابط الويب هوك في MontyMobile")
    print("   - استخدم ngrok للاختبار المحلي: ngrok http 8003")
    print("=" * 60)


if __name__ == "__main__":
    main()
