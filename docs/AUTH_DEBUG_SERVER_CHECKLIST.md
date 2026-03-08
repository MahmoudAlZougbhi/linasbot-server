# Auth Timeout – Server Verification Checklist

Run these on the production server to verify Firestore/Firebase setup.

## 1. Firebase credentials

```bash
# File exists and is readable
ls -la /opt/linasbot/data/firebase_data.json

# Valid JSON with project_id
head -5 /opt/linasbot/data/firebase_data.json

# Env override (if used)
echo $FIRESTORE_SERVICE_ACCOUNT_KEY_PATH
```

## 2. Firestore connectivity

```bash
# Test reachability to Google APIs (404 on root is normal)
curl -s -o /dev/null -w "%{http_code}\n" https://firestore.googleapis.com

# Test connection with gcloud (if installed)
gcloud auth application-default print-access-token 2>/dev/null || echo "gcloud not configured"
```

## 3. Project ID and env

```bash
# From firebase_data.json
grep project_id /opt/linasbot/data/firebase_data.json

# All auth-related env
env | grep -E "FIREBASE|FIRESTORE|GOOGLE"
```

## 4. Check if Firestore reads hang

```bash
# Watch logs during login attempt (in one terminal)
tail -f /var/log/linasbot.log

# In another: trigger login
curl -X POST http://127.0.0.1:8003/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@lina.com","password":"admin123"}' \
  -w "\nTime: %{time_total}s\n"
```

Look for logs in order:
- `[auth] 1. ENTRY`
- `[auth:get_user_by_email] entry`
- `[auth:get_user_by_email] accessing self.collection`
- `[auth:get_user_by_email] calling query.stream()`
- `[auth:get_user_by_email] query.stream() returned in Xs`

If it hangs between `calling query.stream()` and `query.stream() returned`, the Firestore read is blocking.

## 5. Network / firewall

```bash
# Outbound HTTPS
curl -s -o /dev/null -w "%{http_code}" https://www.google.com

# Firestore API
curl -s -m 5 -o /dev/null -w "%{http_code}" https://firestore.googleapis.com/v1/projects/linas-ai-bot/databases/\(default\)/documents 2>/dev/null || echo "timeout or error"
```
