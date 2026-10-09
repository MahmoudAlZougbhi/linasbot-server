#!/bin/sh
# Poll /api/health every 2 seconds. Stops after POLL_SECONDS (default 30).
url="${HEALTH_URL:-https://linasaibot.com/api/health}"
seconds="${POLL_SECONDS:-30}"
end=$(( $(date +%s) + seconds ))
while [ "$(date +%s)" -lt "$end" ]; do
  start=$(date +%s)
  code=$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "$url" || echo 000)
  now=$(date +%s)
  echo "$now $code $((now - start))"
  sleep 2
done
