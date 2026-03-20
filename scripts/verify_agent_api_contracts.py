#!/usr/bin/env python3
"""
One-off backend contract checks for Agent API (appointments/create, branch/move).
Loads .env.local / .env — does not print secrets.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def _parse_simple_env(path: Path) -> dict[str, str]:
    """KEY=value lines only; skips comments and lines dotenv can't handle."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    raw = path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v:
            out[k] = v
    return out


_env_merged = {}
for _p in (ROOT / ".env.local", ROOT / ".env"):
    _env_merged.update(_parse_simple_env(_p))
for _k, _v in _env_merged.items():
    if _k not in os.environ:
        os.environ[_k] = _v

load_dotenv(ROOT / ".env.local", override=False)
load_dotenv(ROOT / ".env", override=False)

BASE = os.getenv("EXTERNAL_API_BASE_URL") or os.getenv("LINASLASER_API_BASE_URL", "")
TOKEN = os.getenv("EXTERNAL_API_TOKEN") or os.getenv("LINASLASER_API_TOKEN")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


async def _post(client: httpx.AsyncClient, path: str, payload: dict) -> tuple[int, dict | str]:
    try:
        r = await client.post(path, json=payload, headers=_headers())
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            try:
                return r.status_code, r.json()
            except json.JSONDecodeError:
                return r.status_code, {"_raw": r.text[:2000]}
        return r.status_code, {"_raw": r.text[:2000]}
    except Exception as e:
        return -1, {"error": str(e)}


async def main() -> int:
    if not TOKEN or not BASE:
        print("SKIP: LINASLASER/EXTERNAL API URL or TOKEN not set in environment.")
        return 2

    base = BASE.rstrip("/") + "/"
    results: dict = {}

    async with httpx.AsyncClient(base_url=base, timeout=60.0) as client:
        # --- Discover ids (read-only) ---
        br = await client.get("branches", headers=_headers())
        sv = await client.get("services", headers=_headers())
        mc = await client.get("machines", headers=_headers())

        def _safe_json(resp: httpx.Response):
            try:
                return resp.json()
            except json.JSONDecodeError:
                return {"_non_json": resp.text[:1500]}

        brj, svj, mcj = _safe_json(br), _safe_json(sv), _safe_json(mc)
        results["preflight"] = {
            "branches_status": br.status_code,
            "services_status": sv.status_code,
            "machines_status": mc.status_code,
        }
        if br.status_code != 200 or sv.status_code != 200 or mc.status_code != 200:
            results["preflight"]["branches_body"] = brj
            results["preflight"]["services_body"] = svj
            results["preflight"]["machines_body"] = mcj
            print(json.dumps({"error": "preflight_failed", "detail": results["preflight"]}, indent=2, default=str))
            return 1

        branches = (brj if isinstance(brj, dict) else {}).get("data") or []
        services = (svj if isinstance(svj, dict) else {}).get("data") or []
        machines = (mcj if isinstance(mcj, dict) else {}).get("data") or []
        branch_id = int(branches[0]["id"]) if branches else 1
        service_id = 1
        for s in services:
            if int(s.get("id", 0)) == 1:
                service_id = 1
                break
        machine_id = int(machines[0]["id"]) if machines else 1

        bp = await client.get("body-parts", params={"service_id": service_id}, headers=_headers())
        body_part_ids: list[int] = []
        if bp.status_code == 200:
            bpj = _safe_json(bp)
            data = (bpj if isinstance(bpj, dict) else {}).get("data") or []
            for row in data[:3]:
                bid = row.get("id") or row.get("body_part_id")
                if bid is not None:
                    try:
                        body_part_ids.append(int(bid))
                    except (TypeError, ValueError):
                        pass
        if not body_part_ids:
            body_part_ids = [1]

        # Non-prod-looking phone; far-future slot to reduce accidental booking if API accepts
        test_phone = "799999991"
        future_date = "2030-06-15 14:00:00"

        payload_parts = {
            "phone": test_phone,
            "service_id": service_id,
            "machine_id": machine_id,
            "branch_id": branch_id,
            "date": future_date,
            "body_parts": [
                {"body_part_id": body_part_ids[0], "session_number": 1},
            ],
        }
        payload_ids = {k: v for k, v in payload_parts.items() if k != "body_parts"}
        payload_ids["body_part_ids"] = body_part_ids[:2] if len(body_part_ids) > 1 else body_part_ids
        payload_both = {**payload_parts, "body_part_ids": payload_ids["body_part_ids"]}

        sc1, body1 = await _post(client, "appointments/create", payload_parts)
        sc2, body2 = await _post(client, "appointments/create", payload_ids)
        sc3, body3 = await _post(client, "appointments/create", payload_both)

        results["appointments_create"] = {
            "A_body_part_ids_only_primary_pdf": {"status": sc2, "body": body2},
            "B_body_parts_only_legacy": {"status": sc1, "body": body1},
            "C_both_fields": {"status": sc3, "body": body3},
            "note": "Interpret success=false with CRM message as accepted schema but business rule failure.",
        }

        move_no_date = {
            "phone": test_phone,
            "from_branch_id": branch_id,
            "to_branch_id": branch_id,  # same branch: minimal move if API allows
            "response": "yes",
        }
        move_with_date = {
            **move_no_date,
            "new_date": "2030-06-20",
        }
        # If from==to is rejected, try 1->2 when both exist
        ids = [int(b["id"]) for b in branches if b.get("id") is not None]
        if len(ids) >= 2:
            a, b = ids[0], ids[1]
            move_no_date = {"phone": test_phone, "from_branch_id": a, "to_branch_id": b, "response": "yes"}
            move_with_date = {**move_no_date, "new_date": "2030-06-20"}

        sc4, body4 = await _post(client, "appointments/branch/move", move_no_date)
        sc5, body5 = await _post(client, "appointments/branch/move", move_with_date)
        results["appointments_branch_move"] = {
            "without_new_date": {"status": sc4, "body": body4},
            "with_new_date": {"status": sc5, "body": body5},
        }

    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
