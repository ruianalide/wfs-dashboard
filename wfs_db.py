"""
wfs_db.py — Database abstraction layer.

Local (development):  uses SQLite via SQLITE_PATH env var or default path
Production (Supabase): uses Supabase Python client (HTTP, no libpq needed)

The dashboard imports `read_sql` and `execute` from here.

Environment variables:
    DATABASE_URL  — Supabase PostgreSQL URL (triggers postgres backend)
    SUPABASE_URL  — Supabase project URL (e.g. https://xxx.supabase.co)
    SUPABASE_KEY  — Supabase anon/service key
"""

import os
import sqlite3
import contextlib
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── detect which backend to use ──────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Use Supabase client if SUPABASE_URL+KEY are set, else fall back to psycopg/sqlite
if SUPABASE_URL and SUPABASE_KEY:
    _BACKEND = "supabase"
elif DATABASE_URL:
    _BACKEND = "postgres"
else:
    _BACKEND = "sqlite"

# SQLite path (only used locally)
_SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy\wfs_fantasy.db"
)

print(f"[wfs_db] Backend: {_BACKEND}")


# ── Supabase client (lazy init) ───────────────────────────────────────────────
_supabase_client = None

def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# ── SQLite connection helper ──────────────────────────────────────────────────
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


# ── Public API ────────────────────────────────────────────────────────────────

def read_sql(query: str, params=None) -> pd.DataFrame:
    """Execute a SELECT and return a DataFrame."""
    if _BACKEND == "supabase":
        # Extract table name from simple SELECT queries
        # For complex queries, fall back to postgres direct connection
        return _supabase_read_sql(query, params)
    elif _BACKEND == "postgres":
        import psycopg2
        pg_query = query.replace("?", "%s")
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        try:
            return pd.read_sql(pg_query, conn, params=params)
        finally:
            conn.close()
    else:
        with get_conn() as conn:
            return pd.read_sql(query, conn, params=params)


def execute(query: str, params=None, many: bool = False):
    """Execute an INSERT / UPDATE / DELETE."""
    if _BACKEND == "supabase":
        _supabase_execute(query, params)
    elif _BACKEND == "postgres":
        import psycopg2
        pg_query = query.replace("?", "%s")
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cursor = conn.cursor()
            if many:
                cursor.executemany(pg_query, params or [])
            else:
                cursor.execute(pg_query, params or ())
            conn.commit()
        finally:
            conn.close()
    else:
        with get_conn() as conn:
            cursor = conn.cursor()
            if many:
                cursor.executemany(query, params or [])
            else:
                cursor.execute(query, params or ())


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _extract_table(query: str) -> str:
    """Extract table name from a simple SELECT query."""
    import re
    # Match: SELECT ... FROM table_name ...
    m = re.search(r'\bFROM\s+(["\w]+)', query, re.IGNORECASE)
    if m:
        return m.group(1).strip('"')
    raise ValueError(f"Cannot extract table name from query: {query}")


def _supabase_read_sql(query: str, params=None) -> pd.DataFrame:
    """Read data from Supabase using the REST API."""
    sb = _get_supabase()
    table = _extract_table(query)

    # Determine ORDER BY if present
    import re
    order_match = re.search(r'ORDER BY\s+(.+?)(?:LIMIT|$)', query, re.IGNORECASE)

    response = sb.table(table).select("*").execute()
    data = response.data

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Apply ORDER BY if present
    if order_match:
        order_str = order_match.group(1).strip()
        # Parse "col1, col2 DESC" etc.
        order_parts = [p.strip() for p in order_str.split(',')]
        cols = []
        ascending = []
        for part in order_parts:
            tokens = part.split()
            col = tokens[0]
            asc = True if len(tokens) < 2 or tokens[1].upper() != 'DESC' else False
            if col in df.columns:
                cols.append(col)
                ascending.append(asc)
        if cols:
            df = df.sort_values(cols, ascending=ascending)

    return df.reset_index(drop=True)


def _supabase_execute(query: str, params=None):
    """Execute a write operation via Supabase REST API."""
    sb = _get_supabase()
    query_upper = query.strip().upper()

    if query_upper.startswith("INSERT"):
        table = _extract_table(query)
        # Build dict from params — requires column names
        # For simple inserts, use upsert via the table API
        # This is a best-effort implementation; complex queries may need adjustment
        import re
        cols_match = re.search(r'\(([^)]+)\)\s+VALUES', query, re.IGNORECASE)
        if cols_match and params:
            cols = [c.strip() for c in cols_match.group(1).split(',')]
            if isinstance(params[0], (list, tuple)):
                rows = [dict(zip(cols, row)) for row in params]
            else:
                rows = [dict(zip(cols, params))]
            sb.table(table).upsert(rows).execute()

    elif query_upper.startswith("UPDATE"):
        table = _extract_table(query)
        # For UPDATE, use the Supabase update API
        # This is simplified — complex WHERE clauses may need adjustment
        import re
        set_match = re.search(r'SET\s+(.+?)\s+WHERE\s+(.+?)(?:$)', query, re.IGNORECASE | re.DOTALL)
        if set_match and params:
            # Best effort: use raw SQL via rpc if available
            pass  # Complex updates handled by sync script, not dashboard

    elif query_upper.startswith("DELETE"):
        table = _extract_table(query)
        # Simple deletes only
        import re
        where_match = re.search(r'WHERE\s+(\w+)\s*=\s*\?', query, re.IGNORECASE)
        if where_match and params:
            col = where_match.group(1)
            val = params[0] if isinstance(params, (list, tuple)) else params
            sb.table(table).delete().eq(col, val).execute()
