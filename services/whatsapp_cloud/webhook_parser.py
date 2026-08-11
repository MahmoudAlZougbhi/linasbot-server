"""Parse Meta WhatsApp Cloud webhook payloads with schema narrowing (unknown → typed)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from services.whatsapp_cloud.types import EventKind, ParsedCloudEvent


def _as_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def parse_whatsapp_cloud_payload(payload: object) -> list[ParsedCloudEvent]:
    """Validate and extract Cloud events. Reject non-WABA objects."""

    root = _as_dict(payload)
    if root is None:
        return []
    obj = str(root.get("object") or "").strip().lower()
    if obj not in {"whatsapp_business_account", "whatsapp"}:
        return []

    events: list[ParsedCloudEvent] = []
    for entry in _as_list(root.get("entry")):
        entry_d = _as_dict(entry)
        if entry_d is None:
            continue
        waba_id = str(entry_d.get("id") or "").strip()
        for change in _as_list(entry_d.get("changes")):
            change_d = _as_dict(change)
            if change_d is None:
                continue
            field = str(change_d.get("field") or "").strip()
            value = _as_dict(change_d.get("value")) or {}
            metadata = _as_dict(value.get("metadata")) or {}
            phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            contacts = _as_list(value.get("contacts"))
            profile_name = ""
            if contacts:
                c0 = _as_dict(contacts[0]) or {}
                profile = _as_dict(c0.get("profile")) or {}
                profile_name = str(profile.get("name") or "")

            if field in {"smb_message_echoes", "message_echoes"}:
                for echo in _as_list(value.get("message_echoes") or value.get("messages")):
                    echo_d = _as_dict(echo)
                    if echo_d is None:
                        continue
                    mid = str(echo_d.get("id") or "").strip()
                    to = str(echo_d.get("to") or echo_d.get("recipient_id") or "").strip()
                    if not mid:
                        mid = (
                            "echo_"
                            + hashlib.sha256(json.dumps(echo_d, sort_keys=True, default=str).encode()).hexdigest()[:32]
                        )
                    events.append(
                        ParsedCloudEvent(
                            event_kind="smb_message_echoes",
                            event_key=f"echo:{mid}",
                            waba_id=waba_id,
                            phone_number_id=phone_number_id,
                            customer_wa_id=to,
                            provider_message_id=mid,
                            message_type=str(echo_d.get("type") or "text"),
                            text_body="",  # never feed echoes to AI; body not retained for AI
                            profile_name=profile_name,
                            raw_change_field=field,
                            meta={"is_echo": True},
                        )
                    )
                continue

            if field in {"history", "smb_app_state_sync"}:
                kind: EventKind = "history" if field == "history" else "smb_app_state_sync"
                basis = json.dumps(
                    {"waba": waba_id, "field": field, "value_keys": sorted(value.keys())}, sort_keys=True
                )
                events.append(
                    ParsedCloudEvent(
                        event_kind=kind,
                        event_key=f"{kind}:{waba_id}:{hashlib.sha256(basis.encode()).hexdigest()[:24]}",
                        waba_id=waba_id,
                        phone_number_id=phone_number_id,
                        raw_change_field=field,
                        meta={"value_keys": sorted(str(k) for k in value.keys())},
                    )
                )
                continue

            if field in {"message_template_status_update", "account_update", "phone_number_quality_update"}:
                kind_map = {
                    "message_template_status_update": "template",
                    "account_update": "account_update",
                    "phone_number_quality_update": "phone_quality",
                }
                kind = kind_map[field]  # type: ignore[assignment]
                basis = json.dumps(value, sort_keys=True, default=str)[:2000]
                events.append(
                    ParsedCloudEvent(
                        event_kind=kind,  # type: ignore[arg-type]
                        event_key=f"{kind}:{waba_id}:{hashlib.sha256(basis.encode()).hexdigest()[:24]}",
                        waba_id=waba_id,
                        phone_number_id=phone_number_id,
                        raw_change_field=field,
                    )
                )
                continue

            # statuses
            for status_row in _as_list(value.get("statuses")):
                st = _as_dict(status_row)
                if st is None:
                    continue
                mid = str(st.get("id") or "").strip()
                recipient = str(st.get("recipient_id") or "").strip()
                status = str(st.get("status") or "").strip()
                if not mid:
                    continue
                events.append(
                    ParsedCloudEvent(
                        event_kind="status",
                        event_key=f"status:{mid}:{status}",
                        waba_id=waba_id,
                        phone_number_id=phone_number_id,
                        customer_wa_id=recipient,
                        provider_message_id=mid,
                        status=status,
                        raw_change_field=field or "messages",
                    )
                )

            # inbound customer messages
            for msg in _as_list(value.get("messages")):
                msg_d = _as_dict(msg)
                if msg_d is None:
                    continue
                mid = str(msg_d.get("id") or "").strip()
                sender = str(msg_d.get("from") or "").strip()
                mtype = str(msg_d.get("type") or "text").strip()
                if not mid or not sender:
                    continue
                text_body = ""
                media_id = ""
                media_mime = ""
                if mtype == "text":
                    text_d = _as_dict(msg_d.get("text")) or {}
                    text_body = str(text_d.get("body") or "")
                elif mtype in {"image", "audio", "video", "document", "sticker"}:
                    media = _as_dict(msg_d.get(mtype)) or {}
                    media_id = str(media.get("id") or "")
                    media_mime = str(media.get("mime_type") or "")
                    text_body = str(media.get("caption") or "")
                elif mtype == "interactive":
                    interactive = _as_dict(msg_d.get("interactive")) or {}
                    button = _as_dict(interactive.get("button_reply")) or {}
                    lst = _as_dict(interactive.get("list_reply")) or {}
                    text_body = str(button.get("title") or lst.get("title") or "")
                elif mtype == "button":
                    button = _as_dict(msg_d.get("button")) or {}
                    text_body = str(button.get("text") or "")
                elif mtype == "reaction":
                    # Represent honestly; do not invoke AI on reactions alone.
                    text_body = ""
                else:
                    mtype = "unsupported"
                    text_body = ""

                events.append(
                    ParsedCloudEvent(
                        event_kind="inbound_message",
                        event_key=f"inbound:{mid}",
                        waba_id=waba_id,
                        phone_number_id=phone_number_id,
                        customer_wa_id=sender,
                        provider_message_id=mid,
                        message_type=mtype,
                        text_body=text_body,
                        media_id=media_id,
                        media_mime=media_mime,
                        profile_name=profile_name,
                        raw_change_field=field or "messages",
                    )
                )
    return events
