#!/usr/bin/env python3
"""
Local diagnostics for duplicate WhatsApp AI replies (no server required).

Usage:
  cd linasbot-server
  python3 scripts/diagnose_outbound_dedupe.py
  python3 scripts/diagnose_outbound_dedupe.py --user-id +96171112222 --phone 96171112222 --text "hello"

Shows:
  - stable_ai_claim_identity (Firestore ai_turn_claims key basis)
  - outbound_fingerprint (in-memory dedupe)
  - Whether two "different" id strings collapse to the same identity

Set TRACE_AI_OUTBOUND=true on the server to log every successful send with trace_id.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose outbound / AI turn dedupe keys")
    parser.add_argument("--user-id", default="+96171110001", help="WhatsApp user id as seen by webhook")
    parser.add_argument("--phone", default="96171110001", help="phone_number from payload")
    parser.add_argument("--text", default="نفس النص للتجربة", help="sample outbound body")
    parser.add_argument("--mid-a", default="wamid.AAAINBOUND001", help="inbound message id sample A")
    parser.add_argument("--mid-b", default="wamid.BBBINBOUND002", help="inbound message id sample B (different from A)")
    args = parser.parse_args()

    from services.whatsapp_adapters.outbound_text_dedupe import outbound_fingerprint
    from utils.phone_utils import phone_match_key

    # Mirrors services/outbound_turn_idempotency.stable_ai_claim_identity enough for local checks
    # without importing utils.utils (heavy deps). Run inside project venv for full parity tests.
    def stable_ai_claim_identity(user_id: str, phone_number=None):
        raw = phone_number or user_id
        pk = phone_match_key(raw)
        if pk:
            return pk
        pk = phone_match_key(user_id)
        if pk:
            return pk
        return (user_id or "").strip()

    os.environ.setdefault("OUTBOUND_TEXT_DEDUPE_WINDOW_SEC", "90")

    id1 = stable_ai_claim_identity(args.user_id, args.phone)
    id2 = stable_ai_claim_identity(args.user_id.replace("+", ""), f"+{args.phone.lstrip('+')}")
    fp = outbound_fingerprint(args.user_id, args.text, phone_hint=args.phone)

    def claim_doc_id(identity: str, mids: list[str]) -> str:
        mids_s = sorted({str(m).strip() for m in mids if m and str(m).strip()})
        key_basis = f"{identity}\0" + "|".join(mids_s)
        return hashlib.sha256(key_basis.encode("utf-8")).hexdigest()

    print("--- stable_ai_claim_identity ---")
    print(f"  user_id={args.user_id!r} phone={args.phone!r}")
    print(f"  identity_1={id1!r}")
    print(f"  identity_2 (alt formatting)={id2!r}")
    print(f"  same_identity={id1 == id2}")

    print("\n--- outbound_fingerprint (text dedupe) ---")
    print(f"  fingerprint={fp!r}")

    print("\n--- Firestore ai_turn_claims doc_id (sha256 key) ---")
    doc_same = claim_doc_id(id1, [args.mid_a, args.mid_b])
    doc_mid_only = claim_doc_id(id1, [args.mid_a])
    print(f"  mids [A,B] -> {doc_same[:32]}…")
    print(f"  mids [A]   -> {doc_mid_only[:32]}…")

    print("\n--- How to read production logs ---")
    print("  1. [ai-turn] trace_id=... claim=OK  → Firestore claim acquired for this turn")
    print("  2. [ai-turn] trace_id=... claim=DUPLICATE_SKIP → second worker skipped (good)")
    print("  3. claim=SKIPPED(no_inbound_mids) → no WhatsApp message_id; dedupe across pods is weak")
    print("  4. [whatsapp-send] dedupe=global_window → in-memory text dedupe blocked duplicate")
    print("  5. dedupe=same_turn_suppressed → same Python turn tried twice")
    print("  6. Set TRACE_AI_OUTBOUND=true to log every successful send with trace_id")

    async def _async_demo():
        from services.whatsapp_adapters import outbound_text_dedupe as od

        od._cache.clear()
        od._inflight.clear()
        assert await od.should_skip_outbound_text(id1, args.text) is False
        await od.finish_outbound_text_attempt(id1, args.text, True)
        dup = await od.should_skip_outbound_text(id1, args.text)
        print("\n--- outbound_text_dedupe module (async) ---")
        print(f"  second identical send skipped: {dup}")

    asyncio.run(_async_demo())


if __name__ == "__main__":
    main()
