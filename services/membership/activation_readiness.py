"""Read-only activation gate. Never flips Brain or billing flags."""

from __future__ import annotations

from typing import Any

from services.membership.message_catalog import AI_SETUP_DAILY_EDIT_DEFAULT, UNCONFIGURED_FREE_FIELDS
from services.membership.message_flags import activation_flags_report
from services.membership.pg_store import store_backend


EXPECTED_ALEMBIC_HEAD = "20260910_req_web_chat"
LIVE_VERIFICATION_BLOCKERS = (
    "eval_suite_below_800",
    "live_channel_proof_missing",
    "live_voyage_pgvector_unverified",
)


def _alembic_head() -> dict[str, Any]:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config("alembic.ini"))
        heads = list(script.get_heads())
        return {
            "heads": heads,
            "expected": EXPECTED_ALEMBIC_HEAD,
            "ok": heads == [EXPECTED_ALEMBIC_HEAD],
        }
    except Exception as exc:
        return {"heads": [], "expected": EXPECTED_ALEMBIC_HEAD, "ok": False, "error": type(exc).__name__}


def _brain_imports() -> dict[str, bool]:
    names = {
        "runtime": "services.customer_ai.runtime",
        "billing": "services.customer_ai.billing",
        "history": "services.customer_ai.history",
        "planner": "services.customer_ai.planner.heuristic",
        "comments": "services.customer_ai.comments.pipeline",
        "pending_settlement": "services.membership.pending_settlement",
        "cost_dashboard": "services.membership.cost_dashboard",
        "outbox": "services.customer_ai.outbox",
        "outbox_pg": "services.customer_ai.outbox_pg",
        "conversation_store_pg": "services.customer_ai.conversation_store_pg",
        "leftover_reserve": "services.customer_ai.leftover_reserve",
        "credit_reservation_index": "services.membership.credit_reservation_index",
        "credit_reservation_index_pg": "services.membership.credit_reservation_index_pg",
        "credit_reservation_scan": "services.membership.credit_reservation_scan",
        "catalog_admin_pg": "services.membership.catalog_admin_pg",
        "daily_edits": "services.membership.daily_edits",
        "processing_budgets_pg": "services.membership.processing_budgets_pg",
        "followup_billing": "services.smart_followup.billing_ids",
        "web_followup": "services.web_chat.followup_delivery",
        "web_fence": "services.web_chat.operation_fence",
        "evals": "services.customer_ai.evals.runner",
        "turn_pipeline": "services.customer_ai.turn_pipeline",
        "pending_actions": "services.customer_ai.actions.pending",
        "followup_revalidate": "services.customer_ai.followup.revalidate",
        "lab": "modules.customer_ai_lab_api",
        "omni_hold": "services.omnichannel.message_hold",
        "social_turn_outcome": "services.social_turn_outcome",
        "social_customer_name": "services.social_customer_name",
        "hold_policy": "services.membership.hold_policy",
        "durable_tables": "services.membership.durable_tables",
    }
    out: dict[str, bool] = {}
    for key, module in names.items():
        try:
            __import__(module)
            out[key] = True
        except Exception:
            out[key] = False
    return out


def _offer_blockers() -> list[str]:
    """Report missing live-message offer gates. Never invent prices or flip sale_ready."""
    from services.membership.catalog_admin import current_catalog, payment_readiness

    catalog = current_catalog()
    pay = payment_readiness()
    out: list[str] = []
    if not catalog.get("published"):
        out.append("message_catalog_unpublished")
    if not catalog.get("checkout_ready"):
        out.append("message_checkout_not_ready")
    packs = catalog.get("topup_packs") or []
    if not any(bool(pack.get("sale_ready")) and pack.get("price_usd") not in (None, "") for pack in packs):
        out.append("message_topup_not_sale_ready")
    if not pay.get("cutover"):
        out.append("message_billing_cutover_off")
    stores = [(pay.get(name) or {}) for name in ("apple", "google", "stripe")]
    if not any(bool(item.get("sale_ready")) for item in stores):
        out.append("live_message_skus_not_sale_ready")
    return out


def activation_readiness() -> dict[str, Any]:
    flags = activation_flags_report()
    from services.customer_ai.outbox import outbox_counts
    from services.membership.conversion_dry_run import dry_run_credit_inventory
    from services.membership.credit_reservation_index import open_counts as leftover_credit_counts
    from services.membership.pending_settlement import pending_counts

    conversion = dry_run_credit_inventory()
    imports = _brain_imports()
    alembic = _alembic_head()
    store = store_backend()
    pending = pending_counts()
    leftover = leftover_credit_counts()
    from services.membership.durable_tables import durable_table_report

    durable = durable_table_report()
    blockers = list(UNCONFIGURED_FREE_FIELDS)
    if flags.get("enabled"):
        blockers.append("activation_flag_already_on")
    if store != "postgres":
        blockers.append("message_store_not_postgres")
    if not alembic.get("ok"):
        blockers.append("alembic_head")
    if not all(imports.values()):
        blockers.append("brain_import")
    if conversion.get("assumed_rate") is not None:
        blockers.append("invented_conversion_rate")
    if conversion.get("blocked"):
        reason = str(conversion.get("reason") or "conversion_dry_run_blocked")
        if reason not in blockers:
            blockers.append(reason)
    for item in _offer_blockers():
        if item not in blockers:
            blockers.append(item)
    for item in LIVE_VERIFICATION_BLOCKERS:
        if item not in blockers:
            blockers.append(item)
    if int(pending.get("unresolved") or 0) > 0:
        blockers.append("unresolved_pending_settlements")
    if int(leftover.get("stale") or 0) > 0:
        blockers.append("stale_leftover_credit_holds")
    if not durable.get("ready"):
        blockers.append("durable_tables_incomplete")
    from services.membership.catalog_admin import current_catalog, payment_readiness

    catalog = current_catalog()
    ready = False
    testing_ready = all(imports.values())
    testing_blockers: list[str] = []
    if not testing_ready:
        testing_blockers.append("brain_import")
    return {
        "ready_to_enable": ready,
        "testing_ready": testing_ready,
        "testing_blockers": testing_blockers,
        "enabled_now": flags.get("enabled") or [],
        "flags": flags,
        "store": store,
        "alembic": alembic,
        "catalog": {
            "published": bool(catalog.get("published")),
            "checkout_ready": bool(catalog.get("checkout_ready")),
            "publication_status": catalog.get("publication_status"),
        },
        "payment_readiness": payment_readiness(),
        "catalog_unconfigured": list(UNCONFIGURED_FREE_FIELDS),
        "conversion": {
            "blocked": bool(conversion.get("blocked")),
            "reason": conversion.get("reason"),
            "assumed_rate": conversion.get("assumed_rate"),
        },
        "daily_edit_default": AI_SETUP_DAILY_EDIT_DEFAULT,
        "pending_settlements": pending,
        "leftover_credit_holds": leftover,
        "outbox": outbox_counts(),
        "durable_tables": durable,
        "imports": imports,
        "lab_isolated": True,
        "verification": {
            "eval_suite_target": 800,
            "eval_suite_complete": False,
            "live_channel_proof": False,
            "live_voyage_pgvector": False,
        },
        "blockers": blockers,
        "note": (
            "testing_ready means Brain/admin code paths import and are ready for staging lab tests "
            "with LINAS_CUSTOMER_AI_LAB (Owner Lab page) on a non-customer tenant. "
            "ready_to_enable stays false until commercial/live verification blockers clear. "
            "This report never enables message billing."
        ),
    }
