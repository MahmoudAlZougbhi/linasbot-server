#!/usr/bin/env bash
# HA shared-state closeout on node02 (mount NFS + identical WA DSN).
# Does NOT deploy app release, merge PR, migrate Requests, or enable BOC.
set -euo pipefail

NODE01_PRIV="10.106.0.3"
DATA_ROOT="/opt/linasbot_data"
REG_DIR="${DATA_ROOT}/meta_registry"
MEDIA_DIR="${DATA_ROOT}/meta_social_post_media"

echo "[ha-share] hostname=$(hostname)"

export DEBIAN_FRONTEND=noninteractive
if ! dpkg -s nfs-common >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y nfs-common
fi

mkdir -p "${DATA_ROOT}"

# Preserve any local registry copy then mount shared
if mountpoint -q "${REG_DIR}"; then
  echo "[ha-share] registry_already_mounted=true"
else
  if [[ -d "${REG_DIR}" ]] && [[ ! -d "${REG_DIR}.local-pre-nfs" ]]; then
    mv "${REG_DIR}" "${REG_DIR}.local-pre-nfs"
    echo "[ha-share] registry_local_moved=true"
  fi
  mkdir -p "${REG_DIR}"
  mount -t nfs4 -o rw,hard,timeo=50,retrans=2 "${NODE01_PRIV}:${REG_DIR}" "${REG_DIR}"
fi

if mountpoint -q "${MEDIA_DIR}"; then
  echo "[ha-share] media_already_mounted=true"
else
  if [[ -d "${MEDIA_DIR}" ]] && [[ ! -d "${MEDIA_DIR}.local-pre-nfs" ]]; then
    mv "${MEDIA_DIR}" "${MEDIA_DIR}.local-pre-nfs" 2>/dev/null || true
  fi
  mkdir -p "${MEDIA_DIR}"
  mount -t nfs4 -o rw,hard,timeo=50,retrans=2 "${NODE01_PRIV}:${MEDIA_DIR}" "${MEDIA_DIR}"
fi

# Persist mounts
FSTAB="/etc/fstab"
for pair in "${REG_DIR}" "${MEDIA_DIR}"; do
  src="${NODE01_PRIV}:${pair}"
  if ! grep -qF "${src}" "${FSTAB}"; then
    echo "${src} ${pair} nfs4 rw,hard,timeo=50,retrans=2,_netdev,nofail 0 0" >> "${FSTAB}"
    echo "[ha-share] fstab_added=${pair}"
  fi
done

mount | grep linasbot_data | sed 's/^/[ha-share] mount /'
ls -la "${REG_DIR}" | sed 's/^/[ha-share] reg /' | head -10

# Identical WA DSN host = node01 private IP (copy user/pass from existing local DSN)
ENV_FILE="/opt/linasbot/.env"
cp -a "${ENV_FILE}" "${ENV_FILE}.bak.ha-share.$(date +%s)"
python3 - <<'PY'
from pathlib import Path
import re
path = Path("/opt/linasbot/.env")
text = path.read_text()
priv = "10.106.0.3"
pat = re.compile(r"^(LINAS_WHATSAPP_DATABASE_URL=)(.*)$", re.M)
m = pat.search(text)
if not m:
    raise SystemExit("missing LINAS_WHATSAPP_DATABASE_URL")
val = m.group(2).strip().strip("\"'")
new = re.sub(r"@(localhost|127\.0\.0\.1)(:\d+)?/", f"@{priv}\\2/", val)
if new == val and f"@{priv}" not in val:
    new = re.sub(r"@[^/@]+/", f"@{priv}/", val)
path.write_text(pat.sub(lambda mm: mm.group(1) + new, text, count=1))
from urllib.parse import urlparse
u = urlparse(new.replace("postgresql+psycopg2", "postgresql"))
print(f"[ha-share] wa_dsn_host={u.hostname} port={u.port} db={u.path}")
PY

# Prove PG reachability (no secret print)
python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlparse, unquote
import os, subprocess
raw = None
for line in Path("/opt/linasbot/.env").read_text().splitlines():
    if line.startswith("LINAS_WHATSAPP_DATABASE_URL="):
        raw = line.split("=", 1)[1].strip().strip("\"'")
        break
assert raw
u = urlparse(raw.replace("postgresql+psycopg2", "postgresql"))
os.environ["PGPASSWORD"] = unquote(u.password or "")
r = subprocess.run(
    ["psql", "-h", u.hostname, "-p", str(u.port or 5432), "-U", u.username,
     "-d", u.path.lstrip("/"), "-tAc", "SELECT current_database()"],
    capture_output=True, text=True,
)
print(f"[ha-share] psql_from_node02_ok={r.returncode==0} out={(r.stdout or r.stderr).strip()[:80]}")
if r.returncode != 0:
    raise SystemExit(1)
PY

# Prove shared registry write visibility
python3 - <<'PY'
from pathlib import Path
import time, json, hashlib
p = Path("/opt/linasbot_data/meta_registry/registry.json")
assert p.exists(), "shared registry missing"
raw = p.read_bytes()
print(f"[ha-share] shared_registry_bytes={len(raw)} sha16={hashlib.sha256(raw).hexdigest()[:16]}")
probe = Path("/opt/linasbot_data/meta_registry/.ha_share_probe")
probe.write_text(f"node02 {time.time()}\n")
print("[ha-share] registry_probe_write=ok")
media = Path("/opt/linasbot_data/meta_social_post_media")
assert media.exists()
(media / ".ha_share_probe").write_text(f"node02 {time.time()}\n")
print("[ha-share] media_probe_write=ok")
PY

systemctl restart linasbot
sleep 2
systemctl is-active linasbot | sed 's/^/[ha-share] linasbot=/'
curl -sS -m 8 http://127.0.0.1:8003/api/health | sed 's/^/[ha-share] health /'
echo "[ha-share] DONE node02"
