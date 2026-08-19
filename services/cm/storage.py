"""Draft storage with optimistic concurrency and tenant publish locks."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

from services.cm.atomic_io import atomic_write_json, compute_checksum, read_json_object
from services.cm.constants import CM_SECTIONS, DEFAULT_TENANT_ID
from services.cm.paths import draft_dir, ensure_cm_dirs, tenant_cm_root
from services.cm.schemas import SectionDraftEnvelope, default_section_payload, utc_now


def _sanitize_section_payload(section: str, payload: dict[str, object]) -> dict[str, object]:
    """Apply section-specific product locks before draft write."""
    if section == "languages":
        from services.cm.language_policy import sanitize_languages_payload

        return sanitize_languages_payload(payload)  # type: ignore[arg-type]
    if section == "dynamic_messages":
        from services.cm.greeting_rules import sanitize_dynamic_messages_payload

        return sanitize_dynamic_messages_payload(payload)  # type: ignore[arg-type]
    if section == "requests_appointments":
        from services.cm.request_rules import sanitize_requests_appointments_payload

        return sanitize_requests_appointments_payload(payload)  # type: ignore[arg-type]
    return payload


_fcntl: ModuleType | None
try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - non-Unix
    _fcntl = None


class ConflictError(Exception):
    """Raised when If-Match / revision does not match the current draft."""

    code: str = "CONFLICT"

    def __init__(
        self,
        message: str,
        *,
        current: SectionDraftEnvelope | None = None,
        expected_etag: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.current = current
        self.expected_etag = expected_etag


class UnknownSectionError(ValueError):
    code: str = "UNKNOWN_SECTION"


_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()
_HELD_TENANTS = threading.local()


def _process_lock(tenant_id: str) -> threading.RLock:
    key = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[key] = lock
        return lock


def _normalize_tenant(tenant_id: str | None) -> str:
    return (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID


def _validate_section(section: str) -> str:
    name = (section or "").strip()
    if name not in CM_SECTIONS:
        raise UnknownSectionError(f"Unknown CM section: {section!r}")
    return name


def draft_section_path(tenant_id: str | None, section: str) -> Path:
    tid = _normalize_tenant(tenant_id)
    name = _validate_section(section)
    return draft_dir(tid) / f"{name}.json"


def make_etag(revision: int, payload: dict[str, object]) -> str:
    digest = compute_checksum({"revision": revision, "payload": payload})
    return f'"{revision}-{digest[:16]}"'


def _envelope_from_dict(data: dict[str, object]) -> SectionDraftEnvelope:
    envelope = SectionDraftEnvelope.model_validate(data)
    sanitized = _sanitize_section_payload(envelope.section, envelope.payload)
    if sanitized is not envelope.payload and sanitized != envelope.payload:
        envelope = envelope.model_copy(update={"payload": sanitized})
    return envelope


def build_default_envelope(
    tenant_id: str,
    section: str,
    *,
    updated_by: str = "system",
) -> SectionDraftEnvelope:
    payload = default_section_payload(section)
    revision = 0
    return SectionDraftEnvelope(
        tenant_id=tenant_id,
        section=section,
        revision=revision,
        etag=make_etag(revision, payload),
        updated_at=utc_now(),
        updated_by=updated_by,
        payload=payload,
    )


def _write_envelope(path: Path, envelope: SectionDraftEnvelope) -> None:
    atomic_write_json(path, envelope.model_dump(mode="json"))


def get_draft(
    section: str,
    *,
    tenant_id: str | None = None,
    create_default: bool = True,
) -> SectionDraftEnvelope:
    """Load a draft section envelope. Optionally materialize defaults."""
    tid = _normalize_tenant(tenant_id)
    name = _validate_section(section)
    ensure_cm_dirs(tid)
    path = draft_section_path(tid, name)

    with tenant_server_lock(tid):
        if path.exists():
            return _envelope_from_dict(read_json_object(path))
        envelope = build_default_envelope(tid, name)
        if create_default:
            _write_envelope(path, envelope)
        return envelope


def put_draft(
    section: str,
    *,
    payload: dict[str, object],
    if_match: str | None,
    tenant_id: str | None = None,
    updated_by: str = "unknown",
    allow_create: bool = False,
) -> SectionDraftEnvelope:
    """Write a draft section with If-Match / revision optimistic concurrency."""
    tid = _normalize_tenant(tenant_id)
    name = _validate_section(section)
    ensure_cm_dirs(tid)
    path = draft_section_path(tid, name)
    expected = (if_match or "").strip()

    with tenant_server_lock(tid):
        if path.exists():
            current = _envelope_from_dict(read_json_object(path))
            if not expected or expected != current.etag:
                raise ConflictError(
                    "Draft section has changed; reload and retry.",
                    current=current,
                    expected_etag=expected or None,
                )
            revision = current.revision + 1
        else:
            # Create only with explicit allow_create or If-Match: *
            if not (allow_create or expected in {"", "*"}):
                raise ConflictError(
                    "Draft section does not exist for If-Match precondition.",
                    expected_etag=expected or None,
                )
            revision = 0

        previous_payload = dict(current.payload) if path.exists() else {}
        safe_payload = _sanitize_section_payload(name, payload)
        from services.search_metadata.cm_apply import enrich_section_payload

        safe_payload = enrich_section_payload(name, safe_payload, previous_payload)
        envelope = SectionDraftEnvelope(
            tenant_id=tid,
            section=name,
            revision=revision,
            etag=make_etag(revision, safe_payload),
            updated_at=utc_now(),
            updated_by=updated_by,
            payload=safe_payload,
        )
        _write_envelope(path, envelope)
        return envelope


def list_sections(*, tenant_id: str | None = None) -> list[dict[str, object]]:
    """List CM sections with draft presence / revision / etag metadata."""
    tid = _normalize_tenant(tenant_id)
    ensure_cm_dirs(tid)
    rows: list[dict[str, object]] = []
    for section in CM_SECTIONS:
        path = draft_section_path(tid, section)
        if path.exists():
            env = _envelope_from_dict(read_json_object(path))
            rows.append(
                {
                    "section": section,
                    "exists": True,
                    "revision": env.revision,
                    "etag": env.etag,
                    "updated_at": env.updated_at.isoformat(),
                    "updated_by": env.updated_by,
                }
            )
        else:
            rows.append(
                {
                    "section": section,
                    "exists": False,
                    "revision": 0,
                    "etag": None,
                    "updated_at": None,
                    "updated_by": None,
                }
            )
    return rows


def ensure_defaults(
    *,
    tenant_id: str | None = None,
    updated_by: str = "system",
) -> list[SectionDraftEnvelope]:
    """Ensure every CM section has a draft file (Restricted gets D8 defaults)."""
    tid = _normalize_tenant(tenant_id)
    ensure_cm_dirs(tid)
    created: list[SectionDraftEnvelope] = []
    with tenant_server_lock(tid):
        for section in CM_SECTIONS:
            path = draft_section_path(tid, section)
            if path.exists():
                continue
            envelope = build_default_envelope(tid, section, updated_by=updated_by)
            _write_envelope(path, envelope)
            created.append(envelope)
    return created


@contextmanager
def tenant_server_lock(tenant_id: str | None = None) -> Iterator[None]:
    """Exclusive lock for publish/reindex/rollback and draft critical sections.

    Reentrant within the same thread: a multi-step caller (e.g. ``publish_draft``) can hold
    the lock while calling helpers (``get_draft``/``put_draft``) that also acquire it, without
    self-deadlocking on the underlying OS ``flock`` (which is per-open-file-description, not
    reentrant across a fresh ``open()`` call even in the same process/thread).
    """
    tid = _normalize_tenant(tenant_id)
    held_obj = getattr(_HELD_TENANTS, "keys", None)
    held: set[str]
    if isinstance(held_obj, set):
        held = held_obj
    else:
        held = set()
        _HELD_TENANTS.keys = held

    if tid in held:
        # Already held by this thread (outer call) — just re-enter, no new flock.
        yield
        return

    ensure_cm_dirs(tid)
    lock_path = tenant_cm_root(tid) / ".cm.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    process_lock = _process_lock(tid)
    with process_lock:
        with open(lock_path, "a+", encoding="utf-8") as handle:
            if _fcntl is not None:
                _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
            held.add(tid)
            try:
                yield
            finally:
                held.discard(tid)
                if _fcntl is not None:
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
