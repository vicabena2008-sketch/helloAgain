"""
funnel.py
Tracks customer journey stages and funnel transitions.
"""

from db.customers import _conn
from datetime import datetime, timezone, timedelta

# Funnel stages:
# 1. browse: first interaction
# 2. engage: asked a specific question
# 3. intent: mentioned budget or asked about delivery/payment
# 4. purchase: confirmed intent or sent to WA

def get_funnel_metrics(days: int = 7) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM customers WHERE first_seen >= ?", (cutoff,)).fetchone()[0]
        engage = con.execute("SELECT COUNT(*) FROM customers WHERE first_seen >= ? AND turn_count >= 2", (cutoff,)).fetchone()[0]
        intent = con.execute("SELECT COUNT(*) FROM customers WHERE first_seen >= ? AND (budget IS NOT NULL OR tag='active')", (cutoff,)).fetchone()[0]
        purchase = con.execute("SELECT COUNT(*) FROM customers WHERE first_seen >= ? AND converted=1", (cutoff,)).fetchone()[0]
        
        return {
            "browse": total,
            "engage": engage,
            "intent": intent,
            "purchase": purchase
        }

def get_conversion_attribution(days: int = 30) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT topic, COUNT(*) as count
            FROM customers
            WHERE converted=1 AND first_seen >= ?
            GROUP BY topic
            ORDER BY count DESC
            LIMIT 5
            """,
            (cutoff,)
        ).fetchall()
        return [{"topic": r["topic"], "conversions": r["count"]} for r in rows]
