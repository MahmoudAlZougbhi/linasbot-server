# Lina's Bot - استكشاف أخطاء systemd

## 1️⃣ أوامر التشخيص (نفّذها على السيرفر)

```bash
# آخر 100 سطر من الـ logs (الأهم)
sudo journalctl -u linasbot -n 100 --no-pager

# آخر 50 سطر + متابعة مباشرة
sudo journalctl -u linasbot -n 50 -f

# عرض status مع آخر 10 أسطر
sudo systemctl status linasbot
sudo journalctl -u linasbot -n 10 --no-pager

# الـ error log المخصص
sudo tail -100 /var/log/linasbot.error.log

# الـ output log
sudo tail -100 /var/log/linasbot.log
```

## 2️⃣ تشغيل يدوي لرؤية الـ traceback الحقيقي

```bash
cd /opt/linasbot
source venv/bin/activate
python main.py
```

أو مع uvicorn مباشرة (إذا main.py فشل عند الـ import):

```bash
cd /opt/linasbot
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8003
```

**ملاحظة:** `python main.py` يشغّل `initialize_firestore()` و `load_bot_assets()` قبل uvicorn. إذا فشل عند الـ import، جرّب:

```bash
cd /opt/linasbot && source venv/bin/activate && python -c "
from dotenv import load_dotenv
load_dotenv()
import config
print('OPENAI_API_KEY:', 'SET' if config.OPENAI_API_KEY else 'MISSING')
print('MONTYMOBILE_API_KEY:', 'SET' if __import__('os').getenv('MONTYMOBILE_API_KEY') else 'MISSING')
import main
"
```

## 3️⃣ Checklist – أسباب محتملة (مرتبة)

| # | السبب | كيف تتأكد |
|---|-------|-----------|
| 1 | **`.env` غير موجود أو فارغ** | `ls -la /opt/linasbot/.env` و `grep OPENAI_API_KEY /opt/linasbot/.env` |
| 2 | **`OPENAI_API_KEY` ناقص أو خاطئ** | `grep OPENAI_API_KEY /opt/linasbot/.env` |
| 3 | **`data/firebase_data.json` غير موجود** | `ls -la /opt/linasbot/data/firebase_data.json` |
| 4 | **ملفات `data/` ناقصة** (price_list, style_guide, knowledge_base) | `ls -la /opt/linasbot/data/*.txt` |
| 5 | **خطأ في الـ import** (مكتبة أو module) | تشغيل `python main.py` يدوياً ورؤية الـ traceback |
| 6 | **Port 8003 مستخدم** | `sudo lsof -i :8003` أو `sudo ss -tlnp \| grep 8003` |
| 7 | **`WorkingDirectory` خاطئ** | التأكد أن `/opt/linasbot` يحتوي `main.py` |
| 8 | **مسار Python أو venv خاطئ** | `ls -la /opt/linasbot/venv/bin/python` |
| 9 | **صلاحيات الملفات** | `ls -la /opt/linasbot/` و `stat /opt/linasbot/data/` |
| 10 | **FFMPEG_PATH خاطئ** | `ls -la $(grep FFMPEG_PATH /opt/linasbot/.env \| cut -d= -f2)` |

## 4️⃣ أوامر إعادة التحميل

```bash
sudo systemctl daemon-reload
sudo systemctl restart linasbot
sudo journalctl -u linasbot -f
```

## 5️⃣ systemd service (النسخة المستخدمة)

```ini
[Unit]
Description=Linas Laser AI Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/linasbot
ExecStart=/opt/linasbot/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/linasbot.log
StandardError=append:/var/log/linasbot.error.log

EnvironmentFile=-/opt/linasbot/.env
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
```

**ملاحظة:** التطبيق يعتمد على `python main.py` لأنه يشغّل `initialize_firestore()` و `load_bot_assets()` قبل uvicorn. استخدام `gunicorn main:app` مباشرة لن ينفّذ هذا الكود.
