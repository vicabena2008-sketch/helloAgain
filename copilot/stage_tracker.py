"""
stage_tracker.py — HelloAgain Customer Stage & Health Score Tracker
Rule-based, zero-AI-cost customer journey management.

Stages (in order):
  new_lead       → Customer starts conversation
  interested     → Customer asks questions (price, size, availability)
  negotiating    → Customer discusses discount / price reduction
  considering    → Customer says "let me think" / "I'll get back to you"
  purchase_ready → Customer asks about payment / delivery / how to order
  purchased      → Customer has bought
  inactive       → Customer stops responding

Health Score (0–100):
  +10  Asked for price
  +15  Asked for delivery
  +10  Viewed product / asked about product
  +15  Negotiated price (serious buyer signal)
  +20  Asked about payment / ordering
  -20  No response for 3 days
  -10  No response for 24 hours
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from db.customers import _conn

# ── Stage definitions ──────────────────────────────────────────────────────────

STAGES = [
    "new_lead",
    "interested",
    "negotiating",
    "considering",
    "purchase_ready",
    "purchased",
    "inactive",
]

STAGE_LABELS = {
    "new_lead":       "New Lead",
    "interested":     "Interested",
    "negotiating":    "Negotiating",
    "considering":    "Considering",
    "purchase_ready": "Purchase Ready",
    "purchased":      "Purchased",
    "inactive":       "Inactive",
}

STAGE_COLORS = {
    "new_lead":       "#6366f1",
    "interested":     "#3b82f6",
    "negotiating":    "#f59e0b",
    "considering":    "#8b5cf6",
    "purchase_ready": "#10b981",
    "purchased":      "#22c55e",
    "inactive":       "#6b7280",
}

# ── Keyword patterns for stage detection ──────────────────────────────────────

_INTERESTED_PATTERNS = re.compile(
    r'\b(show me|what (do|does)|do you have|how much|price|cost|size|colour|color|'
    r'available|in stock|tell me|what about|which one|options|looking for|need|want)\b',
    re.IGNORECASE
)

_NEGOTIATING_PATTERNS = re.compile(
    r'\b(discount|reduce|last price|final price|can you do better|too expensive|'
    r'bring it down|lower it|better price|abeg|too much|last last|no be small money)\b',
    re.IGNORECASE
)

_CONSIDERING_PATTERNS = re.compile(
    r'\b(let me think|i.?ll think|i.?ll get back|maybe|not sure|consider|'
    r'i.?ll discuss|i.?ll check|later|i.?ll decide|still thinking|need to think)\b',
    re.IGNORECASE
)

_PURCHASE_READY_PATTERNS = re.compile(
    r'\b(how (do|can) i (order|pay|buy|get)|payment|account number|transfer|'
    r'pay now|i want to buy|i want to order|place order|how to order|'
    r'send your account|i.?m ready|next step|finalize|confirm)\b',
    re.IGNORECASE
)

_PURCHASED_PATTERNS = re.compile(
    r'\b(i.?ve paid|payment done|sent|transferred|bought|purchased|receipt|'
    r'i paid|done|completed|successful|confirmed|order placed)\b',
    re.IGNORECASE
)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_copilot_tables():
    """Ensure co-pilot specific tables exist. Called at module load."""
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS customer_stages (
            session_id    TEXT PRIMARY KEY,
            stage         TEXT NOT NULL DEFAULT 'new_lead',
            previous_stage TEXT,
            updated_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS health_scores (
            session_id    TEXT PRIMARY KEY,
            score         INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sales_signals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT NOT NULL,
            signal_type   TEXT NOT NULL,
            severity      TEXT NOT NULL,
            alert_message TEXT NOT NULL,
            ai_needed     INTEGER DEFAULT 0,
            action_hint   TEXT,
            actioned      INTEGER DEFAULT 0,
            detected_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_recommendations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT NOT NULL,
            signal_id     INTEGER,
            action_type   TEXT NOT NULL,
            draft_message TEXT,
            status        TEXT DEFAULT 'pending',
            created_at    TEXT NOT NULL
        );
        """)


_ensure_copilot_tables()


# ── Stage detection ────────────────────────────────────────────────────────────

def detect_stage_from_message(message: str, current_stage: str) -> str:
    """
    Given a customer message and their current stage, return the new stage.
    Stages only move forward (except inactive → can reactivate on new message).
    Zero AI cost — pure rule matching.
    """
    msg = message.strip()

    # Purchased? Lock in that stage regardless
    if _PURCHASED_PATTERNS.search(msg):
        return "purchased"

    # Purchase ready?
    if _PURCHASE_READY_PATTERNS.search(msg):
        return "purchase_ready"

    # Negotiating?
    if _NEGOTIATING_PATTERNS.search(msg):
        # Only advance if currently at interested or considering
        if current_stage in ("interested", "considering", "negotiating", "new_lead"):
            return "negotiating"

    # Considering (said "let me think" etc)
    if _CONSIDERING_PATTERNS.search(msg):
        if current_stage in ("interested", "negotiating", "new_lead"):
            return "considering"

    # General interest (questions about product, price, etc.)
    if _INTERESTED_PATTERNS.search(msg):
        if current_stage in ("new_lead", "inactive"):
            return "interested"

    # If was inactive and customer sends any message, reactivate
    if current_stage == "inactive":
        return "interested"

    # Otherwise keep current stage
    return current_stage


# ── Health Score ───────────────────────────────────────────────────────────────

def calculate_health_delta(message: str, signal_type: str = None) -> int:
    """
    Calculate the health score delta for a customer message.
    Returns a positive or negative integer. Zero AI needed.
    """
    delta = 0
    msg = message.strip()

    if _PURCHASE_READY_PATTERNS.search(msg):
        delta += 20
    elif _NEGOTIATING_PATTERNS.search(msg):
        delta += 15
    elif re.search(r'\b(deliver|delivery|shipping|dispatch)\b', msg, re.IGNORECASE):
        delta += 15
    elif re.search(r'\b(how much|price|cost)\b', msg, re.IGNORECASE):
        delta += 10
    elif re.search(r'\b(show me|tell me|what about|do you have)\b', msg, re.IGNORECASE):
        delta += 10
    elif _CONSIDERING_PATTERNS.search(msg):
        delta += 5   # still engaged, just thinking

    # Apply silence penalty from signal type
    if signal_type == "silent_3d":
        delta -= 20
    elif signal_type == "silent_24h":
        delta -= 10

    return delta


# ── DB operations ─────────────────────────────────────────────────────────────

def get_customer_stage(session_id: str) -> str:
    with _conn() as con:
        row = con.execute(
            "SELECT stage FROM customer_stages WHERE session_id=?", (session_id,)
        ).fetchone()
        return row["stage"] if row else "new_lead"


def set_customer_stage(session_id: str, new_stage: str):
    now = datetime.now(timezone.utc).isoformat()
    current = get_customer_stage(session_id)
    with _conn() as con:
        con.execute(
            """INSERT INTO customer_stages (session_id, stage, previous_stage, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 previous_stage = stage,
                 stage = excluded.stage,
                 updated_at = excluded.updated_at""",
            (session_id, new_stage, current, now)
        )


def get_health_score(session_id: str) -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT score FROM health_scores WHERE session_id=?", (session_id,)
        ).fetchone()
        return row["score"] if row else 0


def update_health_score(session_id: str, delta: int) -> int:
    """Apply delta to health score, clamped to 0–100. Returns new score."""
    current = get_health_score(session_id)
    new_score = max(0, min(100, current + delta))
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """INSERT INTO health_scores (session_id, score, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 score = excluded.score,
                 updated_at = excluded.updated_at""",
            (session_id, new_score, now)
        )
    return new_score


def log_signal(session_id: str, signal: dict) -> int:
    """Persist a detected signal to the DB. Returns the new signal ID."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        row = con.execute(
            """INSERT INTO sales_signals
               (session_id, signal_type, severity, alert_message, ai_needed, action_hint, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                signal.get("signal_type", ""),
                signal.get("severity", "low"),
                signal.get("alert_message", ""),
                1 if signal.get("ai_needed") else 0,
                signal.get("action_hint", ""),
                now,
            )
        ).fetchone()
        # SQLite lastrowid
        last_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        return last_id


def get_active_signals(session_id: str = None, limit: int = 50) -> list[dict]:
    """Get unactioned signals. Optionally filter by customer."""
    with _conn() as con:
        if session_id:
            rows = con.execute(
                """SELECT ss.*, c.name, c.phone FROM sales_signals ss
                   LEFT JOIN customers c ON ss.session_id = c.session_id
                   WHERE ss.session_id=? AND ss.actioned=0
                   ORDER BY ss.detected_at DESC LIMIT ?""",
                (session_id, limit)
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT ss.*, c.name, c.phone FROM sales_signals ss
                   LEFT JOIN customers c ON ss.session_id = c.session_id
                   WHERE ss.actioned=0
                   ORDER BY ss.detected_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def mark_signal_actioned(signal_id: int):
    with _conn() as con:
        con.execute("UPDATE sales_signals SET actioned=1 WHERE id=?", (signal_id,))


def get_stage_funnel() -> dict:
    """Returns counts per stage for the funnel visualization."""
    with _conn() as con:
        rows = con.execute(
            "SELECT stage, COUNT(*) as count FROM customer_stages GROUP BY stage"
        ).fetchall()
        counts = {r["stage"]: r["count"] for r in rows}

    result = {}
    for stage in STAGES:
        result[stage] = {
            "count": counts.get(stage, 0),
            "label": STAGE_LABELS[stage],
            "color": STAGE_COLORS[stage],
        }
    return result


# ── Main entry: process a new incoming message ─────────────────────────────────

def process_customer_message(
    session_id: str,
    customer_message: str,
    detected_signals: list = None,
) -> dict:
    """
    Called whenever a new customer message is logged.
    Updates stage and health score. Logs any signals to the DB.
    Returns a summary of changes.

    detected_signals: list of SalesSignal.to_dict() results from signals.py
    """
    current_stage = get_customer_stage(session_id)
    new_stage = detect_stage_from_message(customer_message, current_stage)

    # Calculate health delta from message content
    delta = calculate_health_delta(customer_message)
    new_score = update_health_score(session_id, delta)

    # Advance stage if changed
    if new_stage != current_stage:
        set_customer_stage(session_id, new_stage)

    # Log any signals to DB
    signal_ids = []
    if detected_signals:
        for sig in detected_signals:
            sid = log_signal(session_id, sig)
            signal_ids.append(sid)

    return {
        "session_id":    session_id,
        "previous_stage": current_stage,
        "new_stage":     new_stage,
        "stage_changed": new_stage != current_stage,
        "health_score":  new_score,
        "health_delta":  delta,
        "signal_ids":    signal_ids,
    }
