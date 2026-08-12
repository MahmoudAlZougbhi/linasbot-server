"""Secured customer-AI tool: create Customer Request after confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.requests.capture import (
    appointment_pending_confirmation_message,
    is_public_comment_channel,
    normalize_source_channel,
)
from services.requests.config_loader import (
    load_published_requests_config,
    published_configuration_version,
    requests_capture_active,
)
from services.requests.constants import REQUEST_TYPES, SOURCE_CHANNELS
from services.requests.schemas import RequestCreateBody
from services.requests.service import CustomerRequestsError, CustomerRequestsService

CREATE_CUSTOMER_REQUEST_TOOL_NAME = "create_customer_request"


def appointment_pending_wording(language: str | None = None) -> str:
    """Alias for capture helper — appointment is preference until owner Confirm."""
    return appointment_pending_confirmation_message(language)


CREATE_CUSTOMER_REQUEST_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": CREATE_CUSTOMER_REQUEST_TOOL_NAME,
        "description": (
            "Create a structured customer request ONLY after the customer explicitly confirms "
            "the collected details in this conversation. "
            "For APPOINTMENT: records a preference pending owner confirmation — never claim the "
            "appointment is confirmed. "
            "Never call this from a public comment thread; invite the customer to DM first. "
            "Never invent tenant_id; server binds tenant and conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "request_type": {
                    "type": "string",
                    "enum": list(REQUEST_TYPES),
                    "description": "ORDER | APPOINTMENT | OTHER",
                },
                "customer_confirmed": {
                    "type": "boolean",
                    "description": "Must be true only after explicit customer confirmation.",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Stable unique key for this create attempt (8–128 chars).",
                },
                "title": {"type": "string"},
                "preferred_date": {"type": "string"},
                "preferred_time": {"type": "string"},
                "requested_branch": {"type": "string"},
                "requested_items": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "fulfillment_preference": {"type": "string"},
                "customer_notes": {"type": "string"},
                "customer_name": {"type": "string"},
                "collected_fields": {"type": "object"},
                "configuration_version": {
                    "type": "string",
                    "description": "Published CM version id; server validates against live publish.",
                },
            },
            "required": ["request_type", "customer_confirmed", "idempotency_key"],
        },
    },
}


@dataclass(frozen=True)
class AiToolContext:
    """Server-verified binding — model args cannot override these."""

    tenant_id: str
    source_channel: str
    conversation_id: str | None = None
    source_account_id: str | None = None
    external_customer_id: str | None = None
    platform_username: str | None = None
    customer_display_name: str | None = None
    originating_message_id: str | None = None
    originating_comment_id: str | None = None
    response_language: str = "en"
    # When True, refuse create (public comment must invite DM only).
    public_comment: bool = False


def tools_for_tenant(tenant_id: str | None) -> list[dict[str, Any]]:
    """Expose create tool only when Requests capture is active for the tenant."""
    if not requests_capture_active(tenant_id):
        return []
    return [CREATE_CUSTOMER_REQUEST_TOOL_SCHEMA]


def build_context_from_user_data(
    user_data: dict[str, Any] | None,
    *,
    response_language: str = "en",
) -> AiToolContext | None:
    ud = user_data or {}
    tenant_id = str(ud.get("tenant_id") or ud.get("tenantId") or ud.get("workspace_id") or "").strip()
    if not tenant_id:
        return None
    channel_raw = str(ud.get("channel") or "").strip()
    source = normalize_source_channel(channel_raw) or normalize_source_channel(str(ud.get("source_channel") or ""))
    public = is_public_comment_channel(channel_raw)
    if not source and not public:
        # WhatsApp cloud path often has empty social channel marker.
        if str(ud.get("phone_number") or "").strip() and not str(ud.get("social_sender_id") or "").strip():
            source = "whatsapp_cloud"
    if not source and not public:
        return None
    return AiToolContext(
        tenant_id=tenant_id,
        source_channel=source or "instagram_dm",
        conversation_id=str(ud.get("current_conversation_id") or ud.get("conversation_id") or "") or None,
        source_account_id=str(ud.get("meta_account_id") or ud.get("source_account_id") or "") or None,
        external_customer_id=str(
            ud.get("social_sender_id") or ud.get("external_customer_id") or ud.get("user_id") or ""
        )
        or None,
        platform_username=str(ud.get("platform_username") or ud.get("username") or "") or None,
        customer_display_name=str(ud.get("user_name") or ud.get("name") or ud.get("profile_name") or "") or None,
        originating_message_id=str(ud.get("originating_message_id") or "") or None,
        originating_comment_id=str(ud.get("originating_comment_id") or "") or None,
        response_language=response_language,
        public_comment=public,
    )


def _enabled_types(tenant_id: str) -> set[str]:
    cfg = load_published_requests_config(tenant_id) or {}
    raw = cfg.get("enabled_types") or []
    if not isinstance(raw, list):
        return set()
    return {str(x).strip().upper() for x in raw if str(x).strip()}


def _required_field_ids(tenant_id: str, request_type: str) -> list[str]:
    cfg = load_published_requests_config(tenant_id) or {}
    fields = cfg.get("fields") or []
    if not isinstance(fields, list):
        return []
    required: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        if not field.get("enabled", True):
            continue
        if not field.get("required"):
            continue
        applies = field.get("applies_to") or []
        if applies and request_type not in {str(a).upper() for a in applies}:
            continue
        fid = str(field.get("id") or "").strip()
        if fid:
            required.append(fid)
    return required


def _field_value(args: dict[str, Any], field_id: str) -> Any:
    if field_id in args and args.get(field_id) not in (None, "", [], {}):
        return args.get(field_id)
    raw_collected = args.get("collected_fields")
    collected: dict[str, Any] = raw_collected if isinstance(raw_collected, dict) else {}
    if field_id in collected and collected.get(field_id) not in (None, "", [], {}):
        return collected.get(field_id)
    aliases = {
        "branch": "requested_branch",
        "requested_branch": "requested_branch",
        "date": "preferred_date",
        "preferred_date": "preferred_date",
        "time": "preferred_time",
        "preferred_time": "preferred_time",
        "name": "customer_name",
        "customer_name": "customer_name",
        "items": "requested_items",
        "notes": "customer_notes",
    }
    mapped = aliases.get(field_id)
    if mapped and args.get(mapped) not in (None, "", [], {}):
        return args.get(mapped)
    return None


def execute_create_customer_request(
    args: dict[str, Any] | None,
    ctx: AiToolContext,
    *,
    session: Any,
) -> dict[str, Any]:
    """Validate server-side then create via CustomerRequestsService.

    Ignores any model-supplied tenant_id / conversation_id / source_channel overrides.
    """
    raw = dict(args or {})
    # Security: never trust client/model tenant or channel ownership fields.
    for banned in (
        "tenant_id",
        "source_channel",
        "conversation_id",
        "source_account_id",
        "external_customer_id",
        "phone_normalized",
        "email",
        "delivery_address",
    ):
        raw.pop(banned, None)

    if ctx.public_comment or is_public_comment_channel(ctx.source_channel):
        return {
            "ok": False,
            "error": "PUBLIC_COMMENT_REFUSED",
            "message": "Do not collect PII or create requests on public comments; invite the customer to DM.",
        }

    if not requests_capture_active(ctx.tenant_id):
        return {
            "ok": False,
            "error": "REQUESTS_SETUP_REQUIRED",
            "message": "Requests capture inactive until published configuration",
        }

    if not bool(raw.get("customer_confirmed")):
        return {
            "ok": False,
            "error": "CUSTOMER_CONFIRMATION_REQUIRED",
            "message": "Call only after the customer explicitly confirms the request details.",
        }

    request_type = str(raw.get("request_type") or "").strip().upper()
    if request_type not in REQUEST_TYPES:
        return {"ok": False, "error": "INVALID_REQUEST_TYPE", "message": f"Unsupported type: {request_type}"}

    enabled = _enabled_types(ctx.tenant_id)
    if request_type not in enabled:
        return {
            "ok": False,
            "error": "REQUEST_TYPE_DISABLED",
            "message": f"Type {request_type} is not enabled in published Requests config",
        }

    source_channel = ctx.source_channel.strip().lower()
    if source_channel not in SOURCE_CHANNELS:
        return {"ok": False, "error": "INVALID_SOURCE_CHANNEL", "message": f"Bad channel: {source_channel}"}

    if not ctx.conversation_id:
        return {
            "ok": False,
            "error": "CONVERSATION_REQUIRED",
            "message": "Server conversation binding is required to create a request",
        }

    published = published_configuration_version(ctx.tenant_id)
    cfg_version = str(raw.get("configuration_version") or "").strip() or None
    if cfg_version and published and cfg_version != published:
        return {
            "ok": False,
            "error": "CONFIGURATION_VERSION_MISMATCH",
            "message": "Stale configuration_version; refresh published version and retry",
        }

    for fid in _required_field_ids(ctx.tenant_id, request_type):
        if _field_value(raw, fid) in (None, "", [], {}):
            return {
                "ok": False,
                "error": "REQUIRED_FIELD_MISSING",
                "message": f"Missing required field: {fid}",
                "field": fid,
            }

    idem = str(raw.get("idempotency_key") or "").strip()
    if len(idem) < 8 or len(idem) > 128:
        return {
            "ok": False,
            "error": "INVALID_IDEMPOTENCY_KEY",
            "message": "idempotency_key must be 8–128 characters",
        }

    body = RequestCreateBody(
        request_type=request_type,
        source_channel=source_channel,
        customer_confirmed=True,
        idempotency_key=idem,
        source_account_id=ctx.source_account_id,
        external_customer_id=ctx.external_customer_id,
        platform_username=ctx.platform_username,
        customer_display_name=ctx.customer_display_name,
        customer_name=str(raw.get("customer_name") or "").strip() or None,
        conversation_id=ctx.conversation_id,
        originating_message_id=ctx.originating_message_id,
        originating_comment_id=ctx.originating_comment_id,
        title=str(raw.get("title") or "").strip() or None,
        collected_fields=raw.get("collected_fields") if isinstance(raw.get("collected_fields"), dict) else None,
        requested_items=raw.get("requested_items"),
        requested_branch=str(raw.get("requested_branch") or "").strip() or None,
        preferred_date=str(raw.get("preferred_date") or "").strip() or None,
        preferred_time=str(raw.get("preferred_time") or "").strip() or None,
        fulfillment_preference=str(raw.get("fulfillment_preference") or "").strip() or None,
        customer_notes=str(raw.get("customer_notes") or "").strip() or None,
        configuration_version=cfg_version or published,
    )

    try:
        created = CustomerRequestsService(session).create_from_ai(tenant_id=ctx.tenant_id, body=body)
    except CustomerRequestsError as exc:
        return {"ok": False, "error": exc.code, "message": exc.message}

    out: dict[str, Any] = {
        "ok": True,
        "request_id": created.get("request_id"),
        "request_number": created.get("request_number"),
        "status": created.get("status"),
        "request_type": created.get("request_type"),
        "configuration_version": created.get("configuration_version"),
    }
    if request_type == "APPOINTMENT":
        out["pending_confirmation"] = True
        out["customer_message_hint"] = appointment_pending_confirmation_message(ctx.response_language)
        out["hint_for_model"] = (
            "Appointment is a preference only until the owner confirms. "
            "Tell the customer it is pending confirmation; do not say it is booked/confirmed."
        )
    return out
