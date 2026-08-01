# Production Auth/API Troubleshooting Checklist

Run these on the **production server** (SSH) when login times out at https://www.linasaibot.com/login.

## 1. Backend Service

```bash
# Is linasbot running?
sudo systemctl status linasbot

# If inactive, check error log
sudo tail -100 /var/log/linasbot.error.log

# Restart if needed
sudo systemctl restart linasbot
```

## 2. Backend Listening on 8003

```bash
# Is port 8003 listening?
ss -tlnp | grep 8003
# or
netstat -tlnp | grep 8003
```

## 3. Direct Backend Test (bypass nginx)

```bash
# From the server itself - does the backend respond?
curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8003/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<YOUR_ADMIN_EMAIL>","password":"<YOUR_ADMIN_PASSWORD>"}'
```

Expected: `200` or `401` (not `000` or timeout).

## 4. Nginx Config

```bash
# Is linasaibot site enabled?
ls -la /etc/nginx/sites-enabled/linasaibot

# Does nginx config pass syntax check?
sudo nginx -t

# What config is loaded for www.linasaibot.com?
grep -r "server_name" /etc/nginx/sites-enabled/
grep -A 10 "location /api" /etc/nginx/sites-enabled/linasaibot
```

Expected: `location /api/` with `proxy_pass http://127.0.0.1:8003;`

## 5. Via Nginx (through proxy)

```bash
# Test through nginx from the server
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://www.linasaibot.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<YOUR_ADMIN_EMAIL>","password":"<YOUR_ADMIN_PASSWORD>"}' \
  -k
```

Expected: `200` or `401`. If timeout/connection refused, nginx or backend is the problem.

## 6. Nginx Access/Error Logs

```bash
# See recent requests to /api
sudo tail -50 /var/log/nginx/access.log | grep /api

# Nginx errors
sudo tail -30 /var/log/nginx/error.log
```

## 7. Firewall (if applicable)

```bash
# Local connections to 127.0.0.1 are typically allowed; check if backend binds to 127.0.0.1 only
ss -tlnp | grep 8003
```

Backend should bind to `0.0.0.0:8003` or `127.0.0.1:8003`. Nginx connects to `127.0.0.1:8003`.

---

## Quick Fix Summary

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `curl 127.0.0.1:8003` times out | Backend down | `sudo systemctl restart linasbot` |
| Direct backend works, nginx test fails | Nginx config / wrong site | Check `sites-enabled`, `nginx -t`, reload nginx |
| CORS error in browser console | www subdomain not in CORS | Already fixed in `modules/core.py` (add www.linasaibot.com) |
| 502 Bad Gateway | Backend crashed during request | Check `/var/log/linasbot.error.log` |
