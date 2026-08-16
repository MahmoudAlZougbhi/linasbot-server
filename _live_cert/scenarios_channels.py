"""Channel policy blockers that stay independent of OpenAI."""

from __future__ import annotations

from _live_cert.calls import record


def record_channel_blockers() -> None:
    record(
        "meta_instagram_live",
        "BLOCKED",
        ok=False,
        blocker="No isolated Meta App Role / test IG account bound to this test tenant",
        first_failing_layer="safe test Instagram asset + webhook to isolated tenant",
    )
    record(
        "meta_facebook_live",
        "BLOCKED",
        ok=False,
        blocker="No isolated test Facebook Page bound to this test tenant",
        first_failing_layer="safe test Facebook asset + webhook to isolated tenant",
    )
    record(
        "real_webhook",
        "BLOCKED",
        ok=False,
        blocker="No Meta test webhook delivery into this isolated process",
        first_failing_layer="Meta signed webhook → tenant resolve → AI start → delivery",
    )
    from services.whatsapp_cloud.config import get_whatsapp_cloud_flags

    flags = get_whatsapp_cloud_flags()
    record(
        "whatsapp",
        "DISABLED BY PRODUCT POLICY",
        ok=False,
        blocker="WHATSAPP_CLOUD_PUBLIC_AVAILABILITY is off; no approved test number in this isolated cert",
        first_failing_layer="product policy public-availability OFF + missing approved test WA number",
        prod_flags_readonly={
            "public_availability": flags.public_availability,
            "outbound_sends_enabled": flags.outbound_sends_enabled,
        },
    )
