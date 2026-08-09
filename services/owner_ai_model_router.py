"""Config-driven model routing for owner / CM / creative / customer paths + usage tracking."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from storage.persistent_storage import _DATA_ROOT

RouteKind = Literal[
    "owner_help",
    "owner_complex_cm",
    "creative",
    "customer_high_volume",
]


@dataclass(frozen=True)
class RouteDecision:
    kind: RouteKind
    model: str
    reason: str
    max_context_tokens: int


def _env_model(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip() or default


def router_config() -> dict[str, Any]:
    """Owner/CM/creative route models (OpenAI API ids).

    Content Manager / owner CM / creative → gpt-5.6-sol
    Customer high-volume → gpt-5.6-luna
    """
    return {
        "owner_help": {
            "model": _env_model("LINAS_OWNER_HELP_MODEL", "gpt-5.6-luna"),
            "max_context_tokens": int(os.getenv("LINAS_OWNER_HELP_MAX_CTX", "3500")),
        },
        "owner_complex_cm": {
            "model": _env_model("LINAS_OWNER_CM_MODEL", "gpt-5.6-sol"),
            "max_context_tokens": int(os.getenv("LINAS_OWNER_CM_MAX_CTX", "6000")),
        },
        "creative": {
            "model": _env_model("LINAS_CREATIVE_MODEL", "gpt-5.6-sol"),
            "max_context_tokens": int(os.getenv("LINAS_CREATIVE_MAX_CTX", "4000")),
        },
        "customer_high_volume": {
            "model": _env_model("LINAS_CUSTOMER_HV_MODEL", "gpt-5.6-luna"),
            "max_context_tokens": int(os.getenv("LINAS_CUSTOMER_HV_MAX_CTX", "2500")),
        },
    }


_CM_MARKERS = (
    "content management",
    " cm ",
    "draft",
    "publish",
    "validate",
    "section",
    "faq",
    "prices",
    "services",
    "handoff",
    "ai basics",
)
_CREATIVE_MARKERS = (
    "create post",
    "make a post",
    "caption",
    "creative",
    "image",
    "reel",
    "schedule post",
    "بوست",
    "منشور",
    "كابشن",
    "صورة",
    "فيديو",
    "compress",
    "اختصر",
)


def classify_owner_route(user_text: str, *, intent: str | None = None) -> RouteKind:
    if intent in {"propose_cm_patch", "publish_cm", "validate_cm", "read_cm", "approve_cm_patch"}:
        return "owner_complex_cm"
    if intent in {
        "read_scheduled_posts",
        "create_creative_draft",
        "schedule_creative_draft",
    } or any(m in f" {(user_text or '').lower()} " for m in _CREATIVE_MARKERS):
        return "creative"
    text = f" {(user_text or '').lower()} "
    if any(m in text for m in _CM_MARKERS):
        return "owner_complex_cm"
    return "owner_help"


def route_owner_turn(user_text: str, *, intent: str | None = None) -> RouteDecision:
    kind = classify_owner_route(user_text, intent=intent)
    cfg = router_config()[kind]
    return RouteDecision(
        kind=kind,
        model=str(cfg["model"]),
        reason=f"intent={intent or 'heuristic'}→{kind}",
        max_context_tokens=int(cfg["max_context_tokens"]),
    )


class OwnerChatUsageTracker:
    """Append-only token usage for owner-chat turns (local durable file)."""

    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "owner_ai_usage")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str) -> Path:
        return self._root / f"{tenant_id}.jsonl"

    def record(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        route: RouteDecision,
        prompt_tokens: int,
        completion_tokens: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "ts": time.time(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "kind": route.kind,
            "model": route.model,
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(prompt_tokens) + int(completion_tokens),
            "reason": route.reason,
            "meta": meta or {},
        }
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with self._lock:
            with self._path(tenant_id).open("a", encoding="utf-8") as fh:
                fh.write(line)
        return row

    def totals(self, tenant_id: str) -> dict[str, Any]:
        path = self._path(tenant_id)
        total = 0
        turns = 0
        by_kind: dict[str, int] = {}
        if not path.is_file():
            return {"turns": 0, "total_tokens": 0, "by_kind": {}}
        with self._lock:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                turns += 1
                tok = int(row.get("total_tokens") or 0)
                total += tok
                kind = str(row.get("kind") or "unknown")
                by_kind[kind] = by_kind.get(kind, 0) + tok
        return {"turns": turns, "total_tokens": total, "by_kind": by_kind}


owner_chat_usage_tracker = OwnerChatUsageTracker()


def decision_to_dict(decision: RouteDecision) -> dict[str, Any]:
    return asdict(decision)
