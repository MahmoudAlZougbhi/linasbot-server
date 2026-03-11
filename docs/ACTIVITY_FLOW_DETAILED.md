# Activity Flow – شرح تفصيلي كامل

هذا المستند يشرح **كل شيء** يحدث في تدفق النشاط: ما يُرسل للمستخدم، ما يُرسل للبوت، ما يُرسل للـ AI، وما يُعاد من كل جهة.

---

## 1. نظرة عامة على التدفق

```
User (WhatsApp)  →  Bot  →  AI (GPT / Selector)  →  Bot  →  User (WhatsApp)
```

كل رسالة تمر بهذا المسار. الـ Activity Flow يسجل كل خطوة للشفافية في الـ Dashboard.

---

## 2. نقطة البداية: استقبال الرسالة

**الملف:** `handlers/text_handlers_message.py`

### ما يحدث أولاً:

1. **المستخدم يرسل رسالة** على واتساب
2. **`handle_message()`** تستقبل:
   - `user_id` (رقم الواتساب)
   - `user_name` (اسم المستخدم)
   - `user_input_text` (نص الرسالة)
   - `user_data` (بيانات المستخدم من Firestore)

3. **التحقق من الحالة:**
   - إذا المستخدم في **training mode** → ينتقل لـ `handle_training_input`
   - إذا المستخدم في **human takeover** (محادثة مع موظف) → البوت يرسل "شوي، منكون معك" ولا يمر للـ AI
   - **Sentiment analysis** على الرسالة → إذا غضب/إساءة → تحويل فوري لموظف بشري

4. **حفظ الرسالة في Firestore** كـ `type: "user"`

5. **دمج الرسائل السريعة:** إذا المستخدم أرسل عدة رسائل بسرعة، تُدمج في رسالة واحدة بعد `MESSAGE_COMBINING_DELAY`

6. **استدعاء `_delayed_process_messages`** → الذي يستدعي `_process_and_respond`

---

## 3. المعالجة الرئيسية: `_process_and_respond`

**الملف:** `handlers/text_handlers_respond.py`

هنا يتم **تقرير المسار** لكل رسالة: هل يذهب للـ Router، للـ Q&A، للـ Dynamic Retrieval، أو للـ GPT؟

---

## 4. Router (الموجه الأول)

**الملف:** `services/conversation_router.py`

**الترتيب:** قبل أي استدعاء للـ AI، الـ Router يقرر:

| الإجراء | الشرط | ما يُرسل للمستخدم |
|---------|-------|-------------------|
| `human_handover` | المستخدم طلب موظف بشري | "تم تحويلك لأحد من موظفينا شوي..." |
| `greeting` | رسالة ترحيب فقط (مرحبا، هلا، إلخ) | قالب ترحيب (مثلاً: "Marhaba, ana Marwa...") |
| `fallback` | الرسالة غير واضحة | "أكيد، فيك توضحلي أكتر شو الخدمة..." |
| `ask_gender` | يحتاج جنس للإجابة | سؤال الجنس (أي خدمة؟ ذكر/أنثى؟) |
| `ask_clarification` | يحتاج توضيح | "ممكن توضحلي أي خدمة؟" |
| `answer_question` | يكفي معلومات → يرد | يمر للـ Q&A أو GPT |

**ما يُسجل في Activity Flow للـ Router:**
- `user_message`: رسالة المستخدم
- `bot_to_user`: الرد النهائي
- `source`: `router_greeting` | `router_fallback` | `router_ask_gender` | `router_ask_clarification"`

---

## 5. Q&A Database (قاعدة الأسئلة والأجوبة)

**الشرط:** إذا تطابق السؤال مع Q&A ≥ 90% → **لا يُستدعى GPT أبداً**

**الملف:** `handlers/text_handlers_respond.py` + `services/local_qa_service.py`

### ما يُرسل للبوت (من Q&A):
- `query_to_send_to_gpt`: السؤال الأصلي
- `match_result`: نتيجة المطابقة (score, qa_pair)

### ما يُرسل للمستخدم:
- `qa_response`: الإجابة من قاعدة Q&A مباشرة

**ما يُسجل في Activity Flow:**
- `source`: `qa_database`
- `flow_steps`:
  1. User → Bot → السؤال
  2. Q&A Match (≥90%) → "Bot matched from Q&A database. No AI call."
  3. Bot → User → الإجابة

---

## 6. Dynamic Retrieval (الـ Selector AI)

**الشرط:** إذا لم يوجد Q&A match، وموجود ملفات knowledge/price/style

**الملف:** `services/dynamic_retrieval_service.py`

### المرحلة 1: Selector AI (GPT-4o-mini)

**ما يُرسل للـ AI (Selector):**
- `USER_MESSAGE`: رسالة المستخدم (أو السؤال الأصلي + توضيح)
- `KNOWLEDGE_TITLES`: قائمة عناوين ملفات المعرفة
- `PRICE_TITLES`: قائمة عناوين ملفات الأسعار
- `STYLE_TITLES`: قائمة عناوين ملفات الأسلوب

**الـ Prompt:** يطلب من الـ AI اختيار الملفات المطلوبة فقط (لا يجيب)

**ما يُرجع الـ AI:**
```json
{
  "files": ["file_id_1", "file_id_2"],
  "action": "normal" | "ask_clarification" | "fallback_to_general"
}
```

**إذا `action == "ask_clarification"`:**
- البوت يرسل للمستخدم: "Could you provide more details... which service?"
- **لا يُستدعى GPT الرئيسي**
- يُسجل في Activity Flow: `source: "dynamic_retrieval"`

**إذا `action == "normal"`:**
- البوت يحمّل محتوى الملفات المختارة
- يدمجها في `custom_knowledge_context`
- يمرّها للـ GPT الرئيسي

**ما يُسجل في Activity Flow للـ Dynamic Retrieval:**
- `bot_sent_to_selector`: User message + file titles
- `selector_ai_raw_response`: الـ JSON الخام من الـ AI
- `selected_titles`: الملفات المختارة

---

## 7. GPT الرئيسي (Main Chat Response)

**الملف:** `services/chat_response_service.py` → `get_bot_chat_response()`

### ما يُرسل للـ AI (GPT):

#### 1. System Instruction (الـ Prompt الأساسي):

```
- You are Marwa AI Assistant...
- STYLE GUIDE (MANDATORY)
- CORE KNOWLEDGE BASE
- PRICE LIST (إذا كان سؤال أسعار)
- ADDITIONAL CONTEXT (من Dynamic Retrieval إذا وُجد)
- OPERATIONAL CONTEXT (إذا resume من clarification/gender)
- GENDER INSTRUCTION (ذكر/أنثى/غير محدد)
- TRAINED Q&A REFERENCE (أفضل 3 Q&A ذات صلة)
- Hard rules (لا تختلق معلومات، human handover عند الطلب، إلخ)
```

#### 2. Context Messages:
- آخر 10 رسائل من المحادثة (من Firestore)

#### 3. User Query:
- `user_input`: السؤال الحالي أو `original_question + follow-up`
- إذا `operational_context`: يشرح أن المستخدم أجاب على سؤال توضيح/جنس → يجب الإجابة على السؤال الأصلي

### ما يُرجع الـ AI: JSON:
```json
{
  "action": "answer_question" | "ask_gender" | "human_handover" | ...,
  "bot_reply": "نص الرد",
  "detected_gender": "male" | "female" | null,
  "detected_language": "ar" | "en" | "fr" | "franco"
}
```

### Tool Calls (إذا طلب الـ AI):
- `check_next_appointment` → البوت يستدعي API
- `update_appointment_date` → البوت يستدعي API
- `get_pricing_details` → البوت يستدعي API
- إلخ...

**كل round-trip يُسجل:**
- `ai_requested`: اسم الـ tool
- `args`: المعاملات
- `bot_returned`: نتيجة الـ API

---

## 8. ما يُرسل للمستخدم (النهاية)

بعد كل المعالجة، البوت يرسل:

| المصدر | الرد |
|--------|------|
| Router | قالب (greeting, fallback, ask_gender, ask_clarification) |
| Q&A | إجابة من قاعدة البيانات |
| Dynamic Retrieval (ask_clarification) | سؤال توضيح |
| GPT | `bot_reply` من الـ JSON |

ثم يُحفظ في Firestore كـ `type: "ai"` ويُرسل عبر واتساب.

---

## 9. بنية التسجيل في Activity Flow

**الملف:** `services/interaction_flow_logger.py`

كل تفاعل يُسجل في `activity_flow.jsonl` بالحقول:

```json
{
  "timestamp": "2025-03-11T12:00:00.000Z",
  "user_id": "961...",
  "user_id_masked": "...1234",
  "user_name": "أحمد",
  "user_phone": "...",
  "user_phone_masked": "...5678",
  "user_message": "شو الأسعار عندكن؟",
  "bot_to_user": "هيدي الأسعار...",
  "source": "gpt" | "qa_database" | "dynamic_retrieval" | "rate_limit" | "moderation" | "router_*",
  "ai_query_summary": "Bot sent to AI: System prompt... Context messages... User query...",
  "ai_raw_response": "Raw GPT response (first 2000 chars)",
  "model": "gpt-4o-mini",
  "tokens": 1234,
  "prompt_tokens": 800,
  "completion_tokens": 434,
  "response_time_ms": 2500,
  "qa_match_score": 0.95,
  "tool_calls": ["check_next_appointment"],
  "flow_steps": [
    {"step": 1, "title": "User → Bot", "content": "..."},
    {"step": 2, "title": "Bot → AI", "content": "..."},
    {"step": 3, "title": "AI → Bot", "content": "..."},
    {"step": 4, "title": "Bot → User", "content": "..."}
  ]
}
```

---

## 10. ملخص المصادر (Sources)

| Source | المعنى | هل يُستدعى GPT؟ |
|--------|--------|------------------|
| `router_greeting` | ترحيب فقط | لا |
| `router_fallback` | رسالة غير واضحة | لا |
| `router_ask_gender` | سؤال الجنس | لا |
| `router_ask_clarification` | سؤال توضيح | لا |
| `router_human_handover` | طلب موظف | لا |
| `qa_database` | تطابق Q&A ≥90% | لا |
| `dynamic_retrieval` | Selector اختار ask_clarification | Selector فقط، لا GPT رئيسي |
| `gpt` | استدعاء GPT الرئيسي | نعم |
| `rate_limit` | تجاوز الحد | لا |
| `moderation` | محتوى غير مسموح | لا |

---

## 11. مسار كامل مع Dynamic Retrieval + GPT

عندما يكون السؤال يحتاج معرفة + GPT:

1. **User → Bot:** "شو الأسعار لليزر شعر؟"
2. **Bot → Selector AI:** User message + قائمة عناوين الملفات
3. **Selector AI → Bot:** `{"files": ["laser_hair_removal", "price_laser"], "action": "normal"}`
4. **Bot:** يحمّل محتوى الملفات المختارة
5. **Bot → GPT:** System prompt + Knowledge + Price + Style + User query
6. **GPT → Bot:** JSON مع `bot_reply` (وقد يطلب tools)
7. **Bot:** ينفذ tools إذا وُجدت
8. **Bot → GPT:** (round-trip) نتيجة الـ tool
9. **GPT → Bot:** الرد النهائي
10. **Bot → User:** الإجابة النهائية

---

## 12. الـ Dashboard: Activity Flow

**الملف:** `dashboard/src/pages/ActivityFlow.js`

- يعرض آخر 50 تفاعل (قابل للزيادة)
- بحث برقم الهاتف
- عند التوسيع: كل خطوة (flow_steps) مع المحتوى
- GPT usage: tokens, model, response time

---

## 13. الملفات الرئيسية

| الملف | الدور |
|------|------|
| `handlers/text_handlers_message.py` | استقبال الرسالة، التحقق، Firestore، استدعاء المعالجة |
| `handlers/text_handlers_delayed.py` | دمج الرسائل، استدعاء `_process_and_respond` |
| `handlers/text_handlers_respond.py` | Router، Q&A، Dynamic Retrieval، GPT، تسجيل Activity Flow |
| `services/conversation_router.py` | توجيه الرسائل (greeting, fallback, ask_gender, ask_clarification, answer_question) |
| `services/dynamic_retrieval_service.py` | Selector AI + تحميل الملفات |
| `services/chat_response_service.py` | استدعاء GPT، tool calls، flow_meta |
| `services/interaction_flow_logger.py` | تسجيل كل تفاعل |
| `modules/flow_api.py` | API للـ Dashboard |
| `storage/persistent_storage.py` | `activity_flow.jsonl` |

---

## 14. تفعيل/تعطيل Activity Flow

- **التحكم:** `INTERACTION_FLOW_DEBUG=1` (default) أو في `config.INTERACTION_FLOW_DEBUG`
- **الملف:** `LINASBOT_DATA_ROOT/logs/activity_flow.jsonl`
- **الـ Buffer:** آخر 500 تفاعل في الذاكرة

---

*آخر تحديث: بناءً على الكود الحالي في المشروع.*
