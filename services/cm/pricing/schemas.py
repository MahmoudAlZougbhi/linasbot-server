"""Business-agnostic CM pricing schemas (tenant-owned catalog + rules).

No body-part / Lina-specific types. Tenants configure catalog items of any type.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from services.cm.schemas import CmBaseModel, LocalizedLabels

CatalogItemType = Literal[
    "service",
    "product",
    "procedure",
    "body_area",
    "appointment_type",
    "membership",
    "class",
    "package",
    "add_on",
    "custom",
]

AudienceScope = Literal["men", "women", "general", "any"]
RoundingPolicy = Literal["none", "nearest_0_01", "nearest_1", "floor_0_01", "ceil_0_01"]
StackingPolicy = Literal["stack", "exclusive", "best_of"]
ConditionOp = Literal["and", "or"]
ConditionKind = Literal[
    "subtotal_at_least",
    "eligible_item_count_at_least",
    "eligible_quantity_at_least",
    "category_count_at_least",
    "includes_items",
    "excludes_items",
    "includes_categories",
    "excludes_categories",
    "branch_in",
    "audience_in",
    "effective_now",
]
ActionKind = Literal["percent_off", "fixed_amount_off", "fixed_final_total", "bundle_price"]


class EffectiveWindow(CmBaseModel):
    start: str | None = None  # ISO-8601 date or datetime; None = unbounded
    end: str | None = None


class CatalogCategory(CmBaseModel):
    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    parent_id: str | None = None
    active: bool = True
    notes: str | None = None


class ItemVariant(CmBaseModel):
    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    sku: str | None = None
    duration_minutes: int | None = None
    size: str | None = None
    unit: str | None = None
    active: bool = True
    notes: str | None = None


class CatalogItem(CmBaseModel):
    """Tenant-owned sellable/reference item. Types are tenant-defined via ``item_type``."""

    id: str
    item_type: CatalogItemType = "custom"
    category_ids: list[str] = Field(default_factory=list)
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    base_price: float | None = None
    currency: str = "USD"
    variants: list[ItemVariant] = Field(default_factory=list)
    branch_ids: list[str] = Field(default_factory=list)  # empty = all branches
    audience: AudienceScope = "any"
    unit: str | None = None
    discount_eligible: bool = True
    active: bool = True
    effective: EffectiveWindow = Field(default_factory=EffectiveWindow)
    provenance: str | None = None
    revision: int = 1
    notes: str | None = None

    @field_validator("base_price")
    @classmethod
    def _base_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("base_price must be >= 0")
        return value


class PriceEntry(CmBaseModel):
    """Structured price row keyed by catalog item/variant + optional dimensions."""

    id: str
    catalog_item_id: str
    variant_id: str | None = None
    amount: float
    currency: str = "USD"
    branch_id: str | None = None
    audience: AudienceScope = "any"
    unit: str | None = None
    min_quantity: float | None = None
    max_quantity: float | None = None
    duration_minutes: int | None = None
    size: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)  # validated tenant keys only
    active: bool = True
    effective: EffectiveWindow = Field(default_factory=EffectiveWindow)
    provenance: str | None = None
    revision: int = 1
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def _amount_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("amount must be >= 0")
        return value


class RuleCondition(CmBaseModel):
    kind: ConditionKind
    amount: float | None = None
    count: int | None = None
    item_ids: list[str] = Field(default_factory=list)
    category_ids: list[str] = Field(default_factory=list)
    branch_ids: list[str] = Field(default_factory=list)
    audiences: list[AudienceScope] = Field(default_factory=list)


class RuleConditionGroup(CmBaseModel):
    op: ConditionOp = "and"
    conditions: list[RuleCondition] = Field(default_factory=list)
    groups: list[RuleConditionGroup] = Field(default_factory=list)

    @model_validator(mode="after")
    def _bounded_nesting(self) -> RuleConditionGroup:
        def _depth(group: RuleConditionGroup, level: int) -> int:
            if level > 3:
                raise ValueError("condition group nesting exceeds max depth 3")
            return max([level, *(_depth(g, level + 1) for g in group.groups)], default=level)

        _depth(self, 1)
        return self


class RuleAction(CmBaseModel):
    kind: ActionKind
    percent: float | None = None
    amount: float | None = None
    currency: str | None = None

    @model_validator(mode="after")
    def _action_fields(self) -> RuleAction:
        if self.kind == "percent_off":
            if self.percent is None or self.percent < 0 or self.percent > 100:
                raise ValueError("percent_off requires percent in [0, 100]")
        elif self.kind in {"fixed_amount_off", "fixed_final_total", "bundle_price"}:
            if self.amount is None or self.amount < 0:
                raise ValueError(f"{self.kind} requires non-negative amount")
        return self


class DiscountRule(CmBaseModel):
    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    priority: int = 100  # lower runs first for exclusive; deterministic
    stacking: StackingPolicy = "exclusive"
    exclusive: bool = True
    when: RuleConditionGroup = Field(default_factory=RuleConditionGroup)
    then: RuleAction
    eligible_item_ids: list[str] = Field(default_factory=list)
    excluded_item_ids: list[str] = Field(default_factory=list)
    eligible_category_ids: list[str] = Field(default_factory=list)
    excluded_category_ids: list[str] = Field(default_factory=list)
    currency: str = "USD"
    rounding: RoundingPolicy = "nearest_0_01"
    min_discount: float | None = None
    max_discount: float | None = None
    active: bool = True
    effective: EffectiveWindow = Field(default_factory=EffectiveWindow)
    provenance: str | None = None
    revision: int = 1
    notes: str | None = None


class QuoteLine(CmBaseModel):
    catalog_item_id: str
    variant_id: str | None = None
    quantity: float = 1
    unit_amount: float
    line_subtotal: float
    currency: str
    price_entry_id: str | None = None
    label: str = ""


class AppliedRule(CmBaseModel):
    rule_id: str
    label: str = ""
    action_kind: ActionKind
    discount_amount: float


class PriceQuote(CmBaseModel):
    tenant_id: str
    currency: str
    lines: list[QuoteLine] = Field(default_factory=list)
    subtotal: float = 0
    matching_rule_ids: list[str] = Field(default_factory=list)
    applied_rules: list[AppliedRule] = Field(default_factory=list)
    discount_amount: float = 0
    final_total: float = 0
    content_version_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class PricingContext(CmBaseModel):
    tenant_id: str
    branch_id: str | None = None
    audience: AudienceScope = "any"
    now_iso: str | None = None
    content_version_id: str | None = None
    currency: str | None = None


class QuoteRequestLine(CmBaseModel):
    catalog_item_id: str
    variant_id: str | None = None
    quantity: float = 1

    @field_validator("quantity")
    @classmethod
    def _qty_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("quantity must be > 0")
        return value


# --- Superseding control-plane concepts (tenant-owned, business-agnostic) ---

DimensionValueType = Literal["string", "number", "enum", "boolean"]


class PricingDimensionDefinition(CmBaseModel):
    """Owner-declared typed dimension (validated; never free-form executable formulas)."""

    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    value_type: DimensionValueType = "string"
    allowed_values: list[str] = Field(default_factory=list)  # required when value_type=enum
    required: bool = False
    active: bool = True
    notes: str | None = None


class PricingDimensionValue(CmBaseModel):
    dimension_id: str
    value: str


class ResourceOrMethod(CmBaseModel):
    """Tenant resource/method (machines, rooms, practitioners, tools) — data, not code."""

    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    aliases: list[str] = Field(default_factory=list)
    resource_kind: str = "generic"  # tenant-defined: machine, room, staff, tool, …
    branch_ids: list[str] = Field(default_factory=list)
    active: bool = True
    provenance: str | None = None
    revision: int = 1
    notes: str | None = None


class PriceBook(CmBaseModel):
    """Named price book (e.g. standard, promo window) scoping a set of PriceEntry ids."""

    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    currency: str = "USD"
    entry_ids: list[str] = Field(default_factory=list)
    branch_ids: list[str] = Field(default_factory=list)
    audience: AudienceScope = "any"
    active: bool = True
    effective: EffectiveWindow = Field(default_factory=EffectiveWindow)
    provenance: str | None = None
    revision: int = 1
    notes: str | None = None


class DiscountRuleSet(CmBaseModel):
    """Named collection of discount/package rules with shared stacking defaults."""

    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    rule_ids: list[str] = Field(default_factory=list)
    default_stacking: StackingPolicy = "exclusive"
    active: bool = True
    notes: str | None = None


class PackageRule(CmBaseModel):
    """Package/bundle rule — declarative WHEN/THEN, same engine as DiscountRule."""

    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    priority: int = 100
    stacking: StackingPolicy = "exclusive"
    exclusive: bool = True
    when: RuleConditionGroup = Field(default_factory=RuleConditionGroup)
    then: RuleAction
    included_item_ids: list[str] = Field(default_factory=list)
    included_category_ids: list[str] = Field(default_factory=list)
    currency: str = "USD"
    rounding: RoundingPolicy = "nearest_0_01"
    active: bool = True
    effective: EffectiveWindow = Field(default_factory=EffectiveWindow)
    provenance: str | None = None
    revision: int = 1
    notes: str | None = None

    def as_discount_rule(self) -> DiscountRule:
        return DiscountRule(
            id=self.id,
            labels=self.labels,
            priority=self.priority,
            stacking=self.stacking,
            exclusive=self.exclusive,
            when=self.when,
            then=self.then,
            eligible_item_ids=list(self.included_item_ids),
            eligible_category_ids=list(self.included_category_ids),
            currency=self.currency,
            rounding=self.rounding,
            active=self.active,
            effective=self.effective,
            provenance=self.provenance,
            revision=self.revision,
            notes=self.notes,
        )


class PublishedPricingVersion(CmBaseModel):
    """Immutable pricing slice pointer published with content/index atomically."""

    tenant_id: str
    pricing_version_id: str
    content_version_id: str
    checksum: str
    created_at: str | None = None
    created_by: str | None = None
    schema_version: int = 1


# Stable aliases matching the owner vocabulary (same runtime objects).
ConditionGroup = RuleConditionGroup
PricingAction = RuleAction
QuoteLineItem = QuoteLine
