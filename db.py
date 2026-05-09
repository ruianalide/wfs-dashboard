"""
db.py — Database abstraction layer.

Local (development):  uses SQLite via DB_PATH
Production (Supabase): uses PostgreSQL via DATABASE_URL environment variable

The dashboard and scrapers import `get_conn()` and `execute()` from here.
They never call sqlite3 or psycopg2 directly.

Usage:
    from db import get_conn, execute, read_sql

    # Read
    df = read_sql("SELECT * FROM players")

    # Write
    execute("INSERT INTO players (...) VALUES (%s, %s)", (val1, val2))
"""

import os
import sqlite3
import contextlib
import pandas as pd

# ── detect which backend to use ──────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")  # set on Streamlit Cloud via Secrets
_BACKEND = "postgres" if DATABASE_URL else "sqlite"

# SQLite path (only used locally)
_SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy\wfs_fantasy.db"
)

print(f"[db] Backend: {_BACKEND}")


# ── connection helpers ────────────────────────────────────────────────────────

@contextlib.contextmanager
def get_conn():
    """
    Context manager that yields an open DB connection.
    Commits on clean exit, rolls back on exception, always closes.

    Usage:
        with get_conn() as conn:
            conn.execute(...)
    """
    if _BACKEND == "postgres":
        import psycopg
        conn = psycopg.connect(DATABASE_URL)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def read_sql(query: str, params=None) -> pd.DataFrame:
    """
    Execute a SELECT and return a DataFrame.
    Handles the SQLite vs psycopg parameter style difference automatically.
    """
    if _BACKEND == "postgres":
        import psycopg
        query = query.replace("?", "%s")
        with psycopg.connect(DATABASE_URL) as conn:
            return pd.read_sql(query, conn, params=params)
    else:
        with get_conn() as conn:
            return pd.read_sql(query, conn, params=params)


def execute(query: str, params=None, many: bool = False):
    """
    Execute an INSERT / UPDATE / DELETE.

    Args:
        query:  SQL string. Use ? placeholders (auto-converted for postgres).
        params: tuple for single execute, list of tuples for executemany.
        many:   if True, uses executemany (params must be a list of tuples).
    """
    if _BACKEND == "postgres":
        query = query.replace("?", "%s")

    with get_conn() as conn:
        cursor = conn.cursor()
        if many:
            cursor.executemany(query, params or [])
        else:
            cursor.execute(query, params or ())
