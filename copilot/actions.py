"""
actions.py — HelloAgain Action Recommendation Engine
Maps detected intent → recommended action cards shown to the seller.
Zero AI cost — pure rule mapping.

Action types:
  still_interested    → Customer disappeared after showing interest
  offer_discount      → Customer appears price-sensitive
  negotiate_price     → Customer directly requested lower pricing
  share_testimonial   → Customer needs trust / social proof
  re_engage           → Customer has been inactive for a long period
  share_benefits      → Customer is uncertain about value
  close_sale          → Customer is ready to buy — help them finalize
  share_delivery_info → Customer is asking about delivery / shipping
  suggest_alternatives→ Customer is asking for different options or products
"""

from typing import Optional

# ── Action definitions ─────────────────────────────────────────────────────────

ACTIONS = {
    "still_interested": {
        "id":          "still_interested",
        "label":       "Still Interested?",
        "description": "Customer went quiet after showing interest. Send a gentle check-in.",
        "icon":        "💬",
        "color":       "#6366f1",
        "priority":    3,
    },
    "offer_discount": {
        "id":          "offer_discount",
        "label":       "Offer a Discount",
        "description": "Customer appears price-sensitive. Offer a small incentive.",
        "icon":        "🏷️",
        "color":       "#f59e0b",
        "priority":    2,
    },
    "negotiate_price": {
        "id":          "negotiate_price",
        "label":       "Negotiate Price",
        "description": "Customer is asking for a lower price. Respond with a smart counter-offer.",
        "icon":        "🤝",
        "color":       "#f97316",
        "priority":    2,
    },
    "share_testimonial": {
        "id":          "share_testimonial",
        "label":       "Share a Testimonial",
        "description": "Customer seems hesitant. Share a recent customer success story.",
        "icon":        "⭐",
        "color":       "#eab308",
        "priority":    3,
    },
    "re_engage": {
        "id":          "re_engage",
        "label":       "Re-engage Customer",
        "description": "Customer has been inactive. Send a friendly, no-pressure message.",
        "icon":        "🔄",
        "color":       "#8b5cf6",
        "priority":    4,
    },
    "share_benefits": {
        "id":          "share_benefits",
        "label":       "Share Product Benefits",
        "description": "Customer is uncertain. Highlight key product benefits.",
        "icon":        "✨",
        "color":       "#3b82f6",
        "priority":    4,
    },
    "close_sale": {
        "id":          "close_sale",
        "label":       "Close the Sale",
        "description": "Customer is ready to buy! Send payment details and guide them to complete.",
        "icon":        "🔥",
        "color":       "#10b981",
        "priority":    1,
    },
    "share_delivery_info": {
        "id":          "share_delivery_info",
        "label":       "Share Delivery Info",
        "description": "Customer is asking about delivery. Provide shipping details and timeline.",
        "icon":        "🚚",
        "color":       "#06b6d4",
        "priority":    2,
    },
    "suggest_alternatives": {
        "id":          "suggest_alternatives",
        "label":       "Suggest Alternatives",
        "description": "Customer wants other options. Suggest 1-2 similar products.",
        "icon":        "🔍",
        "color":       "#ec4899",
        "priority":    2,
    },
}


# ── Signal → Action mapping ────────────────────────────────────────────────────

SIGNAL_TO_ACTIONS = {
    "silent_2h":         ["still_interested"],
    "silent_24h":        ["still_interested", "share_testimonial"],
    "silent_3d":         ["re_engage", "offer_discount"],
    "viewed_pricing":    ["still_interested", "offer_discount"],
    "pricing_inquiry":   ["share_benefits", "still_interested"],
    "delivery_inquiry":  ["share_delivery_info", "close_sale"],
    "discount_request":  ["negotiate_price", "offer_discount"],
    "trust_hesitation":  ["share_testimonial", "share_benefits"],
    "purchase_ready":    ["close_sale", "share_delivery_info"],
}

# Intent string → action mapping (from AI analytics output)
INTENT_TO_ACTIONS = {
    "price_hesitation":        ["still_interested", "offer_discount"],
    "price_inquiry":           ["share_benefits", "still_interested"],
    "negotiating":             ["negotiate_price", "offer_discount"],
    "delivery_concern":        ["share_delivery_info"],
    "ready_to_buy":            ["close_sale"],
    "trust_needed":            ["share_testimonial", "share_benefits"],
    "browsing":                ["share_benefits"],
    "re_engagement_needed":    ["re_engage"],
    "considering":             ["share_testimonial", "still_interested"],
    "interested":              ["share_benefits", "still_interested"],
    "seeking_alternatives":    ["suggest_alternatives", "share_benefits"],
}


def get_actions_for_signal(signal_type: str) -> list[dict]:
    """Return action card defs for a given signal type, sorted by priority."""
    action_ids = SIGNAL_TO_ACTIONS.get(signal_type, ["still_interested"])
    return _build_action_list(action_ids)


def get_actions_for_intent(intent: str) -> list[dict]:
    """Return action card defs for an AI-detected intent string."""
    # Normalise intent string to key format
    key = intent.lower().replace(" ", "_").replace("-", "_")
    action_ids = INTENT_TO_ACTIONS.get(key)
    if not action_ids:
        # Try partial match
        for known_intent, aids in INTENT_TO_ACTIONS.items():
            if known_intent in key or key in known_intent:
                action_ids = aids
                break
    if not action_ids:
        action_ids = ["still_interested"]
    return _build_action_list(action_ids)


def get_actions_for_stage(stage: str) -> list[dict]:
    """Return suggested actions based on customer stage."""
    stage_map = {
        "new_lead":       ["share_benefits"],
        "interested":     ["share_benefits", "still_interested"],
        "negotiating":    ["negotiate_price", "offer_discount"],
        "considering":    ["share_testimonial", "still_interested"],
        "purchase_ready": ["close_sale", "share_delivery_info"],
        "inactive":       ["re_engage"],
        "purchased":      [],
    }
    return _build_action_list(stage_map.get(stage, ["still_interested"]))


def get_all_actions() -> list[dict]:
    """Return all available action cards, sorted by priority."""
    return sorted(ACTIONS.values(), key=lambda a: a["priority"])


def _build_action_list(action_ids: list[str]) -> list[dict]:
    result = []
    seen = set()
    for aid in action_ids:
        if aid in ACTIONS and aid not in seen:
            result.append(ACTIONS[aid])
            seen.add(aid)
    return sorted(result, key=lambda a: a["priority"])
