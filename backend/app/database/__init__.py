from contextlib import contextmanager
from typing import Iterator
from urllib.parse import unquote_plus

import pyodbc

from app.core.config import settings


def _odbc_string() -> str:
    url = settings.DATABASE_URL
    marker = "odbc_connect="
    idx = url.find(marker)
    if idx == -1:
        raise ValueError("DATABASE_URL does not contain an odbc_connect parameter")
    return unquote_plus(url[idx + len(marker):])


def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(_odbc_string())


@contextmanager
def db_cursor() -> Iterator[tuple[pyodbc.Connection, pyodbc.Cursor]]:
    """Replaces the `conn = get_connection(); try: ...; finally: conn.close()`
    boilerplate repeated across services. Deliberately does NOT commit or roll
    back on your behalf — callers keep calling conn.commit() exactly where
    they already do, at exactly the same points, so this is a pure boilerplate
    reduction with no change in commit/rollback semantics. Callers that need
    conn.commit() still call it explicitly on the yielded conn.
    """
    conn = get_connection()
    try:
        yield conn, conn.cursor()
    finally:
        conn.close()


def escape_like(value: str) -> str:
    """Escape MSSQL LIKE wildcards so free-text search treats them as literal characters."""
    return value.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
