"""CM Requests & Appointments section schema (draft → publish).

Defaults keep the module inactive until the owner enables types and publishes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from services.cm.schemas_content import ArticleAttachment, CmBaseModel, LocalizedLabels

RequestTypeCode = Literal["ORDER", "APPOINTMENT", "OTHER"]
NotificationLanguage = Literal["auto", "ar", "en", "fr", "franco"]
FieldValidationKind = Literal[
    "",
    "nonempty",
    "phone",
    "email",
    "date",
    "time",
    "quantity",
    "address",
]


class RequestFieldDef(CmBaseModel):
    """One collectable question / field in the customer capture flow."""

    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    required: bool = False
    enabled: bool = True
    order: int = 0
    # Empty applies_to = all enabled request types.
    applies_to: list[RequestTypeCode] = Field(default_factory=list)
    validation: FieldValidationKind = ""
    notes: str | None = None


class RequestCatalogItem(CmBaseModel):
    """Selectable service, product, or branch offered for requests."""

    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    enabled: bool = True
    notes: str | None = None


class RequestMessages(CmBaseModel):
    acknowledgment: str = ""
    appointment_confirmed: str = ""
    order_ready: str = ""
    completed: str = ""
    cancelled: str = ""


class RequestAssignmentDefaults(CmBaseModel):
    default_assignee_user_id: str = ""
    auto_assign: bool = False


class RequestRule(CmBaseModel):
    """Owner-facing request rule — type, title, and custom note."""

    id: str
    type: RequestTypeCode = "APPOINTMENT"
    name: str = ""
    notes: str | None = None
    enabled: bool = True
    attachments: list[ArticleAttachment] = Field(default_factory=list)
    ai_search_title: str = ""
    ai_search_description: str = ""


class RequestsAppointmentsSection(CmBaseModel):
    """Publishable Requests & Appointments configuration.

    Capture stays inactive when ``module_enabled`` is false or ``enabled_types`` is empty
    (see ``services.requests.config_loader.requests_capture_active``).
    """

    module_enabled: bool = False
    rules: list[RequestRule] = Field(default_factory=list)
    enabled_types: list[RequestTypeCode] = Field(default_factory=list)
    type_labels: dict[str, LocalizedLabels] = Field(default_factory=dict)
    fields: list[RequestFieldDef] = Field(default_factory=list)
    services: list[RequestCatalogItem] = Field(default_factory=list)
    products: list[RequestCatalogItem] = Field(default_factory=list)
    branches: list[RequestCatalogItem] = Field(default_factory=list)
    messages: RequestMessages = Field(default_factory=RequestMessages)
    notification_language: NotificationLanguage = "auto"
    assignment_defaults: RequestAssignmentDefaults = Field(default_factory=RequestAssignmentDefaults)
    push_enabled: bool = True
    # Free-text prohibited / restricted request topics (owner-authored).
    prohibited: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("enabled_types")
    @classmethod
    def _unique_enabled_types(cls, value: list[RequestTypeCode]) -> list[RequestTypeCode]:
        seen: set[str] = set()
        out: list[RequestTypeCode] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    @field_validator("type_labels")
    @classmethod
    def _type_label_keys(cls, value: dict[str, LocalizedLabels]) -> dict[str, LocalizedLabels]:
        allowed = {"ORDER", "APPOINTMENT", "OTHER"}
        bad = sorted(k for k in value if k not in allowed)
        if bad:
            raise ValueError(f"type_labels keys must be ORDER|APPOINTMENT|OTHER; got {bad}")
        return value
