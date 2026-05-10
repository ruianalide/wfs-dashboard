"""
wfs_db.py — Database abstraction layer.

Local:       SQLite
Production:  Supabase REST client only (no psycopg2/libpq needed)

The dashboard imports `read_sql` and `execute` from here.
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

_BACKEND = "supabase" if (SUPABASE_URL and SUPABASE_KEY) else "sqlite"

_SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy\wfs_fantasy.db"
)

print(f"[wfs_db] Backend: {_BACKEND}")

# ── Supabase client (lazy) ────────────────────────────────────────────────────
_sb = None

def _get_sb():
    global _sb
    if _sb is None:
        from supabase import create_client
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── SQLite helper (local) ─────────────────────────────────────────────────────
@contextlib.contextmanager
def get_conn():
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


# ── SQL parsing helpers ───────────────────────────────────────────────────────

def _extract_table(query: str) -> str:
    m = re.search(r'\bFROM\s+(["\w]+)', query, re.IGNORECASE)
    if m:
        return m.group(1).strip('"')
    # Also handle INSERT INTO table
    m2 = re.search(r'\bINTO\s+(["\w]+)', query, re.IGNORECASE)
    if m2:
        return m2.group(1).strip('"')
    raise ValueError(f"Cannot extract table name from: {query}")


def _parse_where(query: str, params) -> dict:
    """
    Parse simple WHERE col = ? AND col2 = ? clauses.
    Returns dict of {col: value} for Supabase .eq() filters.
    """
    where_match = re.search(r'WHERE\s+(.+?)(?:ORDER BY|LIMIT|GROUP BY|$)',
                             query, re.IGNORECASE | re.DOTALL)
    if not where_match or not params:
        return {}

    where_str = where_match.group(1).strip()
    # Split on AND
    conditions = re.split(r'\bAND\b', where_str, flags=re.IGNORECASE)
    filters = {}
    param_list = list(params) if params else []
    param_idx = 0

    for cond in conditions:
        # Match: col = ? or col = %s
        m = re.match(r'\s*(\w+)\s*=\s*[?%s]', cond.strip())
        if m and param_idx < len(param_list):
            filters[m.group(1)] = param_list[param_idx]
            param_idx += 1

    return filters


def _apply_order(df: pd.DataFrame, query: str) -> pd.DataFrame:
    order_match = re.search(r'ORDER BY\s+(.+?)(?:LIMIT|$)', query, re.IGNORECASE)
    if not order_match or df.empty:
        return df
    cols, ascending = [], []
    for part in [p.strip() for p in order_match.group(1).strip().split(',')]:
        tokens = part.split()
        col = tokens[0]
        asc = len(tokens) < 2 or tokens[1].upper() != 'DESC'
        if col in df.columns:
            cols.append(col)
            ascending.append(asc)
    if cols:
        df = df.sort_values(cols, ascending=ascending)
    return df.reset_index(drop=True)


def _parse_limit(query: str):
    m = re.search(r'LIMIT\s+(\d+)', query, re.IGNORECASE)
    return int(m.group(1)) if m else None


# ── Public API ────────────────────────────────────────────────────────────────

def read_sql(query: str, params=None) -> pd.DataFrame:
    """Execute a SELECT and return a DataFrame."""
    if _BACKEND == "sqlite":
        with get_conn() as conn:
            return pd.read_sql(query, conn, params=params)

    # Supabase backend
    sb = _get_sb()
    table = _extract_table(query)
    filters = _parse_where(query, params)
    limit = _parse_limit(query)

    PAGE_SIZE = 1000
    all_data = []
    offset = 0

    try:
        while True:
            q = sb.table(table).select("*")
            for col, val in filters.items():
                q = q.eq(col, val)
            end = offset + PAGE_SIZE - 1
            if limit:
                end = min(end, offset + limit - 1)
            q = q.range(offset, end)
            resp = q.execute()
            batch = resp.data
            if not batch:
                break
            all_data.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            if limit and len(all_data) >= limit:
                all_data = all_data[:limit]
                break
            offset += PAGE_SIZE
    except Exception as e:
        print(f"[wfs_db] read_sql error on table '{table}': {e}")
        return pd.DataFrame()

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    return _apply_order(df, query)


def execute(query: str, params=None, many: bool = False):
    """Execute an INSERT / UPDATE / DELETE."""
    if _BACKEND == "sqlite":
        with get_conn() as conn:
            cursor = conn.cursor()
            if many:
                cursor.executemany(query, params or [])
            else:
                cursor.execute(query, params or ())
        return

    # Supabase backend — use REST API
    sb = _get_sb()
    q_upper = query.strip().upper()

    try:
        if q_upper.startswith("INSERT"):
            _sb_insert(sb, query, params, many)
        elif q_upper.startswith("UPDATE"):
            _sb_update(sb, query, params)
        elif q_upper.startswith("DELETE"):
            _sb_delete(sb, query, params)
    except Exception as e:
        print(f"[wfs_db] execute error: {e}")
        raise


# ── Supabase write helpers ────────────────────────────────────────────────────

def _sb_insert(sb, query: str, params, many: bool):
    table = _extract_table(query)
    cols_match = re.search(r'\(([^)]+)\)\s+VALUES', query, re.IGNORECASE)
    if not cols_match or not params:
        print(f"[wfs_db] INSERT skipped: cols_match={bool(cols_match)}, params={bool(params)}")
        return
    cols = [c.strip() for c in cols_match.group(1).split(',')]

    if many:
        rows = [dict(zip(cols, row)) for row in params]
    else:
        rows = [dict(zip(cols, params))]

    print(f"[wfs_db] INSERT into {table}: {rows}")
    try:
        resp = sb.table(table).upsert(rows).execute()
        print(f"[wfs_db] INSERT response: {resp.data}")
    except Exception as e:
        print(f"[wfs_db] INSERT error: {e}")
        raise


def _sb_update(sb, query: str, params):
    table = _extract_table(query)
    # Parse SET col = ?, col2 = ? WHERE col3 = ?
    set_match = re.search(r'SET\s+(.+?)\s+WHERE\s+(.+?)$', query,
                          re.IGNORECASE | re.DOTALL)
    if not set_match or not params:
        return

    set_str = set_match.group(1)
    where_str = set_match.group(2)

    set_cols = [m.group(1) for m in re.finditer(r'(\w+)\s*=\s*[?%s]', set_str)]
    where_cols = [m.group(1) for m in re.finditer(r'(\w+)\s*=\s*[?%s]', where_str)]

    param_list = list(params)
    n_set = len(set_cols)
    set_vals = dict(zip(set_cols, param_list[:n_set]))
    where_vals = dict(zip(where_cols, param_list[n_set:]))

    q = sb.table(table).update(set_vals)
    for col, val in where_vals.items():
        q = q.eq(col, val)
    q.execute()


def _sb_delete(sb, query: str, params):
    table = _extract_table(query)
    filters = _parse_where(query, params)
    if not filters:
        return
    q = sb.table(table).delete()
    for col, val in filters.items():
        q = q.eq(col, val)
    q.execute()
