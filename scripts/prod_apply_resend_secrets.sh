#!/usr/bin/env bash
# Apply Resend runtime secrets to production .env files. Never prints secret values.
# Runtime MUST use SENDING_ONLY key (RESEND_API_KEY). Never write RESEND_API_KEY_FULL.
set -euo pipefail

require_nonempty() {
  local name="$1"
  local value="${!1:-}"
  if [ -z "$value" ]; then
    echo "[resend-apply] missing required env: ${name}" >&2
    exit 1
  fi
}

require_nonempty RESEND_API_KEY
require_nonempty RESEND_WEBHOOK_SECRET

# Reject Full Access key name if mistakenly exported for runtime apply.
if [ -n "${RESEND_API_KEY_FULL:-}" ] && [ "${RESEND_API_KEY}" = "${RESEND_API_KEY_FULL}" ]; then
  echo "[resend-apply] refusing: RESEND_API_KEY equals RESEND_API_KEY_FULL (must be sending-only)" >&2
  exit 1
fi

KEY_LEN="${#RESEND_API_KEY}"
WH_LEN="${#RESEND_WEBHOOK_SECRET}"
if [ "$KEY_LEN" -lt 20 ]; then
  echo "[resend-apply] refusing RESEND_API_KEY: length_too_short len=${KEY_LEN}" >&2
  exit 1
fi
if [ "$WH_LEN" -lt 20 ]; then
  echo "[resend-apply] refusing RESEND_WEBHOOK_SECRET: length_too_short len=${WH_LEN}" >&2
  exit 1
fi
case "${RESEND_API_KEY}" in
  re_*) ;;
  *)
    echo "[resend-apply] refusing RESEND_API_KEY: unexpected_prefix" >&2
    exit 1
    ;;
esac
case "${RESEND_WEBHOOK_SECRET}" in
  whsec_*) ;;
  *)
    echo "[resend-apply] refusing RESEND_WEBHOOK_SECRET: unexpected_prefix" >&2
    exit 1
    ;;
esac

# Non-secret defaults (override via env if needed).
export RESEND_FROM_EMAIL="${RESEND_FROM_EMAIL:-no-reply@linasaibot.com}"
export RESEND_FROM_NAME="${RESEND_FROM_NAME:-Linas AI}"
export RESEND_REPLY_TO="${RESEND_REPLY_TO:-support@linasaibot.com}"
export RESEND_FROM="${RESEND_FROM:-${RESEND_FROM_NAME} <${RESEND_FROM_EMAIL}>}"

# Explicitly clear Full Access from apply environment so it cannot be written.
unset RESEND_API_KEY_FULL || true

python3 - <<'PY'
import hashlib
import os
from pathlib import Path

SECRET_KEYS = ("RESEND_API_KEY", "RESEND_WEBHOOK_SECRET")
PUBLIC_KEYS = (
    "RESEND_FROM_EMAIL",
    "RESEND_FROM_NAME",
    "RESEND_REPLY_TO",
    "RESEND_FROM",
)
FORBIDDEN = ("RESEND_API_KEY_FULL",)

updates = {}
for key in SECRET_KEYS + PUBLIC_KEYS:
    value = (os.environ.get(key) or "").strip()
    if not value:
        raise SystemExit(f"[resend-apply] empty {key}")
    updates[key] = value

fps = {k: hashlib.sha256(updates[k].encode("utf-8")).hexdigest()[:16] for k in SECRET_KEYS}


def upsert(path: Path, updates: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    found = set()
    out = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in FORBIDDEN:
                # Strip Full Access key from runtime env if present.
                continue
            if k in updates:
                out.append(f"{k}={updates[k]}")
                found.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in found:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n")
    os.chmod(path, 0o600)


def verify(path: Path) -> None:
    text = path.read_text()
    env = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    if "RESEND_API_KEY_FULL" in env:
        raise SystemExit(f"[resend-apply] FORBIDDEN key present in {path}")
    for k, expected in updates.items():
        got = env.get(k, "")
        if not got:
            raise SystemExit(f"[resend-apply] missing {k} in {path}")
        if k in SECRET_KEYS:
            got_fp = hashlib.sha256(got.encode("utf-8")).hexdigest()[:16]
            if got_fp != fps[k]:
                raise SystemExit(f"[resend-apply] fp mismatch {k} in {path}")
        elif got != expected:
            raise SystemExit(f"[resend-apply] value mismatch {k} in {path}")
    mode = oct(path.stat().st_mode & 0o777)
    print(f"[resend-apply] updated={path} mode={mode} secrets_fp_ok=true public_ok=true full_access_absent=true")


paths = [Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")]
updated = 0
for path in paths:
    if not path.parent.exists():
        print(f"[resend-apply] skip missing dir for {path}")
        continue
    upsert(path, updates)
    verify(path)
    updated += 1

if updated < 1:
    raise SystemExit("[resend-apply] no .env paths updated")

print(f"[resend-apply] api_key_fp={fps['RESEND_API_KEY']}")
print(f"[resend-apply] api_key_len={len(updates['RESEND_API_KEY'])}")
print(f"[resend-apply] webhook_secret_fp={fps['RESEND_WEBHOOK_SECRET']}")
print(f"[resend-apply] webhook_secret_len={len(updates['RESEND_WEBHOOK_SECRET'])}")
print(f"[resend-apply] from_email={updates['RESEND_FROM_EMAIL']}")
print(f"[resend-apply] from_name={updates['RESEND_FROM_NAME']}")
print(f"[resend-apply] reply_to={updates['RESEND_REPLY_TO']}")
print(f"[resend-apply] scope_note=SENDING_ONLY_runtime_key")
PY

systemctl restart linasbot
sleep 6
systemctl is-active linasbot

python3 - <<'PY'
import hashlib
import os
import subprocess
from pathlib import Path

def load_expected(key: str) -> str:
    for path in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    raise SystemExit(f"[resend-apply] could not read {key} from .env")

expected_api = load_expected("RESEND_API_KEY")
expected_wh = load_expected("RESEND_WEBHOOK_SECRET")
pid = subprocess.check_output(["systemctl", "show", "-p", "MainPID", "--value", "linasbot"], text=True).strip()
if not pid or pid == "0":
    raise SystemExit("[resend-apply] linasbot MainPID unavailable")
raw = Path(f"/proc/{pid}/environ").read_bytes()
env_map = {}
for item in raw.split(b"\0"):
    if b"=" in item:
        k, v = item.split(b"=", 1)
        env_map[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")

def check(key: str, expected: str) -> None:
    loaded = env_map.get(key, "")
    if not loaded:
        raise SystemExit(f"[resend-apply] running process missing {key}")
    if "RESEND_API_KEY_FULL" in env_map:
        raise SystemExit("[resend-apply] running process has FORBIDDEN RESEND_API_KEY_FULL")
    exp_fp = hashlib.sha256(expected.encode("utf-8")).hexdigest()[:16]
    got_fp = hashlib.sha256(loaded.encode("utf-8")).hexdigest()[:16]
    print(f"[resend-apply] process_{key}_present=true fp_match={exp_fp == got_fp}")
    if exp_fp != got_fp:
        raise SystemExit(f"[resend-apply] process fp mismatch for {key}")

print(f"[resend-apply] process_pid={pid}")
check("RESEND_API_KEY", expected_api)
check("RESEND_WEBHOOK_SECRET", expected_wh)
for pub in ("RESEND_FROM_EMAIL", "RESEND_FROM_NAME", "RESEND_REPLY_TO", "RESEND_FROM"):
    print(f"[resend-apply] process_{pub}_present={bool(env_map.get(pub))}")
PY

echo "[resend-apply] SUCCESS"
