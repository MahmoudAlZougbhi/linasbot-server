"""Send Comment Rule static resources after the text reply (independent HA purpose)."""

from __future__ import annotations

from typing import Any

from services.cm.resource_attachment import is_customer_visible_resource


async def send_comment_rule_resources(
    *,
    tenant_id: str,
    rule_decision: Any,
    comment_id: str,
    channel: str,
    binding_id: str,
    simulation: bool,
    capture_send: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    atts = list(getattr(rule_decision, "attachments", None) or [])
    visible = [a for a in atts if isinstance(a, dict) and is_customer_visible_resource(a)]
    if not visible:
        return {"ok": True, "sent": [], "skipped": True, "claimed_sent": False}
    if simulation:
        if capture_send is not None:
            for att in visible:
                capture_send.append(
                    {
                        "comment_id": comment_id,
                        "channel": channel,
                        "delivery": "comment_rule_resource",
                        "rule_id": str(getattr(rule_decision, "rule_id", "") or ""),
                        "resource_ref": str(att.get("id") or ""),
                        "resource_type": str(att.get("kind") or "file"),
                    }
                )
        return {"ok": True, "sent": visible, "delivery_result": "simulated", "claimed_sent": False}

    user_data = {
        "tenant_id": tenant_id,
        "_pending_setup_resources": {
            "ok": True,
            "items": [
                {
                    "resource_ref": str(att.get("id") or ""),
                    "resource_type": str(att.get("kind") or "file"),
                    "title": str(att.get("title") or att.get("filename") or ""),
                }
                for att in visible
                if str(att.get("id") or "").strip()
            ],
        },
    }
    from services.customer_reply_v2.setup_resource_outbound import send_pending_setup_resources

    return await send_pending_setup_resources(
        user_data=user_data,
        sender_id=comment_id,
        adapter=None,
        inbound_event_id=None,
        channel=channel,
        binding_id=binding_id,
        capture_send=None,
        purpose="comment_rule_resource",
        recipient_field="comment_id",
    )
