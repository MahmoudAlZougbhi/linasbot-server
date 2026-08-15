"""Monotonic SFU job claim fencing (claimed_by + attempt_count generation)."""

from __future__ import annotations

from typing import Any


class JobClaimFenceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def claim_generation_of(job: Any) -> int:
    return int(getattr(job, "attempt_count", 0) or 0)


def assert_job_claim_fence(job: Any, *, worker_id: str, claim_generation: int) -> None:
    if str(getattr(job, "claimed_by", None) or "") != str(worker_id):
        raise JobClaimFenceError("claim_stale", "Stale job claim owner.")
    if claim_generation_of(job) != int(claim_generation):
        raise JobClaimFenceError("claim_stale", "Stale job claim generation.")
