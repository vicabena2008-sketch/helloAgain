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

# ── Signals that suggest a HOT buyer ──────────────────────────────────────────
HOT_SIGNALS = re.compile(
    r'\b(how (do|can) i (order|buy|pay|get)|price|delivery|payment|momo|transfer|'
    r'how much|checkout|purchase|where (to|do) (i|we)|available|in stock)\b',
    re.IGNORECASE,
)
WARM_SIGNALS = re.compile(
    r'\b(looking for|need|want|recommend|suggest|show me|do you have|'
    r'budget|around|under|between|which one)\b',
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
    return "cold"


def derive_tag(turn_count: int, intent: str, resolved: bool) -> str:
    """Derive customer tag from session signals."""
    if intent == "hot" and resolved:
        return "hot"
    if intent == "warm" or (turn_count >= 2 and resolved):
        return "warm"
    if turn_count == 0:
        return "new"
    return "new"


# ── Conversation state ────────────────────────────────────────────────────────
class ConversationState:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.reset()

    def reset(self):
        self.history:          list[tuple[str, str]] = []
        self.last_resolved:    bool       = True
        self.last_topic:       str | None = None
        self.unanswered_count: int        = 0
        self.budget_mentioned: str | None = None
        self.intent:           str        = "cold"
        self.turn_count:       int        = 0
        self.is_returning:     bool       = False

    def record_turn(
        self,
        user_msg: str,
        ai_reply: str,
        resolved: bool,
        topic: str | None = None,
    ):
        self.history.append((user_msg, ai_reply))
        self.last_resolved = resolved
        self.turn_count   += 1

        if topic:
            self.last_topic = topic

        self.unanswered_count = 0 if resolved else self.unanswered_count + 1

        # Budget detection
        m = re.search(
            r'(?:GHS?|cedis?)\s*(\d[\d,]+)|(\d[\d,]+)\s*(?:GHS?|cedis)',
            user_msg, re.IGNORECASE,
        )
        if m:
            self.budget_mentioned = m.group(0).strip()

        # Intent scoring
        detected = detect_intent(user_msg)
        # Upgrade intent, never downgrade
        rank = {"cold": 0, "warm": 1, "hot": 2}
        if rank.get(detected, 0) > rank.get(self.intent, 0):
            self.intent = detected

    def history_str(self, last_n: int = 6) -> str:
        return "\n".join(
            f"Customer: {q}\nHelloAgain AI: {a}"
            for q, a in self.history[-last_n:]
        )

    def current_tag(self) -> str:
        return derive_tag(self.turn_count, self.intent, self.last_resolved)


# ── Follow-up instruction builder ────────────────────────────────────────────
def build_followup_instruction(
    state: ConversationState,
    has_context: bool,
    out_of_stock_brands: list[str],
    top_topic: str | None,
) -> str:
    lines = []

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
                "The customer is continuing the conversation. Ignore the lack of new product context. "
                "Use the Previous Conversation history to understand what they are referring to, "
                "and continue the flow naturally to close the sale. DO NOT say 'start fresh' or act confused."
            )
        elif state.unanswered_count == 0:
            lines.append(
                "No specific product match found. If they are just chatting or answering your previous question, "
                "continue naturally using the conversation history. "
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
                state.last_topic or "",
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
