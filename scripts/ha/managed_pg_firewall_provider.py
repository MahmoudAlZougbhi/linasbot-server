"""Closed DigitalOcean projection used by the Managed PG firewall transaction."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from http.client import HTTPMessage
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import Request

if TYPE_CHECKING:
    from scripts.ha import managed_pg_firewall_authority as authority
elif __package__:
    from . import managed_pg_firewall_authority as authority
else:
    import managed_pg_firewall_authority as authority

FirewallContractError = authority.FirewallContractError

COMMAND_TIMEOUT_SECONDS = 45
MAX_PROVIDER_BYTES = 1 << 20
PROVIDER_API_URL = "https://api.digitalocean.com/v2"
ALLOWED_RULE_TYPES = frozenset({"app", "droplet", "ip_addr", "k8s", "tag"})
RULE_KEYS = frozenset({"uuid", "cluster_uuid", "type", "value", "created_at", "description"})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        return None


def _api_request(method: str, path: str, body: Mapping[str, object] | None = None) -> object:
    if method not in {"GET", "PUT"} or not path.startswith("/v2/") or "?" in path or ".." in path:
        raise FirewallContractError("DigitalOcean API request authority is invalid")
    token = os.environ.get("DIGITALOCEAN_ACCESS_TOKEN", "")
    if len(token) < 32 or any(ord(character) < 33 or ord(character) == 127 for character in token):
        raise FirewallContractError("DigitalOcean access authority is missing or invalid")
    data = None if body is None else json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "linas-managed-pg-firewall-v1",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{PROVIDER_API_URL.removesuffix('/v2')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=COMMAND_TIMEOUT_SECONDS) as response:
            status = int(response.status)
            final_url = response.geturl()
            payload = response.read(MAX_PROVIDER_BYTES + 1)
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise FirewallContractError("DigitalOcean firewall API request failed") from exc
    expected_status = 200 if method == "GET" else 204
    if status != expected_status or final_url != request.full_url or len(payload) > MAX_PROVIDER_BYTES:
        raise FirewallContractError("DigitalOcean firewall API response is invalid")
    if method == "PUT":
        if payload:
            raise FirewallContractError("DigitalOcean firewall API response is invalid")
        return None
    return _decode(payload.decode("utf-8"))


def _run_doctl(path: Path, expected_sha256: str, arguments: Sequence[str]) -> str:
    actual_path, actual_sha = authority.secure_executable(str(path), default_name="doctl")
    if actual_path != path or actual_sha != expected_sha256:
        raise FirewallContractError("doctl executable authority changed")
    token = os.environ.get("DIGITALOCEAN_ACCESS_TOKEN", "")
    if len(token) < 32 or any(ord(character) < 33 or ord(character) == 127 for character in token):
        raise FirewallContractError("DigitalOcean access authority is missing or invalid")
    environment = {
        "DIGITALOCEAN_ACCESS_TOKEN": token,
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }
    try:
        result = subprocess.run(
            [str(path), "--api-url", PROVIDER_API_URL, *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FirewallContractError("DigitalOcean firewall command failed") from exc
    if result.returncode != 0 or len(result.stdout.encode("utf-8")) > MAX_PROVIDER_BYTES:
        raise FirewallContractError("DigitalOcean firewall command failed")
    return result.stdout


def _decode(raw: str) -> object:
    try:
        return json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FirewallContractError("provider firewall response is unreadable") from exc


def _read_rules_once(cluster_id: str) -> list[dict[str, str]]:
    return authority.normalize_rules(
        _api_request("GET", f"/v2/databases/{cluster_id}/firewall"),
        cluster_id=cluster_id,
        allowed_types=ALLOWED_RULE_TYPES,
        allowed_keys=RULE_KEYS,
    )


def read_rules_stable(cluster_id: str) -> list[dict[str, str]]:
    first = _read_rules_once(cluster_id)
    second = _read_rules_once(cluster_id)
    if first != second:
        raise FirewallContractError("provider firewall changed between verification reads")
    return first


def _read_tag_members_once(path: Path, expected_sha256: str, tag: str) -> list[str]:
    raw = _run_doctl(path, expected_sha256, ["compute", "droplet", "list", "--tag-name", tag, "-o", "json"])
    decoded = _decode(raw)
    if not isinstance(decoded, list):
        raise FirewallContractError("provider tag membership response is invalid")
    members: list[str] = []
    for row in decoded:
        if not isinstance(row, dict) or not isinstance(row.get("id"), int) or row["id"] < 1:
            raise FirewallContractError("provider tag member identity is invalid")
        tags = row.get("tags")
        if not isinstance(tags, list) or tag not in tags or any(not isinstance(value, str) for value in tags):
            raise FirewallContractError("provider tag member projection is invalid")
        members.append(str(row["id"]))
    if len(members) != len(set(members)):
        raise FirewallContractError("provider tag membership contains a duplicate")
    return sorted(members, key=int)


def read_tag_members_stable(path: Path, expected_sha256: str, tag: str) -> list[str]:
    first = _read_tag_members_once(path, expected_sha256, tag)
    second = _read_tag_members_once(path, expected_sha256, tag)
    if first != second:
        raise FirewallContractError("provider tag membership changed between verification reads")
    return first


def replace_rules(
    cluster_id: str,
    rules: Sequence[Mapping[str, str]],
) -> None:
    payload: list[dict[str, str]] = []
    for rule in rules:
        item = {"type": rule["type"], "value": rule["value"]}
        if "description" in rule:
            item["description"] = rule["description"]
        payload.append(item)
    _api_request("PUT", f"/v2/databases/{cluster_id}/firewall", {"rules": payload})
