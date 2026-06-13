"""
signals.py — HelloAgain Sales Signal Detection Engine
Rule-based, zero-AI-cost signal detection.
AI is ONLY called after a signal is confirmed by these rules.

Signal types:
  - silent_2h        : Customer has not replied for 2 hours
  - silent_24h       : Customer has not replied for 24 hours
  - silent_3d        : Customer has not replied for 3 days
  - viewed_pricing   : Customer asked price, seller replied, customer went quiet
  - delivery_inquiry : Customer is asking about delivery / shipping
  - discount_request : Customer is asking for a lower price / discount
  - purchase_ready   : Customer is asking about payment / ordering
  - trust_signal     : Customer seems hesitant / needs social proof
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── Keyword sets ───────────────────────────────────────────────────────────────

PRICING_KEYWORDS = re.compile(
    r'\b(how much|price|cost|how much is|what.?s the price|what is the price|'
    r'how much does|pricing|rate|charge|fee)\b',
    re.IGNORECASE
)

DELIVERY_KEYWORDS = re.compile(
    r'\b(deliver|delivery|shipping|ship|location|where are you|'
    r'when will it arrive|how long|dispatch|send it|where.?s my|track)\b',
    re.IGNORECASE
)

DISCOUNT_KEYWORDS = re.compile(
    r'\b(discount|reduce|last price|final price|can you do better|too expensive|'
    r'expensive|cut the price|bring it down|reduce it|lower it|better price|'
    r'abeg|na wa|too much|i no get that kind money|manage|last last)\b',
    re.IGNORECASE
)

PURCHASE_READY_KEYWORDS = re.compile(
    r'\b(how (do|can) i (order|pay|buy|get)|payment|account number|transfer|'
    r'momo|bank details|pay now|i want to buy|i want to order|place order|'
    r'how to order|send your account|i.?m ready|let.?s do it|make the order|'
    r'when can i get|next step|finalize|confirm)\b',
    re.IGNORECASE
)

TRUST_HESITATION_KEYWORDS = re.compile(
    r'\b(let me think|i.?ll think|i.?ll get back|consider|maybe|not sure|'
    r'i.?ll discuss|i.?ll check|let me ask|not yet|later|i.?ll decide|'
    r'still thinking|i.?m not sure|need to think|i.?ll come back)\b',
    re.IGNORECASE
)

# ── Signal result structure ────────────────────────────────────────────────────

class SalesSignal:
    """Represents a detected sales signal."""
    def __init__(
        self,
        signal_type: str,
        severity: str,          # "low" | "medium" | "high"
        alert_message: str,
        ai_needed: bool,
        action_hint: str = "",  # suggested action type for actions.py
    ):
        self.signal_type   = signal_type
        self.severity      = severity
        self.alert_message = alert_message
        self.ai_needed     = ai_needed
        self.action_hint   = action_hint
        self.detected_at   = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "signal_type":   self.signal_type,
            "severity":      self.severity,
            "alert_message": self.alert_message,
            "ai_needed":     self.ai_needed,
            "action_hint":   self.action_hint,
            "detected_at":   self.detected_at,
        }


# ── Message-content signal detection ──────────────────────────────────────────

def detect_message_signals(
    customer_message: str,
    conversation_history: list[dict],   # [{"role": "user"|"seller", "content": "...", "ts": "..."}]
) -> list[SalesSignal]:
    """
    Analyse a single customer message against keyword rules.
    Returns a list of SalesSignal objects (can be empty).
    No AI is called here.
    """
    signals: list[SalesSignal] = []
    msg = customer_message.strip()

    # ── Purchase Ready ────────────────────────────────────────────────────────
    if PURCHASE_READY_KEYWORDS.search(msg):
        signals.append(SalesSignal(
            signal_type   = "purchase_ready",
            severity      = "high",
            alert_message = "🔥 Customer is ready to buy — asking about payment or ordering!",
            ai_needed     = True,
            action_hint   = "close_sale",
        ))
        return signals  # highest priority — stop checking

    # ── Delivery Inquiry ──────────────────────────────────────────────────────
    if DELIVERY_KEYWORDS.search(msg):
        signals.append(SalesSignal(
            signal_type   = "delivery_inquiry",
            severity      = "high",
            alert_message = "🚚 Customer is asking about delivery / shipping.",
            ai_needed     = True,
            action_hint   = "share_delivery_info",
        ))

    # ── Discount Request ──────────────────────────────────────────────────────
    if DISCOUNT_KEYWORDS.search(msg):
        signals.append(SalesSignal(
            signal_type   = "discount_request",
            severity      = "high",
            alert_message = "💰 Customer is negotiating — asking for a discount or lower price.",
            ai_needed     = True,
            action_hint   = "negotiate_price",
        ))

    # ── Pricing Inquiry ───────────────────────────────────────────────────────
    if PRICING_KEYWORDS.search(msg) and not signals:
        # Only flag pricing if no stronger signal found
        signals.append(SalesSignal(
            signal_type   = "pricing_inquiry",
            severity      = "medium",
            alert_message = "💬 Customer is asking about price — follow up if they go quiet.",
            ai_needed     = False,   # no AI yet; wait to see if they go silent
            action_hint   = "share_pricing",
        ))

    # ── Trust / Hesitation ────────────────────────────────────────────────────
    if TRUST_HESITATION_KEYWORDS.search(msg):
        # Check if they had pricing or product discussion before
        had_pricing = any(
            PRICING_KEYWORDS.search(m.get("content", ""))
            for m in conversation_history
            if m.get("role") == "user"
        )
        signals.append(SalesSignal(
            signal_type   = "trust_hesitation",
            severity      = "medium",
            alert_message = "🤔 Customer is hesitating — may need social proof or reassurance.",
            ai_needed     = had_pricing,   # only call AI if they already saw price
            action_hint   = "share_testimonial",
        ))

    # ── Viewed Pricing Then Went Quiet ────────────────────────────────────────
    # Check if seller last sent a price message and customer has now re-engaged after silence
    if not signals and _seller_last_shared_price(conversation_history):
        signals.append(SalesSignal(
            signal_type   = "viewed_pricing",
            severity      = "medium",
            alert_message = "👀 Customer viewed pricing — seller replied with price but customer was quiet.",
            ai_needed     = True,
            action_hint   = "still_interested",
        ))

    return signals


def _seller_last_shared_price(history: list[dict]) -> bool:
    """True if the last seller message contains a price, suggesting the customer saw it."""
    for msg in reversed(history):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "seller":
            # Check if seller message looks like a price reply
            return bool(re.search(r'[₦#]?\s*\d[\d,]*|\bNGN\b', content, re.IGNORECASE))
        elif role == "user":
            break  # customer spoke after seller, so not a "viewed pricing" situation
    return False


# ── Silence-based signal detection ────────────────────────────────────────────

def detect_silence_signal(last_customer_message_ts: Optional[str]) -> Optional[SalesSignal]:
    """
    Check if the customer has been silent.
    Returns a SalesSignal if a silence threshold is crossed, else None.
    No AI is called here.

    last_customer_message_ts: ISO8601 string of last customer message timestamp.
    """
    if not last_customer_message_ts:
        return None

    try:
        last_ts = datetime.fromisoformat(last_customer_message_ts.replace("Z", "+00:00"))
    except ValueError:
        return None

    now = datetime.now(timezone.utc)
    delta = now - last_ts

    if delta >= timedelta(days=3):
        return SalesSignal(
            signal_type   = "silent_3d",
            severity      = "high",
            alert_message = "⏰ Customer silent for 3 days — high risk of losing the lead.",
            ai_needed     = True,
            action_hint   = "re_engage",
        )
    elif delta >= timedelta(hours=24):
        return SalesSignal(
            signal_type   = "silent_24h",
            severity      = "medium",
            alert_message = "⏰ Customer silent for 24 hours — time to follow up.",
            ai_needed     = True,
            action_hint   = "still_interested",
        )
    elif delta >= timedelta(hours=2):
        return SalesSignal(
            signal_type   = "silent_2h",
            severity      = "low",
            alert_message = "💤 Customer silent for 2 hours — they may be losing interest.",
            ai_needed     = False,   # just alert; no AI yet for 2h silence
            action_hint   = "still_interested",
        )

    return None


# ── Batch check: scan all customers for silence ────────────────────────────────

def scan_customers_for_silence(customers: list[dict]) -> list[dict]:
    """
    Given a list of customer dicts (from get_all_customers()),
    return those with an active silence signal.
    Used by the background signal scanner.
    """
    results = []
    for c in customers:
        # last_seen is when we last heard from the customer
        signal = detect_silence_signal(c.get("last_seen"))
        if signal:
            results.append({
                "customer": c,
                "signal":   signal.to_dict(),
            })
    return results
