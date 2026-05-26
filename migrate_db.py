import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

SQLITE_PATH = os.environ.get("DB_PATH", "helloagain.db")
POSTGRES_URL = os.environ.get("DATABASE_URL")

if not POSTGRES_URL:
    print("DATABASE_URL not set in .env")
    exit(1)

print("Connecting to SQLite...")
sqlite_con = sqlite3.connect(SQLITE_PATH)
sqlite_con.row_factory = sqlite3.Row
sqlite_cur = sqlite_con.cursor()

print("Connecting to PostgreSQL...")
pg_con = psycopg2.connect(POSTGRES_URL)
pg_cur = pg_con.cursor()

tables_to_migrate = [
    "customers",
    "conversations",
    "knowledge_base",
    "whatsapp_settings"
]

print("Truncating target tables...")
# Truncate to avoid duplicate conflicts if script is run multiple times or if seed data exists
for table in tables_to_migrate:
    pg_cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")

for table in tables_to_migrate:
    print(f"Migrating table: {table}...")
    sqlite_cur.execute(f"SELECT * FROM {table}")
    rows = sqlite_cur.fetchall()
    
    if not rows:
        print(f"  No rows to migrate for {table}")
        continue
        
    # Get column names
    columns = rows[0].keys()
    col_names = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    
    insert_query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
    
    for row in rows:
        pg_cur.execute(insert_query, tuple(row))
        
    print(f"  Migrated {len(rows)} rows.")

    # Update sequences if there is an 'id' column so Postgres auto-increment doesn't collide
    if "id" in columns:
        try:
            pg_cur.execute(f"SELECT setval('{table}_id_seq', (SELECT COALESCE(MAX(id), 1) FROM {table}));")
            print(f"  Reset ID sequence for {table}.")
        except Exception as e:
            print(f"  Warning: Could not reset sequence for {table}: {e}")
            pg_con.rollback() # recover from error to continue commit

pg_con.commit()
print("Migration completed successfully!")

sqlite_con.close()
pg_con.close()
