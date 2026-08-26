"""Token and Graph coexistence proof for Embedded Signup completion."""

from __future__ import annotations

from typing import Any

from services.whatsapp_cloud.embedded_signup_session import (
    SignupAssetError,
    phone_row_proves_coexistence,
    select_proven_coexistence_phone,
)
from services.whatsapp_cloud.graph_client import (
    WhatsAppGraphError,
    fetch_business_phone_number,
    fetch_waba_phone_numbers,
)


def _raise_graph_as_signup(exc: WhatsAppGraphError) -> None:
    if exc.http_status in {403, 400} or str(exc.code) in {"waba_phones_failed", "phone_lookup_failed"}:
        raise SignupAssetError("meta_advanced_access_required", "Meta rejected WhatsApp asset lookup")
    raise SignupAssetError(str(exc.code), "WhatsApp Graph lookup failed")


async def prove_coexistence_phone(
    *,
    access_token: str,
    waba_id: str,
    phone_number_id: str | None,
) -> dict[str, Any]:
    """Enumerate WABA phones and require unique Graph coexistence proof."""

    try:
        phones = await fetch_waba_phone_numbers(access_token=access_token, waba_id=waba_id)
    except WhatsAppGraphError as exc:
        _raise_graph_as_signup(exc)
        raise
    try:
        matched = select_proven_coexistence_phone(
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            phones=phones,
        )
    except SignupAssetError:
        raise
    live_id = str(matched.get("id") or "")
    try:
        live = await fetch_business_phone_number(access_token=access_token, phone_number_id=live_id)
    except WhatsAppGraphError as exc:
        _raise_graph_as_signup(exc)
        raise
    merged = {**matched, **live, "id": live_id}
    if not phone_row_proves_coexistence(merged):
        raise SignupAssetError(
            "coexistence_not_proven",
            "Graph did not prove the phone is on WhatsApp Business App Cloud API",
        )
    return merged
