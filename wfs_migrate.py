"""
wfs_migrate.py — Apply DB schema migrations.
Run once after updating wfs_model.py to add confidence_score.
"""
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = r"C:\Users\ruiana\OneDrive - amazon.com\Attachments\Personal\Fantasy\wfs_fantasy.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Add confidence_score column if it doesn't exist
try:
    cursor.execute("ALTER TABLE predictions ADD COLUMN confidence_score REAL DEFAULT 0")
    conn.commit()
    print("✅ Added confidence_score column to predictions table")
except Exception as e:
    if "duplicate column" in str(e).lower():
        print("ℹ️  confidence_score column already exists")
    else:
        print(f"⚠️  {e}")

conn.close()
print("Done.")
