"""Token and Page validation helpers for Facebook Login for Business."""

from __future__ import annotations

from typing import Any, Literal

from services.meta_facebook_scope_policy import facebook_page_granular_targets_are_allowlisted
from services.meta_oauth_graph_http import MetaOAuthError

MetaOAuthFlowMode = Literal["facebook", "instagram", "unified"]
_REQUIRED_PAGE_TASKS = frozenset({"MESSAGING", "MODERATE"})


def _normalized_page_tasks(raw_tasks: object) -> set[str]:
    """Normalize classic and New Pages Experience task names."""

    tasks = {str(task).strip().upper() for task in raw_tasks} if isinstance(raw_tasks, list) else set()
    if "PROFILE_PLUS_MESSAGING" in tasks:
        tasks.add("MESSAGING")
    if "PROFILE_PLUS_MODERATE" in tasks:
        tasks.add("MODERATE")
    return tasks


def _scope_tuple(debug_data: dict[str, Any]) -> tuple[str, ...]:
    scopes = debug_data.get("scopes")
    if not isinstance(scopes, list):
        return ()
    return tuple(sorted({str(scope) for scope in scopes if str(scope).strip()}))


def _granular_targets_are_allowlisted(
    debug_data: dict[str, Any],
    *,
    page_id: str,
    instagram_id: str,
) -> bool:
    """Backward-compatible OAuth wrapper around the shared Page grant policy."""

    del instagram_id
    return facebook_page_granular_targets_are_allowlisted(debug_data, page_id=page_id)


def _eligible_pages(pages: list[dict[str, Any]], *, flow_mode: MetaOAuthFlowMode) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page in pages:
        page_id = str(page.get("id") or "").strip()
        page_token = str(page.get("access_token") or "").strip()
        instagram = page.get("instagram_business_account")
        if not page_id or not page_token:
            continue
        tasks = _normalized_page_tasks(page.get("tasks"))
        missing_tasks = sorted(_REQUIRED_PAGE_TASKS - tasks)
        if missing_tasks:
            raise MetaOAuthError(f"Authorized Facebook Page is missing required tasks ({','.join(missing_tasks)})")
        if flow_mode == "instagram" and not isinstance(instagram, dict):
            continue
        candidates.append(page)
    if not candidates:
        raise MetaOAuthError("No eligible Facebook Page was authorized in Meta Business Login")
    return candidates
