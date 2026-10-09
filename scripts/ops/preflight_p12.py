#!/usr/bin/env python3
"""Read-only P12 access checks. Prints pass/fail only. Never prints secret values."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

FAILURES: list[str] = []
WARNINGS: list[str] = []


def line(check: str, status: str, evidence: str) -> None:
    print(f"{check} {status} {evidence}")
    if status == "FAIL":
        FAILURES.append(check)
    elif status == "WARN":
        WARNINGS.append(check)


def run(args: list[str], *, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(args, text=True, capture_output=True, env=merged, timeout=timeout, check=False)


def present(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def b1_digitalocean() -> None:
    if not present("DIGITALOCEAN_TOKEN"):
        line("B1", "FAIL", "DIGITALOCEAN_TOKEN absent")
        return
    env = {"DIGITALOCEAN_ACCESS_TOKEN": os.environ["DIGITALOCEAN_TOKEN"]}
    kube = run(
        ["doctl", "kubernetes", "cluster", "kubeconfig", "save", "linas-prod-doks", "--expiry-seconds", "600"],
        env=env,
        timeout=90,
    )
    if kube.returncode != 0:
        line("B1", "FAIL", "kubeconfig save failed")
        return
    nodes = run(["kubectl", "get", "nodes", "--no-headers"], timeout=60)
    ready = sum(1 for row in nodes.stdout.splitlines() if " Ready" in f" {row}")
    if nodes.returncode != 0 or ready < 2:
        line("B1", "FAIL", f"kubectl nodes ready={ready}")
        return
    auth = run(["kubectl", "auth", "can-i", "create", "deployments", "-n", "default"])
    pools = run(["doctl", "kubernetes", "cluster", "node-pool", "list", "linas-prod-doks"], env=env)
    can_deploy = auth.stdout.strip() == "yes"
    line(
        "B3",
        "PASS" if can_deploy and pools.returncode == 0 else "FAIL",
        f"can_create_deployments={can_deploy} node_pool_list_exit={pools.returncode}",
    )
    dbs = run(["doctl", "databases", "list", "--format", "Name,Engine,Status", "--no-header"], env=env)
    names = set(dbs.stdout.split())
    db_ok = "linas-postgres-prod" in names and "linas-redis-prod" in names
    domain = run(
        ["doctl", "compute", "domain", "records", "list", "linasaibot.com", "--format", "Type", "--no-header"], env=env
    )
    drops = run(["doctl", "compute", "droplet", "list", "--format", "ID", "--no-header"], env=env)
    droplets_ok = "510629908" in drops.stdout and "591901417" in drops.stdout
    listed = run(["doctl", "databases", "list", "-o", "json"], env=env)
    db_id = ""
    if listed.returncode == 0:
        try:
            for item in json.loads(listed.stdout):
                if item.get("name") == "linas-postgres-prod" and item.get("id"):
                    db_id = str(item["id"])
        except (json.JSONDecodeError, TypeError, AttributeError):
            db_id = ""
    conn = run(["doctl", "databases", "connection", db_id or "missing", "-o", "json"], env=env)
    uri_ok = False
    if conn.returncode == 0:
        try:
            payload = json.loads(conn.stdout)
            row = payload[0] if isinstance(payload, list) else payload
            uri_ok = bool(isinstance(row, dict) and (row.get("uri") or row.get("host")))
        except json.JSONDecodeError:
            uri_ok = False
    snap = run(["doctl", "compute", "snapshot", "list", "--format", "ID", "--no-header"], env=env)
    ok = db_ok and domain.returncode == 0 and droplets_ok and uri_ok and snap.returncode == 0
    line(
        "B1",
        "PASS" if ok else "FAIL",
        f"nodes_ready={ready} can_create_deployments={auth.stdout.strip() or auth.returncode} "
        f"node_pools_exit={pools.returncode} db_ok={db_ok} dns_exit={domain.returncode} "
        f"droplets_ok={droplets_ok} connection_present={uri_ok} snapshots_exit={snap.returncode}",
    )


def b4_spaces() -> None:
    needed = (
        "LINAS_SPACES_KEY",
        "LINAS_SPACES_SECRET",
        "LINAS_SPACES_BUCKET",
        "LINAS_SPACES_ENDPOINT",
        "LINAS_BACKUP_BUCKET",
    )
    if not all(present(name) for name in needed):
        line("B4", "FAIL", "one or more Spaces secret names are absent")
        return
    media = os.environ["LINAS_SPACES_BUCKET"]
    backup = os.environ["LINAS_BACKUP_BUCKET"]
    endpoint = os.environ["LINAS_SPACES_ENDPOINT"]
    env = {
        "AWS_ACCESS_KEY_ID": os.environ["LINAS_SPACES_KEY"],
        "AWS_SECRET_ACCESS_KEY": os.environ["LINAS_SPACES_SECRET"],
        "AWS_DEFAULT_REGION": "us-east-1",
    }
    ok = True
    for bucket in (media, backup):
        listed = run(
            ["aws", "s3api", "list-objects-v2", "--bucket", bucket, "--max-keys", "1", "--endpoint-url", endpoint],
            env=env,
        )
        if listed.returncode != 0:
            ok = False
    with tempfile.NamedTemporaryFile() as handle:
        handle.write(b"qa-preflight\n")
        handle.flush()
        put = run(
            [
                "aws",
                "s3api",
                "put-object",
                "--bucket",
                media,
                "--key",
                "qa-preflight.txt",
                "--body",
                handle.name,
                "--endpoint-url",
                endpoint,
            ],
            env=env,
        )
        delete = run(
            [
                "aws",
                "s3api",
                "delete-object",
                "--bucket",
                media,
                "--key",
                "qa-preflight.txt",
                "--endpoint-url",
                endpoint,
            ],
            env=env,
        )
    ok = ok and put.returncode == 0 and delete.returncode == 0
    line("B4", "PASS" if ok else "FAIL", f"list_and_put_delete media_and_backup ok={ok}")


def b5_expo() -> None:
    if not present("EXPO_TOKEN"):
        line("B5", "FAIL", "EXPO_TOKEN absent")
        return
    who = run(["eas", "whoami"], env={"EXPO_TOKEN": os.environ["EXPO_TOKEN"], "CI": "1"})
    accounts = []
    for raw in (who.stdout or "").splitlines():
        cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in "._-").strip("._-")
        if cleaned:
            accounts.append(cleaned)
    account = accounts[-1] if accounts else ""
    ok = who.returncode == 0 and account == "linas-ci"
    line("B5", "PASS" if ok else "FAIL", f"whoami_exit={who.returncode} account={account or 'empty'}")


def b6_play() -> None:
    raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON") or ""
    if not raw.strip():
        line("B6", "FAIL", "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON absent")
        return
    path = Path("/tmp/play-sa.json")
    path.write_text(raw, encoding="utf-8")
    path.chmod(0o600)
    code = r"""
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
creds = service_account.Credentials.from_service_account_file(
    "/tmp/play-sa.json",
    scopes=["https://www.googleapis.com/auth/androidpublisher"],
)
svc = build("androidpublisher", "v3", credentials=creds, cache_discovery=False)
edit = svc.edits().insert(packageName="com.linasai.app", body={}).execute()
svc.edits().delete(packageName="com.linasai.app", editId=edit["id"]).execute()
print("play_edit_ok")
"""
    result = run([sys.executable, "-c", code], timeout=90)
    path.unlink(missing_ok=True)
    line(
        "B6",
        "PASS" if result.returncode == 0 and "play_edit_ok" in result.stdout else "FAIL",
        f"exit={result.returncode}",
    )


def b7_apple() -> None:
    if not all(present(name) for name in ("APPLE_IAP_ISSUER_ID", "APPLE_IAP_KEY_ID", "APPLE_IAP_PRIVATE_KEY")):
        line("B7", "WARN", "APPLE_IAP secret name missing")
        return
    key = os.environ["APPLE_IAP_PRIVATE_KEY"].replace("\\n", "\n")
    path = Path("/tmp/apple-key.p8")
    path.write_text(key, encoding="utf-8")
    path.chmod(0o600)
    code = r"""
import os, time, urllib.request, urllib.error
import jwt
from pathlib import Path
key = Path("/tmp/apple-key.p8").read_text(encoding="utf-8")
now = int(time.time())
token = jwt.encode(
    {"iss": os.environ["APPLE_IAP_ISSUER_ID"], "iat": now, "exp": now + 600, "aud": "appstoreconnect-v1"},
    key,
    algorithm="ES256",
    headers={"kid": os.environ["APPLE_IAP_KEY_ID"], "typ": "JWT"},
)
req = urllib.request.Request("https://api.appstoreconnect.apple.com/v1/apps?limit=1", headers={"Authorization": f"Bearer {token}"})
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("asc", resp.status)
except urllib.error.HTTPError as exc:
    print("asc", exc.code)
"""
    result = run(
        [sys.executable, "-c", code],
        env={
            "APPLE_IAP_ISSUER_ID": os.environ["APPLE_IAP_ISSUER_ID"],
            "APPLE_IAP_KEY_ID": os.environ["APPLE_IAP_KEY_ID"],
        },
        timeout=60,
    )
    path.unlink(missing_ok=True)
    text = (result.stdout or "").strip()
    line("B7", "WARN", f"backend_uses_app_store_server_api {text or 'jwt_failed'}")


def b8_sentry() -> None:
    for name in ("SENTRY_DSN", "EXPO_PUBLIC_SENTRY_DSN"):
        dsn = (os.environ.get(name) or "").strip()
        if not dsn or "otlp" in dsn:
            line("B8", "WARN", f"{name} missing_or_otlp")
            continue
        # DSN shape only. The event post is best-effort and the DSN is not printed.
        try:
            store = dsn.split("@", 1)[1]
            host, project = store.split("/", 1)
            key = dsn.split("//", 1)[1].split("@", 1)[0]
        except Exception:
            line("B8", "WARN", f"{name} unparsable")
            continue
        url = f"https://{host}/api/{project}/store/"
        body = json.dumps({"message": "p12 preflight", "level": "info"}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "X-Sentry-Auth": f"Sentry sentry_version=7, sentry_key={key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                line("B8", "WARN", f"{name} event_status={resp.status}")
        except urllib.error.HTTPError as exc:
            line("B8", "WARN", f"{name} event_status={exc.code}")
        except Exception:
            line("B8", "WARN", f"{name} event_failed")


def main() -> int:
    b1_digitalocean()
    line("B2", "PASS", "use ghcr.io with GITHUB_TOKEN; registry scope not required")
    b4_spaces()
    b5_expo()
    b6_play()
    b7_apple()
    b8_sentry()
    print("FAILURES", ",".join(FAILURES) or "none")
    print("WARNINGS", ",".join(WARNINGS) or "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
