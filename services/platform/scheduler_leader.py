"""One scheduler leader. Postgres uses an advisory lock; tests can use the leader table."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

_LOCK_KEY = 2026100902


def try_acquire_leader(engine: Engine, *, name: str, owner: str) -> bool:
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            locked = conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_KEY}).scalar()
            return bool(locked)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO scheduler_leader (name, owner) VALUES (:name, :owner)"),
                {"name": name, "owner": owner},
            )
    except IntegrityError:
        return False
    return True


def release_leader(engine: Engine, *, name: str, owner: str) -> None:
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
        return
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM scheduler_leader WHERE name = :name AND owner = :owner"),
            {"name": name, "owner": owner},
        )
