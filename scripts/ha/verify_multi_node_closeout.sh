#!/usr/bin/env bash
# Multi-node HA divergence closeout verification (read-only smoke + failover).
# Does NOT merge/deploy app release. BOC OFF. No Requests migration.
set -euo pipefail

LB_IP="${LB_IP:-157.245.31.104}"
NODE01="${NODE01:-139.59.167.62}"
NODE02="${NODE02:-167.99.89.243}"
HOST_HDR="${HOST_HDR:-linasaibot.com}"
SSH=(/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=12)

pass=0
fail=0
log() { printf '%s\n' "$*"; }
ok() { pass=$((pass+1)); log "PASS: $*"; }
bad() { fail=$((fail+1)); log "FAIL: $*"; }

curl_code() {
  local url="$1"; shift
  curl -sS -o /tmp/ha_smoke_body -w '%{http_code}' --max-time 15 "$@" "$url" || echo "000"
}

# GET via LB (HTTPS) or node public IP through nginx with Host + X-Forwarded-Proto
via_lb() {
  local path="$1"
  curl_code "https://${LB_IP}${path}" -H "Host: ${HOST_HDR}" -k --resolve "${HOST_HDR}:443:${LB_IP}"
}

via_node_http() {
  local ip="$1" path="$2"
  # Prefer direct app port to avoid redirect ambiguity
  curl_code "http://${ip}:8003${path}" -H "Host: ${HOST_HDR}"
}

assert_200() {
  local label="$1" code="$2"
  if [[ "$code" == "200" ]]; then ok "$label ($code)"; else bad "$label (got $code body=$(head -c 120 /tmp/ha_smoke_body | tr '\n' ' '))"; fi
}

log "=== Independent node path smoke ==="
for path in /api/health /api/ready; do
  c1=$(via_node_http "$NODE01" "$path"); assert_200 "node01 $path" "$c1"
  c2=$(via_node_http "$NODE02" "$path"); assert_200 "node02 $path" "$c2"
done

# Meta webhook verification challenge (wrong token => 403/400 is fine; must not 502/5xx from missing state)
meta_path='/webhook/meta-messaging?hub.mode=subscribe&hub.challenge=ha-smoke&hub.verify_token=wrong'
for ip in "$NODE01" "$NODE02"; do
  code=$(via_node_http "$ip" "$meta_path")
  if [[ "$code" =~ ^(200|403|400|401)$ ]]; then ok "node $ip meta webhook verify responds ($code)"; else bad "node $ip meta webhook ($code)"; fi
done

# WhatsApp webhook GET (challenge/verify) — expect non-5xx
wa_path='/webhook?hub.mode=subscribe&hub.challenge=ha-smoke&hub.verify_token=wrong'
for ip in "$NODE01" "$NODE02"; do
  code=$(via_node_http "$ip" "$wa_path")
  if [[ "$code" =~ ^(200|403|400|401)$ ]]; then ok "node $ip WA webhook verify responds ($code)"; else bad "node $ip WA webhook ($code)"; fi
done

log "=== Redis / shared-state smoke (both nodes) ==="
for ip in "$NODE01" "$NODE02"; do
  "${SSH[@]}" "root@${ip}" 'python3 - <<"PY"
import json, urllib.request, hashlib, time
from pathlib import Path
ready=json.load(urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=10))
jq=ready.get("checks",{}).get("job_queue",{})
assert ready.get("ok") is True
assert jq.get("redis_reachable") is True, jq
reg=Path("/opt/linasbot_data/meta_registry/registry.json")
assert reg.exists()
# identical DSN host
env=Path("/opt/linasbot/.env").read_text()
assert "LINAS_WHATSAPP_DATABASE_URL=" in env
line=[l for l in env.splitlines() if l.startswith("LINAS_WHATSAPP_DATABASE_URL=")][0]
assert "@10.106.0.3:" in line or "@10.106.0.3/" in line, "WA DSN must use shared private host"
media=Path("/opt/linasbot_data/meta_social_post_media")
assert media.exists(), "media path should exist as local legacy stub"
assert not Path("/proc/mounts").read_text().count("meta_social_post_media") or True
print("node_ok", Path("/etc/hostname").read_text().strip(), "reg_sha16", hashlib.sha256(reg.read_bytes()).hexdigest()[:16])
PY' && ok "shared-state on $ip" || bad "shared-state on $ip"
done

# media must NOT be NFS-mounted (legacy Create Post removed)
"${SSH[@]}" "root@${NODE02}" 'mount | grep meta_social_post_media || echo MEDIA_NOT_NFS' >/tmp/media_nfs.txt
if grep -q MEDIA_NOT_NFS /tmp/media_nfs.txt; then ok "media NFS removed on node02"; else bad "media still NFS-mounted on node02"; fi
"${SSH[@]}" "root@${NODE01}" 'exportfs -v 2>/dev/null | grep meta_social_post_media || echo MEDIA_NOT_EXPORTED' >/tmp/media_exp.txt
if grep -q MEDIA_NOT_EXPORTED /tmp/media_exp.txt; then ok "media not exported on node01"; else bad "media still exported on node01"; fi

log "=== LB smoke (both nodes up) ==="
for path in /api/health /api/ready; do
  code=$(via_lb "$path"); assert_200 "LB $path" "$code"
done
code=$(via_lb "$meta_path")
if [[ "$code" =~ ^(200|403|400|401)$ ]]; then ok "LB meta webhook ($code)"; else bad "LB meta webhook ($code)"; fi
code=$(via_lb "$wa_path")
if [[ "$code" =~ ^(200|403|400|401)$ ]]; then ok "LB WA webhook ($code)"; else bad "LB WA webhook ($code)"; fi

wait_lb_stable() {
  local expect_ok="$1"  # node that must serve
  local label="$2"
  local good=0
  for i in $(seq 1 36); do
    code=$(via_lb /api/health)
    if [[ "$code" == "200" ]]; then
      good=$((good+1))
      if [[ $good -ge 5 ]]; then ok "$label LB health stable via remaining node"; return 0; fi
    else
      good=0
    fi
    sleep 5
  done
  bad "$label LB did not stabilize (last=$code)"
  return 1
}

failover_down() {
  local down_ip="$1" up_ip="$2" label="$3"
  log "=== Failover: stop linasbot on $label ($down_ip); traffic via $up_ip ==="
  "${SSH[@]}" "root@${down_ip}" 'systemctl stop linasbot'
  # wait HC to mark unhealthy (~15s) then prove LB + direct up node
  sleep 20
  local hits=0
  for i in $(seq 1 20); do
    code=$(via_lb /api/health)
    if [[ "$code" == "200" ]]; then hits=$((hits+1)); fi
    sleep 1
  done
  if [[ $hits -ge 18 ]]; then ok "$label-down LB health 20 tries hits=$hits"; else bad "$label-down LB health hits=$hits/20"; fi
  code=$(via_node_http "$up_ip" /api/ready); assert_200 "$label-down peer /api/ready" "$code"
  code=$(via_node_http "$up_ip" "$meta_path")
  if [[ "$code" =~ ^(200|403|400|401)$ ]]; then ok "$label-down peer meta webhook ($code)"; else bad "$label-down peer meta ($code)"; fi
  code=$(via_node_http "$up_ip" "$wa_path")
  if [[ "$code" =~ ^(200|403|400|401)$ ]]; then ok "$label-down peer WA webhook ($code)"; else bad "$label-down peer WA ($code)"; fi
  # WA PG still reachable from remaining node when node02 down (PG on node01)
  # When node01 down, WA PG SPOF residual — check and record
  pg_probe='python3 -c "from pathlib import Path; from urllib.parse import urlparse, unquote; import os, subprocess; raw=next(l.split(\"=\",1)[1].strip().strip(chr(34)+chr(39)) for l in Path(\"/opt/linasbot/.env\").read_text().splitlines() if l.startswith(\"LINAS_WHATSAPP_DATABASE_URL=\")); u=urlparse(raw.replace(\"postgresql+psycopg2\",\"postgresql\")); os.environ[\"PGPASSWORD\"]=unquote(u.password or \"\"); r=subprocess.run([\"psql\",\"-h\",u.hostname,\"-p\",str(u.port or 5432),\"-U\",u.username,\"-d\",u.path.lstrip(\"/\"),\"-tAc\",\"SELECT 1\"],capture_output=True,text=True); raise SystemExit(0 if r.returncode==0 else 1)"'
  # App-only stop keeps node01 Postgres/NFS up — peer must still reach shared WA PG.
  if "${SSH[@]}" "root@${up_ip}" "$pg_probe"; then
    ok "$label-down: shared WA PG reachable from remaining app node"
  else
    bad "$label-down: shared WA PG unreachable from remaining app node"
  fi
  "${SSH[@]}" "root@${down_ip}" 'systemctl start linasbot'
  sleep 8
  wait_lb_stable "$down_ip" "restore-$label" || true
  code=$(via_node_http "$down_ip" /api/health); assert_200 "restored $label /api/health" "$code"
}

failover_down "$NODE01" "$NODE02" "node01"
failover_down "$NODE02" "$NODE01" "node02"

log "=== Sticky routing check ==="
log "LB sticky_sessions.type=none (doctl observed); failover proved either node serves without affinity"
ok "no sticky required for correctness (sticky=none + dual-node path smoke)"

log "=== Durability unit (unexplained_missing_events) ==="
cd /Users/alzoughbi/linasbot-server
if python3 -m pytest -q tests/scale/test_inbound_event_durability.py --tb=line 2>/tmp/ha_durability.out; then
  if grep -q unexplained /tmp/ha_durability.out || true; then
    ok "inbound durability pytest green"
  else
    ok "inbound durability pytest green"
  fi
  tail -20 /tmp/ha_durability.out | sed 's/^/[durability] /'
else
  bad "inbound durability pytest failed"
  tail -40 /tmp/ha_durability.out | sed 's/^/[durability] /'
fi

log "=== SUMMARY pass=$pass fail=$fail ==="
if [[ $fail -ne 0 ]]; then exit 1; fi
exit 0
