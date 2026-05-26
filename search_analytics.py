"""
search_analytics.py
Generates insights from search logs and product interactions.
"""

from db.customers import _conn
from datetime import datetime, timezone, timedelta

def get_top_searches(days: int = 7, limit: int = 10) -> list[dict]:
    """Returns the most frequent search queries in the last X days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT query, COUNT(*) as count, AVG(results_count) as avg_results
            FROM search_logs
            WHERE ts >= ?
            GROUP BY LOWER(TRIM(query))
            ORDER BY count DESC
            LIMIT ?
            """,
            (cutoff, limit)
        ).fetchall()
        return [{"query": r["query"], "count": r["count"], "avg_results": round(r["avg_results"], 1)} for r in rows]

def get_search_gaps(days: int = 7, limit: int = 10) -> list[dict]:
    """Returns frequent queries that yielded 0 results."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT query, COUNT(*) as count
            FROM search_logs
            WHERE ts >= ? AND results_count = 0
            GROUP BY LOWER(TRIM(query))
            ORDER BY count DESC
            LIMIT ?
            """,
            (cutoff, limit)
        ).fetchall()
        return [{"query": r["query"], "count": r["count"]} for r in rows]

def get_top_viewed_products(days: int = 7, limit: int = 10) -> list[dict]:
    """Returns products that are viewed/interacted with the most."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT product_category, product_brand, COUNT(*) as count
            FROM product_interactions
            WHERE ts >= ? AND interaction_type = 'viewed'
            GROUP BY product_category, product_brand
            ORDER BY count DESC
            LIMIT ?
            """,
            (cutoff, limit)
        ).fetchall()
        return [{"category": r["product_category"], "brand": r["product_brand"], "count": r["count"]} for r in rows]
