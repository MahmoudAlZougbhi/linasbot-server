# تحديث الـ env على الباكند (مثلاً OPENAI_API_KEY)

الـ `.env` **ما بتنرفع على GitHub** (مهمة أمان). التحديث يكون على السيرفر نفسه.

## إذا الباكند شغال بـ Docker (docker-compose)

1. **اتصل بالسيرفر** (SSH):
   ```bash
   ssh user@your-server
   ```

2. **روح لمجلد المشروع** اللي فيه `docker-compose.yml` أو `docker-compose.prod.yml`.

3. **عدّل الـ .env على السيرفر** (أو أنشئها إذا ما موجودة):
   ```bash
   nano .env
   ```
   ضيف أو حدّث السطر:
   ```
   OPENAI_API_KEY=sk-proj-xxxxxxxx
   ```
   (استخدم الـ key الجديد اللي غيّرته عندك محلياً.)

4. **أعد تشغيل الـ backend عشان يقرا الـ env الجديد**:
   ```bash
   docker-compose -f docker-compose.prod.yml up -d --build backend
   ```
   أو إذا بتستعمل `docker-compose.yml`:
   ```bash
   docker-compose up -d --build backend
   ```

5. **تأكد إن الـ key شغال**:
   ```bash
   docker-compose -f docker-compose.prod.yml exec backend env | grep OPENAI
   ```

## إذا الباكند شغال بدون Docker (مثلاً systemd أو يدوي)

1. عدّل ملف الـ `.env` اللي الباكند يقراه (نفس المسار اللي فيه التشغيل).
2. حدّث `OPENAI_API_KEY=...` بالـ key الجديد.
3. أعد تشغيل الخدمة، مثلاً:
   ```bash
   sudo systemctl restart linas-backend
   ```
   أو أوقف العملية وشغّل الباكند من جديد.

---

**ملاحظة:** ما ترفع أبداً ملف `.env` على Git؛ القيم الحساسة (مثل OPENAI_API_KEY) تظل على السيرفر فقط.
