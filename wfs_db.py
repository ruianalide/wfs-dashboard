"""
wfs_db.py — Database abstraction layer.

Local (development):  SQLite
Production (Supabase): 
  - Simple full-table SELECTs → Supabase REST client (no libpq needed)
  - Parameterised queries (WHERE, INSERT, UPDATE, DELETE) → psycopg via DATABASE_URL

Environment variables:
    DATABASE_URL  — PostgreSQL connection string
    SUPABASE_URL  — Supabase project URL
    SUPABASE_KEY  — Supabase anon/publishable key
"""

import os
import re
import sqlite3
import contextlib
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if SUPABASE_URL and SUPABASE_KEY:
    _BACKEND = "supabase"
elif DATABASE_URL:
    _BACKEND = "postgres"
else:
    _BACKEND = "sqlite"

_SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy\wfs_fantasy.db"
)

print(f"[wfs_db] Backend: {_BACKEND}")

# ── Supabase client (lazy) ────────────────────────────────────────────────────
_supabase_client = None

def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# ── psycopg helper (for parameterised queries in production) ──────────────────
@contextlib.contextmanager
def _pg_conn():
    """Open a psycopg connection to Supabase PostgreSQL."""
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


# ── SQLite helper (local) ─────────────────────────────────────────────────────
@contextlib.contextmanager
def get_conn():
    """SQLite connection context manager (local only)."""
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_table(query: str) -> str:
    m = re.search(r'\bFROM\s+(["\w]+)', query, re.IGNORECASE)
    if m:
        return m.group(1).strip('"')
    raise ValueError(f"Cannot extract table name from: {query}")


def _is_simple_select(query: str, params) -> bool:
    """True if query is a plain SELECT * FROM table with no WHERE/params."""
    q = query.strip().upper()
    return (
        q.startswith("SELECT") and
        "WHERE" not in q and
        not params
    )


def _apply_order(df: pd.DataFrame, query: str) -> pd.DataFrame:
    order_match = re.search(r'ORDER BY\s+(.+?)(?:LIMIT|$)', query, re.IGNORECASE)
    if not order_match:
        return df
    order_str = order_match.group(1).strip()
    cols, ascending = [], []
    for part in [p.strip() for p in order_str.split(',')]:
        tokens = part.split()
        col = tokens[0]
        asc = len(tokens) < 2 or tokens[1].upper() != 'DESC'
        if col in df.columns:
            cols.append(col)
            ascending.append(asc)
    if cols:
        df = df.sort_values(cols, ascending=ascending)
    return df.reset_index(drop=True)


# ── Public API ────────────────────────────────────────────────────────────────

def read_sql(query: str, params=None) -> pd.DataFrame:
    """Execute a SELECT and return a DataFrame."""

    if _BACKEND == "supabase":
        if _is_simple_select(query, params):
            # Use REST client for full-table reads (fast, no libpq)
            return _supabase_full_table(query)
        else:
            # Use psycopg for parameterised queries
            return _pg_read_sql(query, params)

    elif _BACKEND == "postgres":
        return _pg_read_sql(query, params)

    else:
        with get_conn() as conn:
            return pd.read_sql(query, conn, params=params)


def execute(query: str, params=None, many: bool = False):
    """Execute an INSERT / UPDATE / DELETE."""

    if _BACKEND in ("supabase", "postgres"):
        pg_query = query.replace("?", "%s")
        with _pg_conn() as conn:
            cursor = conn.cursor()
            if many:
                cursor.executemany(pg_query, params or [])
            else:
                cursor.execute(pg_query, params or ())

    else:
        with get_conn() as conn:
            cursor = conn.cursor()
            if many:
                cursor.executemany(query, params or [])
            else:
                cursor.execute(query, params or ())


# ── Supabase REST (full-table reads) ──────────────────────────────────────────

def _supabase_full_table(query: str) -> pd.DataFrame:
    """Fetch all rows from a table via Supabase REST with pagination."""
    sb = _get_supabase()
    table = _extract_table(query)
    PAGE_SIZE = 1000
    all_data = []
    offset = 0
    while True:
        resp = sb.table(table).select("*").range(offset, offset + PAGE_SIZE - 1).execute()
        batch = resp.data
        if not batch:
            break
        all_data.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if not all_data:
        return pd.DataFrame()
    return _apply_order(pd.DataFrame(all_data), query)


# ── psycopg reads (parameterised queries) ────────────────────────────────────

def _pg_read_sql(query: str, params=None) -> pd.DataFrame:
    """Execute a parameterised SELECT via psycopg."""
    pg_query = query.replace("?", "%s")
    with _pg_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(pg_query, params or ())
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)
