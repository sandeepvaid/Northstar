"""Request-scoped dependencies."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from ..db import get_connection


def get_db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
