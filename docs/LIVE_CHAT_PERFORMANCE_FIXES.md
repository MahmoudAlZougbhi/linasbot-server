# Live Chat Performance Fixes

## ملخص المشاكل والحلول

### المشكلة 1: بطء فتح Live Chat
**السبب:** `/api/live-chat/unified-chats` كان يعمل scan ثقيل على Firestore (loop على كل users وجلب conversations لكل user) و cache TTL قصير (15 ثانية).

**الحل:**
- رفع CACHE_TTL من 15 إلى 60 ثانية
- الـ cache يتم invalidate فقط عند new_message/new_conversation (من خلال `save_conversation_message_to_firestore`)
- الـ frontend لم يعد ينادي `/unified-chats` بعد كل SSE event:
  - عند `new_message`: تحديث محلي فقط (move to top + update last_message) + debounce للـ refresh (مرة كل 3 ثواني)
  - عند `new_conversation`: إضافة محلياً بدون API call

### المشكلة 2: Load More مش شغال
**السبب:** hard cap على 200 user كان يعطي `has_more=false` خطأ.

**الحل:**
- إزالة الـ 200 cap تماماً
- الـ response يرجع: `chats`, `next_cursor`, `has_more`
- الـ frontend يعمل append: `setActiveConversations((prev) => [...prev, ...chatsResponse.chats])`
- دعم `cursor` في الـ API للـ pagination المستقبلي

### المشكلة 3: رسالة WhatsApp بتتأخر على Dashboard
**السبب:** الـ frontend كان ينادي `refreshChats()` بعد كل `new_message` وبالتالي `/unified-chats` (endpoint ثقيل) لكل رسالة.

**الحل Frontend:**
- عند استقبال SSE `new_message`:
  1. إذا الرسالة لنفس المحادثة المفتوحة: **append فوراً** للـ messages (بدون API call)
  2. تحديث قائمة الشاتات **محلياً**: move conversation to top + update last_message + last_activity
  3. debounce للـ refresh: مرة كل 3 ثواني بدل كل message
- عند `new_conversation`: إضافة المحادثة محلياً بدون API call

**الحل Backend:**
- SSE endpoint فيه headers تمنع buffering:
  - `Cache-Control: no-cache, no-store, must-revalidate`
  - `Pragma: no-cache`
  - `X-Accel-Buffering: no`
- Webhook flow صحيح: يحفظ الرسالة → broadcast `new_message` فوراً → بعدين AI reply (الـ broadcast مش متأخر)

**Logs مضافة:**
- `📡 [SSE] client connected` عند connect
- `📡 [SSE] broadcast new_message conv_id=... user_id=...` عند broadcast
- `📊 [unified-chats] cache hit | N chats | Xms` عند cache hit
- `📊 [unified-chats] Firestore scan | users=N | chats=M | page=P | Xms` عند Firestore scan

---

## الملفات المعدلة

| ملف | التغييرات |
|-----|-----------|
| `services/live_chat_service.py` | CACHE_TTL 60s، إزالة 200 cap، إضافة next_cursor، timing logs |
| `modules/live_chat_api.py` | SSE logs، دعم cursor param، broadcast new_message log |
| `dashboard/src/hooks/useLiveChatSSE.js` | updateChatListLocally، debounce refresh 3s، local list update، new_conversation محلي |
| `dashboard/src/pages/LiveChat.js` | updateChatListLocally callback |

---

## كيف تتأكد إن المشكلة انحلت

1. **بطء الفتح:**
   - افتح Live Chat
   - راقب الـ logs: `📊 [unified-chats] Firestore scan | ... | Xms` – الوقت لازم يكون أقل
   - افتح مرة ثانية خلال 60 ثانية – لازم تشوف `📊 [unified-chats] cache hit` (بدون Firestore scan)

2. **Load More:**
   - إذا عندك أكثر من 30 محادثة، اضغط "Load More"
   - لازم يطلع المزيد من المحادثات
   - راقب `has_more` و `next_cursor` في الـ response

3. **تأخر الرسائل:**
   - أرسل رسالة من WhatsApp
   - لازم تظهر على Dashboard **فوراً** (بدون انتظار AI reply)
   - راقب الـ logs: `📡 [SSE] broadcast new_message` بعد الحفظ
   - قائمة الشاتات تتحدث محلياً (المحادثة تروح للأعلى) بدون انتظار refresh ثقيل

4. **SSE Connect:**
   - افتح Live Chat
   - راقب الـ log: `📡 [SSE] client connected`
