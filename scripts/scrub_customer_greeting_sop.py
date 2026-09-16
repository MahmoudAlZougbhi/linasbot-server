"""Dry-run: list published greeting SOP that would leak to customers.

Does not invent clinic facts. Default is print-only.

  python scripts/scrub_customer_greeting_sop.py --tenant linas
  python scripts/scrub_customer_greeting_sop.py --tenant linas --apply

--apply clears unsafe dynamic_messages bodies in DRAFT only. Owner must review
and republish ai_basics + dynamic_messages.
"""

from __future__ import annotations

import argparse
import sys

from services.brain.outbound_safety import is_customer_safe_opener, looks_like_instruction_text


def _load_draft(tenant_id: str, section: str) -> dict:
    try:
        from services.ai_setup.storage import get_draft

        env = get_draft(section, tenant_id=tenant_id, create_default=False)
        payload = getattr(env, "payload", None)
        return dict(payload or {}) if isinstance(payload, dict) else {}
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--apply", action="store_true", help="Clear unsafe greeting bodies in draft")
    args = parser.parse_args(argv)
    tenant_id = str(args.tenant).strip()
    dyn = _load_draft(tenant_id, "dynamic_messages")
    basics = _load_draft(tenant_id, "ai_basics")
    flagged: list[str] = []
    for item in dyn.get("items") or []:
        if not isinstance(item, dict):
            continue
        for lang in ("ar", "en", "fr"):
            body = str(item.get(lang) or "").strip()
            if body and (looks_like_instruction_text(body) or not is_customer_safe_opener(body)):
                flagged.append(f"dynamic_messages id={item.get('id')} lang={lang} chars={len(body)}")
                if args.apply:
                    item[lang] = ""
    for field in ("greeting_behavior", "short_introduction", "advanced_instructions"):
        body = str(basics.get(field) or "").strip()
        if body and looks_like_instruction_text(body):
            flagged.append(f"ai_basics.{field} chars={len(body)}")
            if args.apply and field != "advanced_instructions":
                basics[field] = ""
    for row in flagged:
        print(row)
    if not flagged:
        print("no unsafe greeting SOP found in draft")
        return 0
    if args.apply:
        from services.ai_setup.storage import get_draft, put_draft

        env = get_draft("dynamic_messages", tenant_id=tenant_id, create_default=True)
        put_draft(
            "dynamic_messages",
            payload=dyn,
            if_match=env.etag,
            tenant_id=tenant_id,
            updated_by="ops-greeting-sop-scrub",
        )
        env_ai = get_draft("ai_basics", tenant_id=tenant_id, create_default=True)
        put_draft(
            "ai_basics",
            payload={**dict(env_ai.payload or {}), **basics},
            if_match=env_ai.etag,
            tenant_id=tenant_id,
            updated_by="ops-greeting-sop-scrub",
        )
        print("draft updated; republish from Owner CM before IG sees the change")
    else:
        print("dry-run only; pass --apply to clear unsafe greeting bodies in draft")
    return 0


if __name__ == "__main__":
    sys.exit(main())
