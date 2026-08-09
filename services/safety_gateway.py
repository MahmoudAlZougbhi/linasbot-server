"""Safety gateway for inbound/outbound AI and creative flows."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from storage.persistent_storage import _DATA_ROOT

Decision = Literal["allow", "block", "review"]


@dataclass
class SafetyDecision:
    decision: Decision
    reasons: list[str]
    provider: str | None
    incident_id: str | None = None


@dataclass
class ModerationIncident:
    id: str
    tenant_id: str
    user_id: str | None
    channel: str
    decision: Decision
    reasons: list[str]
    created_at: float


class SafetyGateway:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "safety")
        self._root.mkdir(parents=True, exist_ok=True)
        self._strikes: dict[str, int] = {}

    def _incident_path(self, incident_id: str) -> Path:
        return self._root / "incidents" / f"{incident_id}.json"

    def record_incident(self, incident: ModerationIncident) -> None:
        path = self._incident_path(incident.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            path.write_text(json.dumps(asdict(incident)), encoding="utf-8")

    async def check_text(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        text: str,
        channel: str,
    ) -> SafetyDecision:
        # Application rules first (explicit; not keyword-only end state — provider moderation next).
        lowered = (text or "").lower()
        hard_block_markers = (
            "how to make a bomb",
            "child sexual",
            "csam",
        )
        reasons: list[str] = []
        for marker in hard_block_markers:
            if marker in lowered:
                reasons.append(f"policy:{marker}")
        provider_name: str | None = None
        try:
            from services.providers.base import provider_config

            provider_name = str(provider_config()["moderation"]["provider"])
            if provider_name == "openai":
                from services import llm_core_service

                client = getattr(llm_core_service, "client", None)
                if client is not None and hasattr(client, "moderations"):
                    resp = await client.moderations.create(input=text)
                    result = resp.results[0]
                    if getattr(result, "flagged", False):
                        reasons.append("provider_moderation_flagged")
        except Exception:
            # Fail closed only for hard markers; otherwise continue with app rules.
            pass

        if reasons:
            incident_id = uuid.uuid4().hex
            self.record_incident(
                ModerationIncident(
                    id=incident_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    channel=channel,
                    decision="block",
                    reasons=reasons,
                    created_at=time.time(),
                )
            )
            key = f"{tenant_id}:{user_id or 'anon'}"
            self._strikes[key] = self._strikes.get(key, 0) + 1
            return SafetyDecision(decision="block", reasons=reasons, provider=provider_name, incident_id=incident_id)
        return SafetyDecision(decision="allow", reasons=[], provider=provider_name)

    def strike_count(self, tenant_id: str, user_id: str | None) -> int:
        return self._strikes.get(f"{tenant_id}:{user_id or 'anon'}", 0)


safety_gateway = SafetyGateway()
