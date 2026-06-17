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
