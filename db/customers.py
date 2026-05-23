"""
db/customers.py — HelloAgain customer store with analytics support.
"""

import sqlite3
import os
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get("DB_PATH", "helloagain.db")

# Ensure the directory exists only when DB_PATH contains an explicit directory
# component (e.g. "/data/helloagain.db").  When it is a bare filename the
# dirname is just cwd, which already exists and may be read-only on Render.
_db_dir = os.path.dirname(DB_PATH)  # empty string when no dir component
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)


def _conn():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT    UNIQUE NOT NULL,
            name          TEXT,
            phone         TEXT,
            first_seen    TEXT    NOT NULL,
            last_seen     TEXT    NOT NULL,
            status        TEXT    DEFAULT 'new',
            tag           TEXT    DEFAULT 'new',
            topic         TEXT,
            budget        TEXT,
            turn_count    INTEGER DEFAULT 0,
            silent_turns  INTEGER DEFAULT 0,
            converted     INTEGER DEFAULT 0,
            followup_sent INTEGER DEFAULT 0,
            notes         TEXT
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            ts          TEXT NOT NULL
        );
        """)
        # Add new columns if upgrading from old DB
        for col, definition in [
            ("followup_sent", "INTEGER DEFAULT 0"),
            ("notes",         "TEXT"),
            ("phone",         "TEXT"),
            ("name",          "TEXT"),
        ]:
            try:
                con.execute(f"ALTER TABLE customers ADD COLUMN {col} {definition}")
            except Exception:
                pass


def upsert_customer(session_id: str, **kwargs):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        row = con.execute("SELECT id FROM customers WHERE session_id=?", (session_id,)).fetchone()
        if row:
            sets = ", ".join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [now, session_id]
            con.execute(f"UPDATE customers SET {sets}, last_seen=? WHERE session_id=?", vals)
        else:
            kwargs.setdefault("status", "new")
            kwargs.setdefault("tag", "new")
            cols = ", ".join(["session_id", "first_seen", "last_seen"] + list(kwargs.keys()))
            placeholders = ", ".join(["?"] * (3 + len(kwargs)))
            vals = [session_id, now, now] + list(kwargs.values())
            con.execute(f"INSERT INTO customers ({cols}) VALUES ({placeholders})", vals)


def log_message(session_id: str, role: str, content: str):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO conversations (session_id, role, content, ts) VALUES (?,?,?,?)",
            (session_id, role, content, now),
        )


def get_customer(session_id: str):
    with _conn() as con:
        row = con.execute("SELECT * FROM customers WHERE session_id=?", (session_id,)).fetchone()
        return dict(row) if row else None


def increment_turns(session_id: str, resolved: bool):
    with _conn() as con:
        if resolved:
            con.execute(
                "UPDATE customers SET turn_count=turn_count+1, silent_turns=0 WHERE session_id=?",
                (session_id,),
            )
        else:
            con.execute(
                "UPDATE customers SET turn_count=turn_count+1, silent_turns=silent_turns+1 WHERE session_id=?",
                (session_id,),
            )


def tag_customer(session_id: str, tag: str):
    with _conn() as con:
        con.execute(
            "UPDATE customers SET tag=?, status=? WHERE session_id=?",
            (tag, tag, session_id),
        )


def update_customer_info(session_id: str, name: str = None, phone: str = None, notes: str = None):
    with _conn() as con:
        if name:
            con.execute("UPDATE customers SET name=? WHERE session_id=?", (name, session_id))
        if phone:
            con.execute("UPDATE customers SET phone=? WHERE session_id=?", (phone, session_id))
        if notes:
            con.execute("UPDATE customers SET notes=? WHERE session_id=?", (notes, session_id))


def mark_followup_sent(session_id: str):
    with _conn() as con:
        con.execute(
            "UPDATE customers SET followup_sent=1 WHERE session_id=?", (session_id,)
        )


def get_all_customers():
    with _conn() as con:
        rows = con.execute("SELECT * FROM customers ORDER BY last_seen DESC").fetchall()
        return [dict(r) for r in rows]


def get_silent_customers(hours: int = 24):
    """Customers tagged hot/warm who haven't been seen in `hours` hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM customers
               WHERE tag IN ('hot','warm')
               AND last_seen < ?
               AND converted = 0
               AND followup_sent = 0
               ORDER BY last_seen ASC""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_conversation(session_id: str):
    with _conn() as con:
        rows = con.execute(
            "SELECT role, content, ts FROM conversations WHERE session_id=? ORDER BY ts",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_analytics():
    with _conn() as con:
        total     = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        hot       = con.execute("SELECT COUNT(*) FROM customers WHERE tag='hot'").fetchone()[0]
        warm      = con.execute("SELECT COUNT(*) FROM customers WHERE tag='warm'").fetchone()[0]
        converted = con.execute("SELECT COUNT(*) FROM customers WHERE tag='converted'").fetchone()[0]
        silent    = len(get_silent_customers(24))
        with_phone = con.execute("SELECT COUNT(*) FROM customers WHERE phone IS NOT NULL AND phone != ''").fetchone()[0]
        return {
            "total": total, "hot": hot, "warm": warm,
            "converted": converted, "silent": silent,
            "with_phone": with_phone,
        }


init_db()
