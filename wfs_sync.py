"""
sync_to_supabase.py — Upload local SQLite data to Supabase (PostgreSQL).

Run this after each scraper/model run to push fresh data to the cloud.

Usage:
    python sync_to_supabase.py

Requires:
    pip install psycopg2-binary pandas python-dotenv

Environment variable (in .env):
    DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres
"""

import os
import json
import sqlite3
import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

SAVE_FOLDER = r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy"

SQLITE_PATH = r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy\wfs_fantasy.db"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env file!")

# Tables to sync (order matters for foreign keys)
TABLES = [
    "players",
    "gameweeks",
    "historical_stats",
    "league_managers",
    "league_standings",
    "league_fines",
    "league_fines_payments",
    "league_rankings",
    "predictions",
    "prediction_history",
    "update_log",
    "forum_users",
    "forum_posts",
    "forum_polls",
    "forum_poll_votes",
]


def sqlite_to_postgres_type(sqlite_type: str) -> str:
    """Map SQLite column types to PostgreSQL types."""
    t = sqlite_type.upper()
    if "INT" in t:
        return "BIGINT"
    if "REAL" in t or "FLOAT" in t or "DOUBLE" in t:
        return "DOUBLE PRECISION"
    return "TEXT"


def ensure_table_exists(pg_cur, table: str, df: pd.DataFrame):
    """Create the table in Postgres if it doesn't exist, based on DataFrame dtypes."""
    cols = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        if "int" in dtype:
            pg_type = "BIGINT"
        elif "float" in dtype:
            pg_type = "DOUBLE PRECISION"
        else:
            # Check if object column actually contains integers (e.g. bytes-packed ints)
            sample = df[col].dropna().head(10)
            all_bytes = all(isinstance(v, bytes) for v in sample)
            if all_bytes:
                pg_type = "BIGINT"
            else:
                pg_type = "TEXT"
        cols.append(f'"{col}" {pg_type}')

    # Drop and recreate to ensure correct types
    pg_cur.execute(f'DROP TABLE IF EXISTS "{table}"')
    create_sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(cols)});'
    pg_cur.execute(create_sql)


def sync_table(sqlite_conn, pg_conn, table: str, pk_cols):
    """Sync one table from SQLite to PostgreSQL using truncate + insert."""
    try:
        df = pd.read_sql(f"SELECT * FROM {table}", sqlite_conn)
    except Exception as e:
        print(f"  ⚠️  {table}: not found in SQLite ({e}), skipping.")
        return 0

    if df.empty:
        print(f"  ℹ️  {table}: empty, skipping.")
        return 0

    # Replace NaN with None for psycopg2
    df = df.where(pd.notnull(df), None)

    # Convert all columns to native Python types to avoid bytea/type errors
    for col in df.columns:
        if df[col].dtype == object:
            # Convert bytes to int if they look like packed integers
            def convert_val(x):
                if isinstance(x, bytes):
                    try:
                        return int.from_bytes(x, byteorder='little', signed=True)
                    except Exception:
                        return x.decode('utf-8', errors='replace')
                return x
            df[col] = df[col].apply(convert_val)
        elif str(df[col].dtype).startswith('int'):
            df[col] = df[col].apply(lambda x: int(x) if x is not None else None)
        elif str(df[col].dtype).startswith('float'):
            df[col] = df[col].apply(lambda x: float(x) if x is not None else None)

    pg_cur = pg_conn.cursor()
    ensure_table_exists(pg_cur, table, df)

    cols = list(df.columns)
    col_str = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))

    # Truncate then insert — simple and reliable, no constraint needed
    pg_cur.execute(f'TRUNCATE TABLE "{table}"')
    insert_sql = f'INSERT INTO "{table}" ({col_str}) VALUES ({placeholders})'
    rows = [tuple(row) for row in df.itertuples(index=False, name=None)]
    psycopg2.extras.execute_batch(pg_cur, insert_sql, rows, page_size=500)

    pg_conn.commit()
    return len(df)


def main():
    start = datetime.now()
    print("=" * 60)
    print("  🔄 SYNC: SQLite → Supabase")
    print(f"  {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = psycopg2.connect(DATABASE_URL)

    total_rows = 0
    for table in TABLES:
        print(f"\n  📋 {table}...", end=" ")
        n = sync_table(sqlite_conn, pg_conn, table, None)
        print(f"{n} rows")
        total_rows += n

    sqlite_conn.close()

    # --- Sync feature importance JSON ---
    fi_path = os.path.join(SAVE_FOLDER, 'feature_importance_history.json')
    if os.path.exists(fi_path):
        print(f"\n  📋 feature_importance_history...", end=" ")
        with open(fi_path, 'r') as f:
            history = json.load(f)

        pg_cur = pg_conn.cursor()
        pg_cur.execute("""
            CREATE TABLE IF NOT EXISTS feature_importance_history (
                gw TEXT,
                position TEXT,
                feature TEXT,
                importance DOUBLE PRECISION
            )
        """)
        pg_cur.execute("TRUNCATE TABLE feature_importance_history")

        rows = []
        for gw, positions in history.items():
            for pos, features in positions.items():
                for feat, imp in features.items():
                    rows.append((gw, pos, feat, float(imp)))

        psycopg2.extras.execute_batch(
            pg_cur,
            "INSERT INTO feature_importance_history (gw, position, feature, importance) VALUES (%s, %s, %s, %s)",
            rows,
            page_size=500
        )
        pg_conn.commit()
        print(f"{len(rows)} rows")
        total_rows += len(rows)
    else:
        print(f"\n  ⚠️  feature_importance_history.json not found, skipping.")

    # --- Sync fixtures from Calendar.xlsx ---
    fixtures_path = os.path.join(SAVE_FOLDER, r"Multas\Calendar.xlsx")
    if os.path.exists(fixtures_path):
        print(f"\n  📋 fixtures...", end=" ")
        df_fix = pd.read_excel(fixtures_path)
        df_fix = df_fix.rename(columns={
            'J': 'gw_number',
            'Eq. Casa': 'home_team',
            'Eq. Fora': 'away_team',
            'Data': 'date',
        })
        df_fix['gw_number'] = pd.to_numeric(df_fix['gw_number'], errors='coerce')
        df_fix = df_fix.dropna(subset=['gw_number'])
        df_fix['gw_number'] = df_fix['gw_number'].astype(int)

        # Keep only relevant columns
        keep_cols = [c for c in ['gw_number', 'home_team', 'away_team', 'date'] if c in df_fix.columns]
        df_fix = df_fix[keep_cols]
        df_fix = df_fix.where(pd.notnull(df_fix), None)

        pg_cur = pg_conn.cursor()
        pg_cur.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                gw_number BIGINT,
                home_team TEXT,
                away_team TEXT,
                date TEXT
            )
        """)
        pg_cur.execute("TRUNCATE TABLE fixtures")

        cols = list(df_fix.columns)
        placeholders = ", ".join(["%s"] * len(cols))
        insert_sql = f'INSERT INTO fixtures ({", ".join(cols)}) VALUES ({placeholders})'
        rows = [tuple(row) for row in df_fix.itertuples(index=False, name=None)]
        psycopg2.extras.execute_batch(pg_cur, insert_sql, rows, page_size=500)
        pg_conn.commit()
        print(f"{len(rows)} rows")
        total_rows += len(rows)
    else:
        print(f"\n  ⚠️  Calendar.xlsx not found, skipping fixtures.")

    pg_conn.close()

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"  ✅ Sync complete: {total_rows} rows in {elapsed:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
