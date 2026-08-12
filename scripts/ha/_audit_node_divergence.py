#!/usr/bin/env python3
"""Redacted multi-node HA divergence audit (run on each app node)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def redact_url(v: str) -> str:
    if "://" not in v:
        return v[:80]
    try:
        u = urlparse(v.replace("postgresql+psycopg2", "postgresql"))
        host = u.hostname or ""
        if u.port:
            host = f"{host}:{u.port}"
        if u.username:
            host = f"{u.username}:***@{host}"
        return urlunparse((u.scheme, host, u.path, "", "", ""))
    except Exception as exc:  # noqa: BLE001
        return f"<parse_err {exc}> scheme={v.split('://', 1)[0]}"


def load_env(path: Path) -> dict[str, str]:
    keys: dict[str, str] = {}
    if not path.exists():
        return keys
    for line in path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        keys[k.strip()] = v.strip().strip("\"'")
    return keys


def main() -> int:
    print(f"hostname={subprocess.getoutput('hostname')}")
    print(f"public_ip={subprocess.getoutput('curl -sS -m 3 https://ifconfig.me || true')}")
    keys = load_env(Path("/opt/linasbot/.env"))
    interesting = [
        "LINAS_WHATSAPP_DATABASE_URL",
        "DATABASE_URL",
        "REDIS_URL",
        "RATE_LIMIT_REDIS_URL",
        "LINAS_REQUIRE_REDIS",
        "DATA_ROOT",
        "PUBLIC_URL",
        "RATE_LIMIT_BACKEND",
    ]
    for k in interesting:
        v = keys.get(k, "")
        if not v:
            hits = [kk for kk in keys if k.lower() in kk.lower()]
            print(f"{k}=MISSING fuzzy_keys={hits}")
            continue
        print(f"{k}={redact_url(v) if '://' in v else v}")

    print("pg_listen=" + subprocess.getoutput("ss -lnt | grep -E ':5432|:5433' || true"))
    reg = Path("/opt/linasbot_data/meta_registry/registry.json")
    print(f"meta_registry_exists={reg.exists()}")
    if reg.exists():
        st = reg.stat()
        raw = json.loads(reg.read_text())
        print(
            "registry "
            f"bytes={st.st_size} bindings={len(raw.get('bindings', {}))} "
            f"creds={len(raw.get('credentials', {}))} "
            f"oauth={len(raw.get('oauth_states', {}))} mtime={st.st_mtime}"
        )
        # fingerprint without secrets
        binding_ids = sorted(raw.get("bindings", {}).keys())
        print(f"binding_ids_sha16={__import__('hashlib').sha256(','.join(binding_ids).encode()).hexdigest()[:16]}")
    media = Path("/opt/linasbot_data/meta_social_post_media")
    print(f"media_root_exists={media.exists()}")
    if media.exists():
        files = list(media.rglob("*"))
        file_count = sum(1 for p in files if p.is_file())
        print(f"media_files={file_count} media_dirs={sum(1 for p in files if p.is_dir())}")
    print("git_head=" + subprocess.getoutput("git -C /opt/linasbot rev-parse --short HEAD 2>/dev/null || true"))
    print("linasbot=" + subprocess.getoutput("systemctl is-active linasbot || true"))
    print("nginx=" + subprocess.getoutput("systemctl is-active nginx || true"))
    # readiness snippet
    ready = subprocess.getoutput("curl -sS -m 8 http://127.0.0.1:8003/api/ready || true")
    if ready:
        try:
            j = json.loads(ready)
            print(
                "ready "
                f"ok={j.get('ok')} redis_reachable={j.get('checks', {}).get('redis_reachable') or j.get('redis_reachable')} "
                f"keys={list(j.keys())[:12]}"
            )
            # print compact checks of interest
            checks = j.get("checks") if isinstance(j.get("checks"), dict) else j
            for needle in ("redis", "postgres", "whatsapp", "meta", "data_root", "job_queue", "production"):
                for ck, cv in (checks or {}).items():
                    if needle in str(ck).lower():
                        print(
                            f"ready_check {ck}={cv if not isinstance(cv, dict) else {k: cv.get(k) for k in list(cv)[:6]}}"
                        )
        except Exception:
            print(f"ready_raw_prefix={ready[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
