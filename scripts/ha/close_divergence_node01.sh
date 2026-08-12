#!/usr/bin/env bash
# HA shared-state closeout on node01 (WA PG private + NFS exports).
# Does NOT deploy app release, merge PR, migrate Requests, or enable BOC.
set -euo pipefail

NODE01_PRIV="10.106.0.3"
NODE02_PRIV="10.106.0.4"
VPC_CIDR="10.106.0.0/20"
DATA_ROOT="/opt/linasbot_data"
REG_DIR="${DATA_ROOT}/meta_registry"
MEDIA_DIR="${DATA_ROOT}/meta_social_post_media"
EXPORTS="/etc/exports"
PG_CONF_DIR="$(sudo -u postgres psql -tAc 'SHOW config_file' | xargs dirname)"

echo "[ha-share] hostname=$(hostname) priv=${NODE01_PRIV}"

mkdir -p "${REG_DIR}" "${MEDIA_DIR}"
chmod 755 "${DATA_ROOT}" "${MEDIA_DIR}"
chmod 700 "${REG_DIR}"
chown root:root "${REG_DIR}" "${MEDIA_DIR}"

# --- PostgreSQL: listen on private VPC + allow node02 ---
CONF="${PG_CONF_DIR}/postgresql.conf"
HBA="${PG_CONF_DIR}/pg_hba.conf"
cp -a "${CONF}" "${CONF}.bak.ha-share.$(date +%s)"
cp -a "${HBA}" "${HBA}.bak.ha-share.$(date +%s)"

if grep -qE '^\s*listen_addresses\s*=' "${CONF}"; then
  sed -i -E "s|^[[:space:]]*listen_addresses[[:space:]]*=.*|listen_addresses = 'localhost,${NODE01_PRIV}'|" "${CONF}"
else
  echo "listen_addresses = 'localhost,${NODE01_PRIV}'" >> "${CONF}"
fi

MARKER="# linas-ha-share-node02"
if ! grep -qF "${MARKER}" "${HBA}"; then
  cat >> "${HBA}" <<EOF

${MARKER}
# Allow Linas app peer (node02) over VPC only — scram
host    linas_whatsapp    linas_whatsapp    ${NODE02_PRIV}/32    scram-sha-256
host    linas_whatsapp    linas_whatsapp    ${NODE01_PRIV}/32    scram-sha-256
EOF
fi

ufw allow from "${NODE02_PRIV}" to any port 5432 proto tcp comment "linas-ha-wa-pg-node02" || true
# NFS/RPC + full VPC allow for peer (mountd uses dynamic ports)
ufw allow from "${NODE02_PRIV}" comment "linas-ha-node02-vpc" || true
# LB health checks hit app :8003 from VPC only (no public Anywhere)
ufw allow from "${VPC_CIDR}" to any port 8003 proto tcp comment "linas-ha-lb-hc-vpc" || true
ufw status | sed -n '1,40p' | sed 's/^/[ha-share] ufw /'

systemctl reload postgresql || systemctl restart postgresql
sleep 1
ss -lnt | grep 5432 | sed 's/^/[ha-share] pg_listen /'
sudo -u postgres psql -tAc "SHOW listen_addresses;" | sed 's/^/[ha-share] listen_addresses=/'

# --- NFS: export registry only (media is legacy; Create Post disabled — no Spaces) ---
export DEBIAN_FRONTEND=noninteractive
if ! dpkg -s nfs-kernel-server >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y nfs-kernel-server
fi
mkdir -p "${MEDIA_DIR}"
echo "legacy-local $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${MEDIA_DIR}/.legacy_removed"

NFS_MARKER="# linas-ha-share"
TMP_EXP="$(mktemp)"
if [[ -f "${EXPORTS}" ]]; then
  # drop previous linas-ha-share block
  awk -v m="${NFS_MARKER}" '
    $0 ~ m {skip=1; next}
    skip && /^[^#]/ && NF {skip=0}
    skip && /^$/ {next}
    skip {next}
    {print}
  ' "${EXPORTS}" > "${TMP_EXP}" || cp "${EXPORTS}" "${TMP_EXP}"
else
  : > "${TMP_EXP}"
fi
cat >> "${TMP_EXP}" <<EOF
${NFS_MARKER}
${REG_DIR} ${NODE02_PRIV}(rw,sync,no_subtree_check,no_root_squash)
EOF
mv "${TMP_EXP}" "${EXPORTS}"
exportfs -ra
systemctl enable --now nfs-server
exportfs -v | sed 's/^/[ha-share] export /'
# Prefer VPC-only :8003 (LB HC). Public Anywhere is removed by harden_port_8003.sh.
ufw allow from "${VPC_CIDR}" to any port 8003 proto tcp comment "linas-ha-lb-hc-vpc" || true
ufw status | grep 8003 | sed 's/^/[ha-share] ufw8003 /' || true

# --- Point node01 DSN at private IP (identical DSN as node02 will use) ---
ENV_FILE="/opt/linasbot/.env"
cp -a "${ENV_FILE}" "${ENV_FILE}.bak.ha-share.$(date +%s)"
python3 - <<'PY'
from pathlib import Path
import re
path = Path("/opt/linasbot/.env")
text = path.read_text()
priv = "10.106.0.3"

def rewrite(key: str, content: str) -> str:
    pat = re.compile(rf"^({re.escape(key)}=)(.*)$", re.M)
    m = pat.search(content)
    if not m:
        return content
    val = m.group(2).strip().strip("\"'")
    # only rewrite host for WA URL
    if "://" not in val:
        return content
    # replace 127.0.0.1 / localhost host
    new = re.sub(r"@(localhost|127\.0\.0\.1)(:\d+)?/", f"@{priv}\\2/", val)
    if new == val and f"@{priv}" not in val:
        # generic host replace between @ and /
        new = re.sub(r"@[^/@]+/", f"@{priv}/", val)
    return pat.sub(lambda mm: mm.group(1) + new, content, count=1)

text2 = rewrite("LINAS_WHATSAPP_DATABASE_URL", text)
path.write_text(text2)
print("[ha-share] node01_env_wa_host_updated=true")
PY

# redact-check
python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlparse
for line in Path("/opt/linasbot/.env").read_text().splitlines():
    if line.startswith("LINAS_WHATSAPP_DATABASE_URL="):
        u = urlparse(line.split("=",1)[1].strip().strip("\"'").replace("postgresql+psycopg2","postgresql"))
        print(f"[ha-share] wa_dsn_host={u.hostname} port={u.port} db={u.path}")
PY

systemctl restart linasbot
sleep 2
systemctl is-active linasbot | sed 's/^/[ha-share] linasbot=/'
curl -sS -m 8 http://127.0.0.1:8003/api/health | sed 's/^/[ha-share] health /'
echo "[ha-share] DONE node01"
