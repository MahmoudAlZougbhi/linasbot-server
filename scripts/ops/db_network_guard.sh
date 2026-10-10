#!/bin/sh
# Refuse a database or VPC change unless the live site is healthy right now.
# A private-host switch still requires a successful test connection that does
# not edit /opt/linasbot/.env. This script only checks the public health URL.
set -eu
url="${HEALTH_URL:-https://linasaibot.com/api/health}"
polls="${POLL_COUNT:-15}"
i=0
while [ "$i" -lt "$polls" ]; do
  code=$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "$url" || echo 000)
  echo "$(date +%s) $code"
  if [ "$code" != "200" ]; then
    echo "guard_failed poll=$code"
    exit 1
  fi
  i=$((i + 1))
  sleep 2
done
echo "guard_ok polls=$polls"
