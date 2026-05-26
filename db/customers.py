"""
db/customers.py — HelloAgain customer store with analytics support.
"""

import sqlite3
import os
import tempfile
from datetime import datetime, timezone, timedelta

# ── Resolve a writable DB path ────────────────────────────────────────────────
# Priority:
#   1. $DB_PATH env var (e.g. /data/helloagain.db on Render with a disk)
#   2. Fallback to /tmp/<basename> when the configured directory can't be
#      created (e.g. Render free plan with no persistent disk attached).
# Data stored in /tmp is lost on restart — the app still boots correctly.

_configured = os.environ.get("DB_PATH", "helloagain.db")
_db_dir = os.path.dirname(_configured)  # empty string for bare filenames

if _db_dir:
    if os.path.isdir(_db_dir):
        # Directory already exists (disk is mounted) — use it as-is.
        DB_PATH = _configured
    else:
        try:
            os.makedirs(_db_dir, exist_ok=True)
            DB_PATH = _configured
        except (PermissionError, OSError) as _exc:
            # Persistent disk not mounted (free plan or first-time deploy).
            # Fall back to a temp file so the app can still start.
            _fallback = os.path.join(
                tempfile.gettempdir(), os.path.basename(_configured)
            )
            print(
                f"[WARNING] Cannot create DB directory '{_db_dir}': {_exc}\n"
                f"[WARNING] Falling back to '{_fallback}'. "
                "Data will NOT persist across restarts.\n"
                "[WARNING] Add a Persistent Disk in your Render dashboard "
                "and set DB_PATH=/data/helloagain.db to fix this."
            )
            DB_PATH = _fallback
else:
    DB_PATH = _configured


from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        pass

class DBWrapper:
    def __init__(self, con, is_postgres):
        self.con = con
        self.is_postgres = is_postgres

    def execute(self, query, params=None):
        if self.is_postgres:
            query = query.replace("?", "%s")
            if "INSERT OR REPLACE INTO whatsapp_settings" in query:
                query = query.replace("INSERT OR REPLACE INTO whatsapp_settings", "INSERT INTO whatsapp_settings")
                query += " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            
            cursor = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor
        else:
            if params:
                return self.con.execute(query, params)
            else:
                return self.con.execute(query)

    def executescript(self, script):
        if self.is_postgres:
            script = script.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            cursor = self.con.cursor()
            cursor.execute(script)
            return cursor
        else:
            return self.con.executescript(script)

@contextmanager
def _conn():
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        con = psycopg2.connect(DATABASE_URL)
        wrapper = DBWrapper(con, is_postgres=True)
        try:
            yield wrapper
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
    else:
        con = sqlite3.connect(DB_PATH, check_same_thread=False)
        con.row_factory = sqlite3.Row
        wrapper = DBWrapper(con, is_postgres=False)
        try:
            with con:
                yield wrapper
        finally:
            con.close()


import re

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
            status        TEXT    DEFAULT 'normal',
            tag           TEXT    DEFAULT 'normal',
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

        CREATE TABLE IF NOT EXISTS knowledge_base (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            category      TEXT NOT NULL,
            brand         TEXT NOT NULL,
            in_stock      INTEGER DEFAULT 1,
            stock_count   INTEGER,
            image_url     TEXT,
            content       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS whatsapp_settings (
            key           TEXT PRIMARY KEY,
            value         TEXT
        );

        CREATE TABLE IF NOT EXISTS search_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT NOT NULL,
            query         TEXT NOT NULL,
            results_count INTEGER DEFAULT 0,
            ts            TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS product_interactions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       TEXT NOT NULL,
            product_category TEXT NOT NULL,
            product_brand    TEXT NOT NULL,
            interaction_type TEXT NOT NULL,
            ts               TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id     TEXT NOT NULL,
            task_type      TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            status         TEXT DEFAULT 'pending',
            payload        TEXT
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            type           TEXT NOT NULL,
            message        TEXT NOT NULL,
            read           INTEGER DEFAULT 0,
            ts             TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analytics_cache (
            session_id     TEXT PRIMARY KEY,
            analysis_json  TEXT NOT NULL,
            cached_at      TEXT NOT NULL
        );
        """)
        # Add new columns if upgrading from old DB
        for col, definition in [
            ("followup_sent",    "INTEGER DEFAULT 0"),
            ("notes",            "TEXT"),
            ("phone",            "TEXT"),
            ("name",             "TEXT"),
            ("engagement_score", "INTEGER DEFAULT 0"),
        ]:
            try:
                if getattr(con, "is_postgres", False):
                    con.execute("SAVEPOINT col_sp")
                con.execute(f"ALTER TABLE customers ADD COLUMN {col} {definition}")
                if getattr(con, "is_postgres", False):
                    con.execute("RELEASE SAVEPOINT col_sp")
            except Exception:
                if getattr(con, "is_postgres", False):
                    con.execute("ROLLBACK TO SAVEPOINT col_sp")
                pass

        # Seed knowledge base if empty
        row = con.execute("SELECT COUNT(*) FROM knowledge_base").fetchone()
        if row[0] == 0:
            try:
                from knowledge_base import business_data
                for item in business_data:
                    con.execute(
                        """INSERT INTO knowledge_base (category, brand, in_stock, stock_count, image_url, content)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            item.get("category"),
                            item.get("brand", "General"),
                            1 if item.get("in_stock", True) else 0,
                            item.get("stock_count"),
                            item.get("image_url"),
                            item.get("content")
                        )
                    )
            except Exception as e:
                print(f"[WARNING] Seeding knowledge_base failed: {e}")


def upsert_customer(session_id: str, **kwargs):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        row = con.execute("SELECT id FROM customers WHERE session_id=?", (session_id,)).fetchone()
        if row:
            sets = ", ".join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [now, session_id]
            con.execute(f"UPDATE customers SET {sets}, last_seen=? WHERE session_id=?", vals)
        else:
            kwargs.setdefault("status", "normal")
            kwargs.setdefault("tag", "normal")
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

def log_turn_start(session_id: str, user_query: str, topic: str, budget: str, tag: str):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        row = con.execute("SELECT id FROM customers WHERE session_id=?", (session_id,)).fetchone()
        if row:
            con.execute("UPDATE customers SET topic=?, budget=?, tag=?, last_seen=? WHERE session_id=?", 
                        (topic, budget, tag, now, session_id))
        else:
            con.execute("INSERT INTO customers (session_id, first_seen, last_seen, topic, budget, tag, status) VALUES (?,?,?,?,?,?,?)", 
                        (session_id, now, now, topic, budget, tag, "normal"))
        con.execute("INSERT INTO conversations (session_id, role, content, ts) VALUES (?,?,?,?)",
                    (session_id, "user", user_query, now))

def log_turn_end(session_id: str, reply: str, resolved: bool, tag: str, engagement_score: int, topic: str, budget: str, turn_count: int):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        if resolved:
            con.execute(
                "UPDATE customers SET topic=?, budget=?, tag=?, status=?, turn_count=?, silent_turns=0, engagement_score=?, last_seen=? WHERE session_id=?",
                (topic, budget, tag, tag, turn_count, engagement_score, now, session_id)
            )
        else:
            con.execute(
                "UPDATE customers SET topic=?, budget=?, tag=?, status=?, turn_count=?, silent_turns=silent_turns+1, engagement_score=?, last_seen=? WHERE session_id=?",
                (topic, budget, tag, tag, turn_count, engagement_score, now, session_id)
            )
        con.execute("INSERT INTO conversations (session_id, role, content, ts) VALUES (?,?,?,?)",
                    (session_id, "assistant", reply, now))


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
        if notes is not None:
            con.execute("UPDATE customers SET notes=? WHERE session_id=?", (notes, session_id))


def mark_followup_sent(session_id: str):
    with _conn() as con:
        con.execute(
            "UPDATE customers SET followup_sent=1 WHERE session_id=?", (session_id,)
        )


def save_engagement_score(session_id: str, score: int):
    """Persist the live AI engagement score (0-100) for this session."""
    with _conn() as con:
        con.execute(
            "UPDATE customers SET engagement_score=? WHERE session_id=?",
            (score, session_id),
        )


def get_all_customers():
    with _conn() as con:
        rows = con.execute("SELECT * FROM customers ORDER BY last_seen DESC").fetchall()
        return [dict(r) for r in rows]


def get_silent_customers(hours: int = 24):
    """
    Customers tagged 'active' or 'follow_up' who haven't been seen in `hours` hours.
    These are the priority recovery targets surfaced in the dashboard.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM customers
               WHERE tag IN ('active','follow_up','recoverable')
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


# ── Knowledge Base Helpers ───────────────────────────────────────────────────
def get_all_kb_items():
    with _conn() as con:
        rows = con.execute("SELECT * FROM knowledge_base ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def add_kb_item(category: str, brand: str, in_stock: bool, stock_count: int = None, image_url: str = None, content: str = ""):
    with _conn() as con:
        row = con.execute(
            """INSERT INTO knowledge_base (category, brand, in_stock, stock_count, image_url, content)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (category, brand, 1 if in_stock else 0, stock_count, image_url, content)
        ).fetchone()
        return row[0] if row else None


def update_kb_item(item_id: int, category: str, brand: str, in_stock: bool, stock_count: int = None, image_url: str = None, content: str = ""):
    with _conn() as con:
        con.execute(
            """UPDATE knowledge_base
               SET category=?, brand=?, in_stock=?, stock_count=?, image_url=?, content=?
               WHERE id=?""",
            (category, brand, 1 if in_stock else 0, stock_count, image_url, content, item_id)
        )


def delete_kb_item(item_id: int):
    with _conn() as con:
        con.execute("DELETE FROM knowledge_base WHERE id=?", (item_id,))


# ── WhatsApp Settings Helpers ──────────────────────────────────────────────────
def get_whatsapp_settings():
    with _conn() as con:
        rows = con.execute("SELECT key, value FROM whatsapp_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def save_whatsapp_settings(settings: dict):
    with _conn() as con:
        for k, v in settings.items():
            con.execute("INSERT OR REPLACE INTO whatsapp_settings (key, value) VALUES (?, ?)", (k, str(v)))


def parse_budget_number(budget_str: str) -> float:
    if not budget_str:
        return 0.0
    cleaned = re.sub(r'[^\d.]', '', budget_str)
    try:
        if cleaned:
            return float(cleaned)
    except ValueError:
        pass
    return 0.0


def get_analytics():
    with _conn() as con:
        total        = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        active       = con.execute("SELECT COUNT(*) FROM customers WHERE tag='active'").fetchone()[0]
        follow_up    = con.execute("SELECT COUNT(*) FROM customers WHERE tag='follow_up'").fetchone()[0]
        recoverable  = con.execute("SELECT COUNT(*) FROM customers WHERE tag='recoverable'").fetchone()[0]
        normal       = con.execute("SELECT COUNT(*) FROM customers WHERE tag='normal'").fetchone()[0]
        converted    = con.execute("SELECT COUNT(*) FROM customers WHERE converted=1").fetchone()[0]
        silent       = len(get_silent_customers(24))
        with_phone   = con.execute("SELECT COUNT(*) FROM customers WHERE phone IS NOT NULL AND phone != ''").fetchone()[0]

        # ── Revenue Intelligence ───────────────────────────────────────────────
        # Potential: budget sum from active/follow-up leads not yet converted
        potential_revenue = 0.0
        pot_rows = con.execute(
            "SELECT budget FROM customers WHERE tag IN ('active','follow_up') AND converted=0"
        ).fetchall()
        for r in pot_rows:
            potential_revenue += parse_budget_number(r[0])

        # Recovered: budget sum of previously recoverable/follow-up leads now converted
        recovered_revenue = 0.0
        rec_rows = con.execute(
            "SELECT budget FROM customers WHERE tag IN ('recoverable', 'follow_up') AND converted=1"
        ).fetchall()
        for r in rec_rows:
            recovered_revenue += parse_budget_number(r[0])

        # Avg engagement score
        avg_score = con.execute("SELECT AVG(engagement_score) FROM customers").fetchone()[0] or 0
        try:
            avg_score = round(float(avg_score), 1)
        except Exception:
            avg_score = 0

        avg_turns = con.execute("SELECT AVG(turn_count) FROM customers").fetchone()[0] or 0
        try:
            avg_turns = round(float(avg_turns), 1)
        except Exception:
            avg_turns = 0

        percent_converted = round((converted / total) * 100, 1) if total else 0

        # Daily active: customers seen in the last 24 hours
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        daily_active = con.execute(
            "SELECT COUNT(*) FROM customers WHERE last_seen >= ?", (cutoff,)
        ).fetchone()[0]

        # Top topics
        rows = con.execute(
            "SELECT topic, COUNT(*) as c FROM customers "
            "WHERE topic IS NOT NULL AND topic != '' "
            "GROUP BY topic ORDER BY c DESC LIMIT 5"
        ).fetchall()
        top_topics = [{"topic": r[0], "count": r[1]} for r in rows]

        return {
            # New 4-class counts
            "total":              total,
            "active":             active,
            "follow_up":          follow_up,
            "recoverable":        recoverable,
            "normal":             normal,
            "converted":          converted,
            # Legacy fields kept so existing dashboard widgets don't break
            "hot":                active,
            "warm":               follow_up,
            "inactive":           normal,
            "vip":                0,
            # Engagement & activity
            "silent":             silent,
            "with_phone":         with_phone,
            "avg_turns":          avg_turns,
            "avg_engagement":     avg_score,
            "percent_converted":  percent_converted,
            "daily_active":       daily_active,
            "top_topics":         top_topics,
            # Revenue Intelligence
            "potential_revenue_raw":  potential_revenue,
            "potential_revenue":      f"₦{potential_revenue:,.0f}",
            "recovered_revenue_raw":  recovered_revenue,
            "recovered_revenue":      f"₦{recovered_revenue:,.0f}",
        }


# ── Search & Interaction Helpers ──────────────────────────────────────────────
def log_search(session_id: str, query: str, results_count: int):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO search_logs (session_id, query, results_count, ts) VALUES (?, ?, ?, ?)",
            (session_id, query, results_count, now)
        )

def log_interaction(session_id: str, category: str, brand: str, interaction_type: str):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO product_interactions (session_id, product_category, product_brand, interaction_type, ts) VALUES (?, ?, ?, ?, ?)",
            (session_id, category, brand, interaction_type, now)
        )

init_db()
