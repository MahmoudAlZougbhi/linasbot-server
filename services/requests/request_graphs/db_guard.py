"""Honest readiness checks for request-definition graph tables."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError, ProgrammingError

GRAPH_TABLE = "request_definition_graphs"


class RequestGraphsDbError(RuntimeError):
    """Raised when the customer DB cannot serve request graphs."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def graphs_tables_ready(session: Any) -> bool:
    bind = session.get_bind()
    if bind is None:
        return False
    return GRAPH_TABLE in inspect(bind).get_table_names()


@contextmanager
def request_graphs_session() -> Iterator[Any]:
    """Yield a WhatsApp DB session only when graph tables are migrated."""
    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

    try:
        with whatsapp_session(require=True) as db:
            if not graphs_tables_ready(db):
                raise RequestGraphsDbError(
                    "REQUEST_GRAPHS_UNMIGRATED",
                    "Request graph tables are not migrated on this database.",
                )
            yield db
    except WhatsAppDatabaseUnavailable as exc:
        raise RequestGraphsDbError(
            "REQUEST_GRAPHS_DB_UNAVAILABLE",
            str(exc) or "Customer database unavailable.",
        ) from exc
    except RequestGraphsDbError:
        raise
    except (OperationalError, ProgrammingError) as exc:
        text = str(exc).lower()
        if GRAPH_TABLE in text or "no such table" in text or "does not exist" in text:
            raise RequestGraphsDbError(
                "REQUEST_GRAPHS_UNMIGRATED",
                "Request graph tables are not migrated on this database.",
            ) from exc
        raise
