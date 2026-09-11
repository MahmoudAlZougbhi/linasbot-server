# مسار الرسالة من 0 للأخر – Lina's AI Bot

## خريطة المسار (Flow Map)

```mermaid
flowchart TD
    A[👤 USER يرسل رسالة] --> B[📥 WEBHOOK<br/>parse · CRM · Firestore]
    B --> C{📌 ROUTING}
    C -->|صورة| D3[Vision]
    C -->|صوت| D4[Whisper → نص]
    C -->|نص| E[💾 handle_message<br/>save · sentiment · combining]
    E --> F[⏳ _process_and_respond]
    F --> G{Published CM?}
    G -->|لا| H[unpublished message]
    G -->|نعم| I[Customer Reply V2]
    I --> J{FAQ fast path?}
    J -->|نعم| K[FAQ reply]
    J -->|لا| L[CM retrieval + Terra answer]
    K --> O[📤 إرسال bot_reply]
    L --> O
    H --> O
    O --> P[👤 USER يستلم]
```

---

## مخطط نصي

```
0. USER يرسل رسالة
        ↓
1. WEBHOOK (parse, CRM, Firestore)
        ↓
2. ROUTING (صورة, صوت, نص)
        ↓
3. handle_message (save, sentiment, takeover check, combining)
        ↓
4. _process_and_respond (out-of-scope check)
        ↓
5. Phase 1 (لغة + takeover + unpublished guard)
        ↓
6. Phase 2 Customer Reply V2
        ↓
   unpublished → unpublished message
   published → FAQ fast path أو CM retrieval + Terra
        ↓
7. إرسال bot_reply (Meta Cloud)
        ↓
8. USER يستلم الرد
```

## ملخص

| المرحلة | من | إلى | مين يقرر |
|---------|-----|-----|----------|
| 0–3 | User | Bot | — |
| 4–5 | Bot | Q&A / GPT | Bot (يجرّب Q&A أولاً) |
| 6 | Bot | GPT | GPT (هل بدو context؟) |
| 7 | GPT | Bot | GPT (يطلب tool) |
| 7 | Bot | Selector AI | Bot (ينفذ) |
| 7 | Selector AI | Bot | Selector AI |
| 8 | Bot | GPT | GPT (يستخدم المحتوى) |
| 9 | GPT | Bot | GPT (action + bot_reply + handover) |
| 10 | Bot | User | Bot (ينفذ) |

**الخلاصة:** الـ AI (GPT + Selector) يقرر، البوت ينفذ. GPT يقرر متى نحوّل للبشري (handover_degree / human_handover).

---

## مسار الكود (Code Path)

| الخطوة | الملف | الدالة / المسار |
|--------|-------|------------------|
| 0 | WhatsApp | المستخدم يرسل رسالة |
| 1 | `modules/webhook_handlers.py` | `receive_webhook()` → `process_parsed_message()` → `adapter.parse_webhook_message()` (parse) → `resolve_customer_from_external()` (CRM) → `get_user_state_from_firestore()` (Firestore restore) |
| 2 | `modules/webhook_handlers.py` | `process_parsed_message()`: `image` → `handle_photo_message_whatsapp_with_adapter()` \| `audio` → `handle_voice_message_whatsapp_with_adapter()` \| نص → `handle_message_whatsapp_with_adapter()` _(/start و /train غير مستخدمين)_ |
| 3 | `handlers/text_handlers_message.py` | `handle_message()` → save to Firestore → `sentiment_service.analyze_sentiment()` → takeover check → `config.user_pending_messages` (combining) → `_delayed_process_messages()` |
| 4 | `handlers/text_handlers_delayed.py` → `handlers/text_handlers_respond.py` | `_delayed_process_messages()` → `_process_and_respond()` (out-of-scope check) |
| 5 | `handlers/text_handlers_respond_phase1.py` | لغة + takeover + unpublished guard |
| 6 | `handlers/text_handlers_respond_phase2.py` | Customer Reply V2 (`_handle_published_cm_runtime`) — FAQ fast path ثم published CM. ما في classic GPT. |
| 7 | `services/local_qa_service.py` | `find_match_with_tier()` جوّا V2 FAQ fast path |
| 8 | `handlers/text_handlers_respond.py` | `send_message_func()` + `save_conversation_message_to_firestore()` |
| 9 | Adapter (Meta Cloud) | `adapter.send_text_message()` → WhatsApp |
