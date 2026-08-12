"""Thin shim: re-export Meta webhook field contracts from archive.

Kept under scripts/ so GHA, ops scripts, and tests can keep importing
`scripts.meta_webhook_contract` after the implementation was archived.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ARCHIVE = Path(__file__).resolve().parents[1] / "archive" / "scripts" / "meta_webhook_contract.py"
_MODULE_NAME = "_archived_meta_webhook_contract"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _ARCHIVE)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load archived meta_webhook_contract from {_ARCHIVE}")
_mod = importlib.util.module_from_spec(_spec)
# dataclasses require the module to be present in sys.modules during exec.
sys.modules[_MODULE_NAME] = _mod
_spec.loader.exec_module(_mod)

# Re-export public contract API used by scripts and tests.
ALLOWED_PAGE_SUBSCRIPTION_FIELDS = _mod.ALLOWED_PAGE_SUBSCRIPTION_FIELDS
APP_INSTAGRAM_WEBHOOK_FIELDS = _mod.APP_INSTAGRAM_WEBHOOK_FIELDS
APP_PAGE_WEBHOOK_FIELDS = _mod.APP_PAGE_WEBHOOK_FIELDS
COMMENT_FEATURE_SCOPES = _mod.COMMENT_FEATURE_SCOPES
DM_WEBHOOK_FIELDS = _mod.DM_WEBHOOK_FIELDS
FACEBOOK_COMMENT_SCOPES = _mod.FACEBOOK_COMMENT_SCOPES
FieldSetCheck = _mod.FieldSetCheck
INSTAGRAM_COMMENT_SCOPES = _mod.INSTAGRAM_COMMENT_SCOPES
PAGE_SUBSCRIPTION_COMMENT_DELIVERY = _mod.PAGE_SUBSCRIPTION_COMMENT_DELIVERY
PAGE_SUBSCRIPTION_DM_ONLY = _mod.PAGE_SUBSCRIPTION_DM_ONLY
PUBLISH_FEATURE_SCOPES = _mod.PUBLISH_FEATURE_SCOPES
assert_page_subscription_baseline = _mod.assert_page_subscription_baseline
assert_page_subscription_configuration = _mod.assert_page_subscription_configuration
check_exact_fields = _mod.check_exact_fields
evaluate_feature_readiness = _mod.evaluate_feature_readiness
extract_page_subscribed_app_id = _mod.extract_page_subscribed_app_id
extract_page_subscribed_fields = _mod.extract_page_subscribed_fields
merge_subscription_fields = _mod.merge_subscription_fields
page_subscribed_app_count = _mod.page_subscribed_app_count
parse_bool_env = _mod.parse_bool_env
plan_page_subscription_reconcile = _mod.plan_page_subscription_reconcile
subscription_field_names = _mod.subscription_field_names
validate_page_subscription_baseline = _mod.validate_page_subscription_baseline
validate_page_subscription_configuration = _mod.validate_page_subscription_configuration

__all__ = [
    "ALLOWED_PAGE_SUBSCRIPTION_FIELDS",
    "APP_INSTAGRAM_WEBHOOK_FIELDS",
    "APP_PAGE_WEBHOOK_FIELDS",
    "COMMENT_FEATURE_SCOPES",
    "DM_WEBHOOK_FIELDS",
    "FACEBOOK_COMMENT_SCOPES",
    "FieldSetCheck",
    "INSTAGRAM_COMMENT_SCOPES",
    "PAGE_SUBSCRIPTION_COMMENT_DELIVERY",
    "PAGE_SUBSCRIPTION_DM_ONLY",
    "PUBLISH_FEATURE_SCOPES",
    "assert_page_subscription_baseline",
    "assert_page_subscription_configuration",
    "check_exact_fields",
    "evaluate_feature_readiness",
    "extract_page_subscribed_app_id",
    "extract_page_subscribed_fields",
    "merge_subscription_fields",
    "page_subscribed_app_count",
    "parse_bool_env",
    "plan_page_subscription_reconcile",
    "subscription_field_names",
    "validate_page_subscription_baseline",
    "validate_page_subscription_configuration",
]
