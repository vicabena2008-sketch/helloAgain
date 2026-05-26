"""
conversation.py
ConversationState, follow-up builder, customer tagging logic.
Aligned with HelloAgain: lead scoring, re-engagement, silent customer detection.
"""

import re
import uuid
from urllib.parse import quote

WHATSAPP_NUMBER = "2348123456789"

TOPIC_FOLLOWUPS = {
    "tech":    "Ask if the customer wants warranty details, delivery timeline, or payment options.",
    "home":    "Ask if the customer wants warranty details, delivery timeline, or payment options.",
    "fashion": "Ask if they need a different size, colour, or matching accessories.",
    "food":    "Ask if they need bulk/wholesale pricing or event packaging.",
    "beauty":  "Ask if they want a product bundle or a recommendation for their skin type.",
}
DEFAULT_FOLLOWUP = (
    "Ask if there is anything else from our categories "
    "(Tech, Fashion, Food, Home, Beauty) you can help with."
)

NO_ANSWER_FALLBACK = (
    "I'm sorry, I don't have information about that in our current catalogue. "
    "Please reach out to us on WhatsApp at +234 812 345 6789 — our team will assist you right away. "
    "Is there anything else from our current stock I can help you with?"
)

# ── Intent signal patterns ────────────────────────────────────────────────────
# HOT: customer is ready to transact
HOT_SIGNALS = re.compile(
    r'\b(how (do|can) i (order|buy|pay|get)|price|delivery|payment|momo|transfer|'
    r'how much|checkout|purchase|where (to|do) (i|we)|available|in stock|'
    r'i want to buy|i want to order|place an? order|send me|ship|dispatch)\b',
    re.IGNORECASE,
)
# WARM: customer is engaged and comparing
WARM_SIGNALS = re.compile(
    r'\b(looking for|need|want|recommend|suggest|show me|do you have|'
    r'budget|around|under|between|which one|compare|versus|vs|difference|'
    r'tell me more|more info|what about|options|alternatives)\b',
    re.IGNORECASE,
)
# COLD: disengagement signals
COLD_SIGNALS = re.compile(
    r'\b(never mind|no thanks|not interested|forget it|maybe later|'
    r'just browsing|just looking|too expensive|out of my budget)\b',
    re.IGNORECASE,
)

# ── Engagement score weights (sum to 100 range) ───────────────────────────────
_SCORE_HOT_SIGNAL    = 40   # HOT keyword detected
_SCORE_WARM_SIGNAL   = 20   # WARM keyword detected
_SCORE_PER_RESOLVED  = 10   # per resolved turn (max 30)
_SCORE_COLD_PENALTY  = -25  # explicit disengagement
_SCORE_RETURNING     = 15   # returning customer

# ── Signals that the customer is referring to something already discussed ──────
REFERENCE_SIGNALS = re.compile(
    r'\b(that|it|this|the one|those|them|same one|for that|about that|'
    r'its delivery|its price|how much is it|the timeline|the payment|'
    r'get it|alternative|price|warranty|options|the|them|that one|this one|it please)\b',
    re.IGNORECASE,
)


def build_whatsapp_link(last_user_message: str, product_context: str = "") -> str:
    intro = "Hello! I was chatting with the HelloAgain AI assistant and need help with:"
    body  = f"{intro}\n\n\"{last_user_message}\""
    if product_context:
        body += f"\n\nContext: {product_context}"
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(body)}"


def detect_intent(message: str) -> str:
    """Returns 'hot', 'warm', or 'cold' based on message signals."""
    if HOT_SIGNALS.search(message):
        return "hot"
    if WARM_SIGNALS.search(message):
        return "warm"
    if COLD_SIGNALS.search(message):
        return "cold"
    return "cold"


def compute_engagement_score(
    turn_count: int, intent: str, resolved_turns: int, is_returning: bool, last_msg: str = ""
) -> int:
    """Compute a 0-100 engagement score based on session signals."""
    score = 0
    if intent == "hot":
        score += _SCORE_HOT_SIGNAL
    elif intent == "warm":
        score += _SCORE_WARM_SIGNAL
    # Reward resolved turns (knowledge-base hits), cap at 30
    score += min(resolved_turns * _SCORE_PER_RESOLVED, 30)
    if is_returning:
        score += _SCORE_RETURNING
    # Penalise explicit cold signals
    if last_msg and COLD_SIGNALS.search(last_msg):
        score += _SCORE_COLD_PENALTY
    return max(0, min(100, score))


def is_followup_on_same_product(message: str) -> bool:
    """Returns True if the customer is asking a follow-up about the same product."""
    return bool(REFERENCE_SIGNALS.search(message))


def derive_classification(turn_count: int, intent: str, resolved: bool, is_returning: bool, engagement: int) -> str:
    """
    Map session signals to the 4 HelloAgain CRM classifications:
      - active      : Engaged RIGHT NOW — hot/warm signals, recent interaction
      - follow_up   : Was warm/hot but has gone quiet — needs a nudge
      - recoverable : Went cold after real interest — can still be won back
      - normal      : Browsing / no real intent shown yet
    """
    if engagement >= 60 or intent == "hot":
        return "active"
    if intent == "warm" or (turn_count >= 2 and resolved):
        return "active"
    if is_returning and engagement >= 30:
        return "follow_up"
    if turn_count >= 3 and engagement >= 20:
        return "recoverable"
    return "normal"


# Keep legacy alias so old callers don't break during migration
def derive_tag(turn_count: int, intent: str, resolved: bool) -> str:
    """Legacy wrapper — redirects to derive_classification."""
    return derive_classification(turn_count, intent, resolved, False, 0)


# ── Conversation state ────────────────────────────────────────────────────────
class ConversationState:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.reset()

    def reset(self):
        self.history:           list[tuple[str, str]] = []
        self.last_resolved:     bool       = True
        self.last_topic:        str | None = None
        self.unanswered_count:  int        = 0
        self.budget_mentioned:  str | None = None
        self.intent:            str        = "cold"
        self.llm_intent:        str | None = None
        self.llm_engagement_score: int | None = None
        self.turn_count:        int        = 0
        self.resolved_turns:    int        = 0    # count of turns with KB hits
        self.is_returning:      bool       = False
        # ── Active product tracking (prevents topic drift) ──────────────────
        self.active_product:    str | None = None   # e.g. "Kosua Ne Mako"
        self.active_brand:      str | None = None   # e.g. "food"
        self.active_category:   str | None = None   # e.g. "food"
        self.active_product_doc: str | None = None  # full KB doc for pinning
        # ── Pro upgrades ────────────────────────────────────────────────────────
        self.sentiment_history: list[str] = []
        self.product_interactions: list[dict] = []
        self.cart: list[dict] = []
        self.last_suggestions: list[str] = []

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "history": self.history,
            "last_resolved": self.last_resolved,
            "last_topic": self.last_topic,
            "unanswered_count": self.unanswered_count,
            "budget_mentioned": self.budget_mentioned,
            "intent": self.intent,
            "llm_intent": self.llm_intent,
            "llm_engagement_score": self.llm_engagement_score,
            "turn_count": self.turn_count,
            "resolved_turns": self.resolved_turns,
            "is_returning": self.is_returning,
            "active_product": self.active_product,
            "active_brand": self.active_brand,
            "active_category": self.active_category,
            "active_product_doc": self.active_product_doc,
            "sentiment_history": self.sentiment_history,
            "product_interactions": self.product_interactions,
            "cart": self.cart,
            "last_suggestions": self.last_suggestions,
        }

    @classmethod
    def from_dict(cls, data: dict):
        state = cls()
        state.session_id = data.get("session_id", state.session_id)
        state.history = data.get("history", [])
        state.last_resolved = data.get("last_resolved", True)
        state.last_topic = data.get("last_topic")
        state.unanswered_count = data.get("unanswered_count", 0)
        state.budget_mentioned = data.get("budget_mentioned")
        state.intent = data.get("intent", "cold")
        state.llm_intent = data.get("llm_intent")
        state.llm_engagement_score = data.get("llm_engagement_score")
        state.turn_count = data.get("turn_count", 0)
        state.resolved_turns = data.get("resolved_turns", 0)
        state.is_returning = data.get("is_returning", False)
        state.active_product = data.get("active_product")
        state.active_brand = data.get("active_brand")
        state.active_category = data.get("active_category")
        state.active_product_doc = data.get("active_product_doc")
        state.sentiment_history = data.get("sentiment_history", [])
        state.product_interactions = data.get("product_interactions", [])
        state.cart = data.get("cart", [])
        state.last_suggestions = data.get("last_suggestions", [])
        return state

    def record_turn(
        self,
        user_msg: str,
        ai_reply: str,
        resolved: bool,
        topic: str | None = None,
        brand: str | None = None,
        product_doc: str | None = None,
        new_engagement_score: int | None = None,
        new_intent: str | None = None,
    ):
        self.history.append((user_msg, ai_reply))
        self.last_resolved = resolved
        self.turn_count   += 1

        # Only update the active product when a NEW product is clearly discussed
        # If the customer is asking a follow-up about the same product, keep it pinned
        if not is_followup_on_same_product(user_msg):
            if topic:
                self.last_topic = topic
            if brand:
                self.active_brand = brand
            if topic:
                self.active_category = topic
            # product_doc should contain the full KB doc or product title; store both
            if product_doc:
                # If a brand string was passed as `brand` and product_doc is the doc,
                # try to extract a product short name from the doc header
                self.active_product_doc = product_doc
                # attempt to set a short active_product name if present in doc
                first_line = product_doc.splitlines()[0] if product_doc else ""
                # fallback to brand if we can't extract a better product name
                self.active_product = first_line or brand
        # Always update topic for DB tracking even on follow-ups
        if topic and not self.last_topic:
            self.last_topic = topic

        self.unanswered_count = 0 if resolved else self.unanswered_count + 1
        if resolved:
            self.resolved_turns += 1

        # Budget detection: normalize spaces/commas inside numbers, support 'k' suffix
        # Remove spaces between digits (e.g., '150 000' -> '150000'), then normalize commas
        normalized_msg = re.sub(r'(?<=\d)\s+(?=\d)', '', user_msg)
        normalized_msg = re.sub(r'\s*,\s*', ',', normalized_msg)

        m = re.search(
            r'(?:NGN|₦|naira)?\s*(\d[\d,]*\s*k?|\d[\d,]*k?)\s*(?:NGN|₦|naira)?',
            normalized_msg, re.IGNORECASE,
        )

        if m:
            raw_val = m.group(1) or m.group(0)
            cleaned = re.sub(r'(?:NGN|₦|naira)', '', raw_val, flags=re.IGNORECASE).strip()
            # remove internal spaces and normalize commas
            cleaned = cleaned.replace(' ', '').replace(',', '')
            if cleaned.lower().endswith('k'):
                try:
                    num = float(cleaned[:-1]) * 1000
                    cleaned = f"{int(num):,}"
                except ValueError:
                    pass
            else:
                try:
                    cleaned = f"{int(cleaned):,}"
                except ValueError:
                    # leave as-is if parsing fails
                    pass
            self.budget_mentioned = f"NGN {cleaned}"

        # Intent scoring — prefer LLM if available, fallback to regex
        if new_intent:
            self.llm_intent = new_intent
            self.intent = new_intent
        else:
            detected = detect_intent(user_msg)
            rank = {"cold": 0, "warm": 1, "hot": 2}
            if rank.get(detected, 0) > rank.get(self.intent, 0):
                self.intent = detected

        if new_engagement_score is not None:
            try:
                self.llm_engagement_score = int(new_engagement_score)
            except ValueError:
                pass

    def history_str(self, last_n: int = 3) -> str:
        return "\n".join(
            f"Customer: {q}\nHelloAgain AI: {a}"
            for q, a in self.history[-last_n:]
        )

    def active_product_context(self) -> str:
        """Returns a pinned product reminder to inject into every prompt."""
        if self.active_product and self.active_product_doc:
            return (
                f"══ ACTIVE PRODUCT (customer is still discussing this) ══\n"
                f"Product: {self.active_product} | Category: {self.active_category}\n"
                f"{self.active_product_doc}\n"
                f"══ END ACTIVE PRODUCT ══"
            )
        return ""

    def engagement_score(self) -> int:
        """Live 0-100 engagement score for this session."""
        if self.llm_engagement_score is not None:
            return self.llm_engagement_score
        last_msg = self.history[-1][0] if self.history else ""
        return compute_engagement_score(
            self.turn_count, self.intent, self.resolved_turns,
            self.is_returning, last_msg
        )

    def current_tag(self) -> str:
        return derive_classification(
            self.turn_count, self.intent, self.last_resolved,
            self.is_returning, self.engagement_score()
        )


# ── Follow-up instruction builder ────────────────────────────────────────────
def build_followup_instruction(
    state: ConversationState,
    has_context: bool,
    out_of_stock_brands: list[str],
    top_topic: str | None,
) -> str:
    lines = []

    # ── Pin active product reminder ────────────────────────────────────────────
    if state.active_product and is_followup_on_same_product(
        state.history[-1][0] if state.history else ""
    ):
        lines.append(
            f"IMPORTANT: The customer is asking a follow-up about '{state.active_product}'. "
            f"Stay focused on this product. Do NOT switch to a different product or category. "
            f"Answer their follow-up question using the ACTIVE PRODUCT context above."
        )

    # Re-engagement opener for returning customers
    if state.is_returning and state.last_topic:
        lines.append(
            f"This customer is RETURNING after a period of silence. "
            f"Open warmly and reference their last interest in '{state.last_topic}'. "
            "Use the re-engagement technique from the system prompt."
        )

    if not has_context:
        if state.intent in ["hot", "warm"] and len(state.history) > 0:
            lines.append(
                "The customer is continuing the conversation about a product already discussed. "
                "Use the Previous Conversation history and ACTIVE PRODUCT context to answer. "
                "Do NOT say you don't have information — check the conversation history first. "
                "Continue the sales flow naturally to close the sale."
            )
        elif state.unanswered_count == 0:
            lines.append(
                "No specific product match found. If they are just chatting or answering your "
                "previous question, continue naturally using the conversation history. "
                "Otherwise, ask ONE focused clarifying question (budget, category, or purpose)."
            )
        elif state.unanswered_count == 1:
            lines.append(
                "Still no match. Try a different angle — ask if the customer can describe "
                "what they need differently, or suggest the closest category we carry."
            )
        else:
            wa_link = build_whatsapp_link(
                state.history[-1][0] if state.history else "a product inquiry"
            )
            lines.append(
                f"Unable to help for {state.unanswered_count} turns. "
                f"Sincerely apologise and share this WhatsApp link: {wa_link} "
                "Then ask if anything else from current stock can be helped with."
            )
    else:
        if out_of_stock_brands:
            oos = ", ".join(out_of_stock_brands)
            lines.append(
                f"'{oos}' is currently unavailable. Acknowledge it briefly once, "
                "then immediately recommend the best in-stock alternative from the context."
            )

        # Intent-based closing instruction
        if state.intent == "hot":
            wa_link = build_whatsapp_link(
                state.history[-1][0] if state.history else "an order",
                state.active_product or state.last_topic or "",
            )
            lines.append(
                f"This customer is HOT — they are ready to buy. "
                f"Make a strong closing move. Share this WhatsApp link to complete the order: {wa_link} "
                "Create gentle urgency if stock is low."
            )
        elif state.intent == "warm":
            lines.append(
                "This customer is WARM — they are interested but not yet decided. "
                "Make a confident recommendation and offer one upsell naturally."
            )
        else:
            lines.append(TOPIC_FOLLOWUPS.get(top_topic or "", DEFAULT_FOLLOWUP))

        if state.budget_mentioned:
            lines.append(
                f"Customer mentioned a budget of {state.budget_mentioned}. "
                "If not yet addressed, suggest 1–2 in-stock items within that budget."
            )

    return "\n".join(lines)