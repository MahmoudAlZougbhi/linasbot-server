#!/usr/bin/env bash
# Restrict app :8003 to DigitalOcean VPC only (LB health checks).
# Removes public Anywhere :8003 rules. Does not touch nginx 80/443.
set -euo pipefail

VPC_CIDR="${VPC_CIDR:-10.106.0.0/20}"
PORT="${PORT:-8003}"

echo "[ha-8003] hostname=$(hostname) vpc=${VPC_CIDR} port=${PORT}"

if ! command -v ufw >/dev/null 2>&1; then
  echo "[ha-8003] ufw missing; skip"
  exit 0
fi

ufw status numbered | sed 's/^/[ha-8003] before /' | head -40

# Ensure VPC allow exists
ufw allow from "${VPC_CIDR}" to any port "${PORT}" proto tcp comment "linas-ha-lb-hc-vpc" || true

# Delete public/open 8003 rules (IPv4 + IPv6) by matching lines; re-run until gone
python3 - <<'PY'
import re, subprocess, time
for _ in range(12):
    out = subprocess.check_output(["ufw", "status", "numbered"], text=True)
    # match [N] 8003/tcp ... Anywhere
    victims = []
    for line in out.splitlines():
        m = re.match(r"\[\s*(\d+)\]\s+8003/tcp\b.*(Anywhere|Anywhere \(v6\))", line)
        if m and "10.106.0.0/20" not in line:
            victims.append(int(m.group(1)))
    if not victims:
        print("[ha-8003] no public 8003 rules left")
        break
    # delete highest index first
    n = max(victims)
    print(f"[ha-8003] deleting rule {n}")
    subprocess.run(["ufw", "--force", "delete", str(n)], check=False)
    time.sleep(0.2)
PY

ufw status numbered | sed 's/^/[ha-8003] after /' | head -40
echo "[ha-8003] DONE"
