"""Postgres document store. Replaces the Firestore client for remaining collections."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from db.session import database_url, whatsapp_session
from services.persistence.query_api import SERVER_TIMESTAMP, AlreadyExists, FieldFilter, Increment
from services.persistence.schema import ensure_schema

_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS linas_documents (
    path TEXT PRIMARY KEY,
    parent TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_INDEX = "CREATE INDEX IF NOT EXISTS linas_documents_parent ON linas_documents (parent)"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _encode(value: Any) -> Any:
    if value is SERVER_TIMESTAMP:
        return _now()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    return value


def _field(data: dict[str, Any], name: str) -> Any:
    current: Any = data
    for part in str(name).split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _apply(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, value in updates.items():
        if isinstance(value, Increment):
            merged[key] = int(merged.get(key) or 0) + int(value.value)
        else:
            merged[key] = _encode(value)
    return merged


def _matches(data: dict[str, Any], field: str, op: str, expected: Any) -> bool:
    actual = _field(data, field)
    expected = _encode(expected)
    if isinstance(actual, datetime):
        actual = actual.isoformat()
    if op == "==":
        return actual == expected
    if op == "<":
        return actual is not None and actual < expected
    if op == "<=":
        return actual is not None and actual <= expected
    if op == ">":
        return actual is not None and actual > expected
    if op == ">=":
        return actual is not None and actual >= expected
    if op == "in":
        return actual in set(expected or [])
    return False


class Snapshot:
    def __init__(self, ref: Document, data: dict[str, Any] | None) -> None:
        self.reference = ref
        self.id = ref.doc_id
        self.path = ref.path
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class Document:
    def __init__(self, client: DocumentClient, path: str) -> None:
        self._client = client
        self.path = path
        parent, _, doc_id = path.rpartition("/")
        self.parent = parent
        self.doc_id = doc_id or path

    def collection(self, name: str) -> Collection:
        return Collection(self._client, f"{self.path}/{name}")

    def get(self, transaction: Any = None, timeout: float | None = None, retry: Any = None) -> Snapshot:
        del transaction, timeout, retry
        return self._client.read(self)

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        self._client.write(self, data, merge=merge)

    def update(self, data: dict[str, Any]) -> None:
        self._client.write(self, data, merge=True, require_existing=True)

    def delete(self) -> None:
        self._client.remove(self)

    def create(self, data: dict[str, Any]) -> None:
        if self.get().exists:
            raise AlreadyExists(self.path)
        self.set(data, merge=False)


class Collection:
    def __init__(self, client: DocumentClient, path: str) -> None:
        self._client = client
        self.path = path

    def document(self, doc_id: str) -> Document:
        return Document(self._client, f"{self.path}/{doc_id}")

    def where(
        self, field: str | None = None, op: str | None = None, value: Any = None, *, filter: Any = None
    ) -> QuerySet:
        query = QuerySet(self._client, self.path)
        return query.where(field, op, value, filter=filter)

    def order_by(self, field: str, direction: str | None = None) -> QuerySet:
        return QuerySet(self._client, self.path).order_by(field, direction)

    def limit(self, count: int) -> QuerySet:
        return QuerySet(self._client, self.path).limit(count)

    def stream(self, timeout: float | None = None, retry: Any = None) -> list[Snapshot]:
        return QuerySet(self._client, self.path).stream(timeout=timeout, retry=retry)

    def get(self) -> list[Snapshot]:
        return self.stream()


class QuerySet:
    def __init__(self, client: DocumentClient, path: str) -> None:
        self._client = client
        self.path = path
        self._filters: list[tuple[str, str, Any]] = []
        self._order: list[tuple[str, str]] = []
        self._limit: int | None = None
        self._after: list[Any] | None = None

    def where(
        self, field: str | None = None, op: str | None = None, value: Any = None, *, filter: Any = None
    ) -> QuerySet:
        if isinstance(filter, FieldFilter):
            self._filters.append((str(filter.field_path), str(filter.op_string), filter.value))
        elif field is not None and op is not None:
            self._filters.append((field, op, value))
        return self

    def order_by(self, field: str, direction: str | None = None) -> QuerySet:
        self._order.append((field, direction or "ASCENDING"))
        return self

    def limit(self, count: int) -> QuerySet:
        self._limit = int(count)
        return self

    def start_after(self, *values: Any) -> QuerySet:
        if len(values) == 1 and isinstance(values[0], list):
            self._after = list(values[0])
        elif len(values) == 1 and isinstance(values[0], Snapshot):
            data = values[0].to_dict() or {}
            self._after = [_field(data, name) if name != "__name__" else values[0].id for name, _ in self._order]
        else:
            self._after = list(values)
        return self

    def stream(self, timeout: float | None = None, retry: Any = None) -> list[Snapshot]:
        del timeout, retry
        rows = []
        for snapshot in self._client.children(self.path):
            data = snapshot.to_dict() or {}
            if all(_matches(data, field, op, value) for field, op, value in self._filters):
                rows.append(snapshot)
        rows.sort(key=lambda snap: self._sort_key(snap))
        descending = bool(self._order) and self._order[0][1] == "DESCENDING"
        if descending:
            rows.reverse()
        if self._after:
            cursor = tuple(_encode(item) for item in self._after)
            rows = [
                snap
                for snap in rows
                if (self._sort_key(snap) < cursor if descending else self._sort_key(snap) > cursor)
            ]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def get(self) -> list[Snapshot]:
        return self.stream()

    def _sort_key(self, snap: Snapshot) -> tuple[Any, ...]:
        data = snap.to_dict() or {}
        if not self._order:
            return (snap.id,)
        values = []
        for name, _direction in self._order:
            values.append(snap.id if name == "__name__" else _field(data, name))
        return tuple(values)


class Transaction:
    def __init__(self, client: DocumentClient) -> None:
        self._client = client

    def get(self, ref: Document) -> Snapshot:
        return ref.get()

    def set(self, ref: Document, data: dict[str, Any], merge: bool = False) -> None:
        ref.set(data, merge=merge)

    def update(self, ref: Document, data: dict[str, Any]) -> None:
        ref.update(data)

    def delete(self, ref: Document) -> None:
        ref.delete()

    def commit(self) -> None:
        return None


class DocumentClient:
    def __init__(self) -> None:
        if not database_url():
            raise RuntimeError("document store requires DATABASE_URL")

    def collection(self, name: str) -> Collection:
        return Collection(self, name)

    def transaction(self) -> Transaction:
        return Transaction(self)

    def _session(self):
        return whatsapp_session(require=True)

    def _ensure(self, session: Any) -> None:
        ensure_schema(session)
        session.execute(text(_DOCUMENTS))
        session.execute(text(_INDEX))

    def read(self, ref: Document) -> Snapshot:
        with self._session() as session:
            self._ensure(session)
            row = session.execute(
                text("SELECT data_json FROM linas_documents WHERE path = :path"),
                {"path": ref.path},
            ).first()
        if row is None:
            return Snapshot(ref, None)
        return Snapshot(ref, json.loads(row[0]))

    def write(self, ref: Document, data: dict[str, Any], *, merge: bool, require_existing: bool = False) -> None:
        with self._session() as session:
            self._ensure(session)
            current_row = session.execute(
                text("SELECT data_json FROM linas_documents WHERE path = :path"),
                {"path": ref.path},
            ).first()
            if current_row is None and require_existing:
                raise KeyError(ref.path)
            current = json.loads(current_row[0]) if current_row and merge else {}
            stored = _apply(current, data)
            session.execute(
                text(
                    """
                    INSERT INTO linas_documents (path, parent, doc_id, data_json, updated_at)
                    VALUES (:path, :parent, :doc_id, :data_json, :updated_at)
                    ON CONFLICT (path) DO UPDATE SET
                        data_json = excluded.data_json,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "path": ref.path,
                    "parent": ref.parent,
                    "doc_id": ref.doc_id,
                    "data_json": json.dumps(stored, default=str),
                    "updated_at": _now(),
                },
            )

    def remove(self, ref: Document) -> None:
        with self._session() as session:
            self._ensure(session)
            session.execute(text("DELETE FROM linas_documents WHERE path = :path"), {"path": ref.path})

    def children(self, parent: str) -> list[Snapshot]:
        with self._session() as session:
            self._ensure(session)
            rows = session.execute(
                text("SELECT path, doc_id, data_json FROM linas_documents WHERE parent = :parent"),
                {"parent": parent},
            ).all()
        snapshots = []
        for path, doc_id, raw in rows:
            ref = Document(self, path)
            ref.doc_id = doc_id
            snapshots.append(Snapshot(ref, json.loads(raw)))
        return snapshots


def open_document_client() -> DocumentClient | None:
    if not database_url():
        return None
    return DocumentClient()
