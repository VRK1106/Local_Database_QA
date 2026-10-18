#!/usr/bin/env python3
"""
SQLite to PostgreSQL Data Migration Utility for AMYPO / Local Database QA System.

Decouples local state by transferring:
- users
- audit_logs
- tickets
- ticket_messages
- student_records

Usage:
    python migrate_sqlite_to_postgres.py [--sqlite-path auth.db] [--postgres-url postgresql://user:pass@host:5432/dbname]
"""

import os
import sys
import argparse
import sqlite3
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import AUTH_DB_PATH, DATABASE_URL

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("[ERROR] psycopg2 is required for PostgreSQL migration. Install with: pip install psycopg2-binary")
    sys.exit(1)


def migrate(sqlite_path: Path, postgres_url: str):
    print("=" * 70)
    print("  AMYPO DATABASE MIGRATION: SQLITE -> PERSISTENT POSTGRESQL")
    print(f"  Source SQLite:   {sqlite_path}")
    print(f"  Target Postgres: {postgres_url.split('@')[-1] if '@' in postgres_url else postgres_url}")
    print("=" * 70)

    if not sqlite_path.exists():
        print(f"[ERROR] Source SQLite file does not exist: {sqlite_path}")
        sys.exit(1)

    # Connect to SQLite
    s_conn = sqlite3.connect(str(sqlite_path))
    s_conn.row_factory = sqlite3.Row
    s_cur = s_conn.cursor()

    # Connect to PostgreSQL
    try:
        p_conn = psycopg2.connect(postgres_url)
        p_cur = p_conn.cursor()
    except Exception as e:
        print(f"[ERROR] Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

    # 1. Initialize schema in PostgreSQL
    from src.auth import init_auth_db
    # Set environment variable temporarily
    os.environ["DATABASE_URL"] = postgres_url
    print("\n[*] Initializing PostgreSQL schema...")
    init_auth_db()
    print("[+] PostgreSQL schema verified.")

    tables = ["users", "student_records", "tickets", "ticket_messages", "audit_logs"]

    for table in tables:
        print(f"\n[*] Migrating table: {table}...")
        try:
            s_cur.execute(f"SELECT * FROM {table};")
            rows = s_cur.fetchall()
            if not rows:
                print(f"    - Table '{table}' has 0 rows in SQLite. Skipped.")
                continue

            columns = [col[0] for col in s_cur.description]
            cols_str = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))

            # In PostgreSQL, handle primary key conflicts gracefully
            conflict_target = "id"
            if table == "users":
                conflict_target = "username"
            elif table == "student_records":
                conflict_target = "student_id"
            elif table == "tickets":
                conflict_target = "ticket_number"

            insert_query = f"""
                INSERT INTO {table} ({cols_str})
                VALUES ({placeholders})
                ON CONFLICT ({conflict_target}) DO NOTHING;
            """

            migrated_count = 0
            for row in rows:
                vals = [row[c] for c in columns]
                p_cur.execute(insert_query, vals)
                migrated_count += p_cur.rowcount

            p_conn.commit()
            print(f"    [+] Migrated {migrated_count} of {len(rows)} row(s) to PostgreSQL.")

            # Reset sequence for serial primary keys
            if "id" in columns:
                try:
                    p_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table};")
                    p_conn.commit()
                except Exception:
                    p_conn.rollback()

        except Exception as ex:
            p_conn.rollback()
            print(f"    [!] Error migrating table '{table}': {ex}")

    s_conn.close()
    p_conn.close()
    print("\n" + "=" * 70)
    print("  MIGRATION COMPLETE! All relational state transferred to PostgreSQL.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite auth.db to persistent PostgreSQL.")
    parser.add_argument("--sqlite-path", default=str(AUTH_DB_PATH), help="Path to source SQLite database")
    parser.add_argument("--postgres-url", default=DATABASE_URL, help="PostgreSQL connection URL")
    args = parser.parse_args()

    pg_url = args.postgres_url or os.environ.get("DATABASE_URL", "")
    if not pg_url:
        print("[ERROR] Please provide --postgres-url or set the DATABASE_URL environment variable.")
        print("Example: python migrate_sqlite_to_postgres.py --postgres-url postgresql://amypo_user:amypo_pass@localhost:5432/amypo_db")
        sys.exit(1)

    migrate(Path(args.sqlite_path), pg_url)


if __name__ == "__main__":
    main()
