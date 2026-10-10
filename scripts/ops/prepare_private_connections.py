#!/usr/bin/env python3
"""Point cluster connections at the database private host in the cluster VPC.

Prints ids and booleans only. Never prints hostnames, URIs, or tokens.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = payload[0]
    if isinstance(payload, dict) and isinstance(payload.get("database"), dict):
        payload = payload["database"]
    if not isinstance(payload, dict):
        raise SystemExit(f"bad json: {path.name}")
    return payload


def _api(method: str, path: str, body: dict[str, str]) -> int:
    token = os.environ["DIGITALOCEAN_ACCESS_TOKEN"]
    request = urllib.request.Request(
        "https://api.digitalocean.com/v2" + path,
        data=json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _run(args: list[str], stdout: Path | None = None) -> subprocess.CompletedProcess[str]:
    if stdout is None:
        return subprocess.run(args, check=False, text=True, capture_output=True)
    with stdout.open("w", encoding="utf-8") as handle:
        return subprocess.run(args, check=False, text=True, stdout=handle, stderr=subprocess.PIPE)


def _private_host(path: Path) -> str:
    row = _load(path)
    host = str(row.get("host") or "")
    uri = str(row.get("uri") or "")
    if "://" in uri:
        host = uri.split("://", 1)[1].split("@")[-1].split("/")[0].split(":")[0]
    return host


def _attach(database_id: str, vpc: str) -> str:
    status = _api("PUT", f"/databases/{database_id}/vpc", {"vpc_uuid": vpc})
    if status in {200, 202, 204}:
        return f"vpc_put={status}"
    status = _api("PUT", f"/databases/{database_id}", {"private_network_uuid": vpc})
    return f"cluster_put={status}"


def _connect(database_id: str, dest: Path) -> bool:
    for _ in range(12):
        result = _run(["doctl", "databases", "connection", database_id, "--private", "-o", "json"], dest)
        if result.returncode == 0 and dest.exists() and _private_host(dest).startswith("private-"):
            return True
        time.sleep(10)
    return False


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: prepare_private_connections.py databases.json cluster.json outdir")
    databases = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    cluster = _load(Path(sys.argv[2]))
    outdir = Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    vpc = str(cluster.get("vpc_uuid") or "")
    cluster_id = str(cluster.get("id") or "")
    if not vpc or not cluster_id:
        raise SystemExit("cluster vpc or id missing")
    print("cluster_vpc", vpc)
    wanted = {"linas-postgres-prod": "pg", "linas-redis-prod": "redis"}
    if not isinstance(databases, list):
        raise SystemExit("database list missing")
    for row in databases:
        if not isinstance(row, dict):
            continue
        kind = wanted.get(str(row.get("name")))
        if not kind:
            continue
        database_id = str(row["id"])
        detail_path = outdir / f"{kind}-detail.json"
        _run(["doctl", "databases", "get", database_id, "-o", "json"], detail_path)
        current = str(_load(detail_path).get("private_network_uuid") or "")
        print(kind, "vpc_match", current == vpc, "private_network_set", bool(current))
        if current != vpc:
            print(kind, _attach(database_id, vpc))
        connected = _connect(database_id, outdir / f"{kind}.json")
        print(kind, "private_host", connected)
        if not connected:
            return 1
        firewall = _run(["doctl", "databases", "firewalls", "append", database_id, "--rule", f"k8s:{cluster_id}"])
        already = "already" in (firewall.stderr or "").lower()
        print(kind, "trusted_k8s", firewall.returncode == 0 or already)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
