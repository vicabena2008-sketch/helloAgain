"""
drafter.py — HelloAgain One-Click AI Message Drafter
Called ONLY when the seller clicks an action button.
Makes a single, focused LLM call to generate a personalized WhatsApp draft.

One AI call per seller action click.
"""

import logging
import json
import re
from typing import Optional

from utils.llm import llm
from db.customers import get_conversation, get_customer
from knowledge.retrieval import retrieve_context, split_by_stock

# ── Draft prompts per action type ─────────────────────────────────────────────

DRAFT_PROMPTS = {
    "still_interested": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a short, warm, and genuine follow-up message (2-3 sentences max) to send to a customer who showed interest but went quiet.
- Address them by name if provided
- Reference their interest naturally
- Keep it friendly and low-pressure (no begging)
- End with a single, easy question or call to action
- Write in the same language/tone as the conversation (Pidgin if they used Pidgin, formal if they were formal)
- Do NOT mention AI, system, or that this is automated
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "offer_discount": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a short, warm message (2-3 sentences max) offering a small discount to a price-sensitive customer.
- Address them by name if provided
- Mention the specific product if discussed
- Frame the discount as a special gesture for them, not desperation
- Keep urgency natural (don't be pushy)
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "negotiate_price": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a smart, friendly negotiation response (2-3 sentences max) to a customer asking for a lower price.
- Acknowledge their concern warmly
- Offer a small concession OR highlight the value they're getting
- Don't give too much away — suggest meeting halfway or a bundle deal
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "share_testimonial": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a short, authentic-sounding customer testimonial message (2-3 sentences max) to build trust with a hesitant customer.
- Reference a recent satisfied customer's experience (keep it general but believable)
- Relate it to what the current customer is considering
- End with a gentle next step
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "re_engage": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a warm, friendly re-engagement message (2-3 sentences max) for a customer who has been inactive.
- Be genuinely warm — not salesy or desperate
- Reference their last topic of interest naturally
- Offer new value or ask a simple question
- NO guilt-tripping or pressure
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "share_benefits": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a confident, compelling product benefit message (2-3 sentences max) for a customer who seems uncertain.
- Highlight 2-3 key reasons to choose the product
- Keep it specific to what they asked about
- Sound enthusiastic but genuine
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "close_sale": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a clear, helpful closing message (2-3 sentences max) for a customer who is ready to buy.
- Make it easy for them to complete the purchase
- Include a clear next step (ask for their location, mention payment options, etc.)
- Be warm and efficient — they've made their decision, help them finalize it
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "share_delivery_info": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a helpful, reassuring delivery information message (2-3 sentences max) for a customer asking about shipping.
- Be clear about delivery timelines (use realistic estimates: 1-3 days Lagos, 3-5 days other states)
- Mention any relevant delivery cost or process
- End with a question to move them toward a decision
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",

    "suggest_alternatives": """You are a helpful WhatsApp sales assistant for a Nigerian business.
Generate a helpful message (2-3 sentences max) suggesting 1 or 2 alternative products to a customer.
- Acknowledge what they are looking for
- Suggest alternatives enthusiastically but briefly
- Ask if they would like to see pictures or more details
- Write in the same language/tone as the conversation
- Return ONLY the message text. No quotes, no intro, no JSON.""",
}

DEFAULT_DRAFT_PROMPT = DRAFT_PROMPTS["still_interested"]


# ── Context builder ────────────────────────────────────────────────────────────

def _build_conversation_context(conversation_history: list[dict], max_messages: int = 10) -> str:
    """Format last N messages into a readable context string for the LLM."""
    recent = conversation_history[-max_messages:] if len(conversation_history) > max_messages else conversation_history
    lines = []
    for msg in recent:
        role = "Customer" if msg.get("role") == "user" else "Seller"
        lines.append(f"{role}: {msg.get('content', '').strip()}")
    return "\n".join(lines) if lines else "No conversation history yet."


# ── Main drafter function ──────────────────────────────────────────────────────

def draft_message(
    action_type: str,
    session_id: str,
    customer_name: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """
    Generate a personalized WhatsApp draft message for the seller to review and send.
    Makes exactly ONE AI call.

    Returns:
        {
          "ok": True,
          "draft": "Hi Amaka! I noticed you were looking at...",
          "action_type": "still_interested",
          "customer_name": "Amaka"
        }
    """
    # Fetch conversation history from DB
    history = get_conversation(session_id)
    customer = get_customer(session_id)

    # Resolve customer name
    name = customer_name or (customer.get("name") if customer else None) or "there"

    # Build context block
    conversation_text = _build_conversation_context(history)
    topic = (customer.get("topic") if customer else None) or "your inquiry"
    budget = (customer.get("budget") if customer else None) or ""

    # Fetch KB context to prevent hallucination
    query_str = topic if topic and topic != "your inquiry" else (history[-1].get("content", "") if history else "")
    retrieved = retrieve_context(query_str, top_k=3)
    in_stock_docs, _ = split_by_stock(retrieved, query_str)
    kb_context = "\n".join(in_stock_docs) if in_stock_docs else "No specific product context found."

    # Select the appropriate prompt
    base_prompt = DRAFT_PROMPTS.get(action_type, DEFAULT_DRAFT_PROMPT)

    # Build the full prompt
    full_prompt = f"""{base_prompt}

---
CUSTOMER NAME: {name}
PRODUCT / TOPIC THEY DISCUSSED: {topic}
{f"THEIR BUDGET: {budget}" if budget else ""}
{f"EXTRA CONTEXT: {extra_context}" if extra_context else ""}

AVAILABLE PRODUCTS IN STORE (DO NOT HALLUCINATE PRODUCTS NOT LISTED HERE):
{kb_context}

RECENT CONVERSATION:
{conversation_text}
---

Write the WhatsApp message now:"""

    try:
        # Single LLM call
        response = llm.invoke(full_prompt)
        raw = (response.content or "").strip()

        # The LLM might return JSON (since we configured json_object mode globally)
        # Try to extract just the text if it returns JSON
        draft_text = _extract_text_from_response(raw)

        if not draft_text:
            raise ValueError("Empty draft from LLM")

        return {
            "ok":            True,
            "draft":         draft_text,
            "action_type":   action_type,
            "customer_name": name,
        }

    except Exception as e:
        logging.exception(f"[drafter] Draft generation failed for {session_id}: {e}")
        return {
            "ok":    False,
            "error": "Could not generate draft — please write your message manually.",
            "action_type": action_type,
        }


def _extract_text_from_response(raw: str) -> str:
    """
    Extract plain text from LLM response.
    Handles both plain text and JSON wrapper (since llm uses json_object mode).
    """
    raw = raw.strip()

    # If it looks like JSON, try to parse and extract a text field
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            # Try common field names
            for key in ("message", "draft", "reply", "text", "content"):
                if key in parsed and isinstance(parsed[key], str):
                    return parsed[key].strip()
            # If no recognized key, join all string values
            parts = [str(v) for v in parsed.values() if isinstance(v, str)]
            if parts:
                return " ".join(parts).strip()
        except json.JSONDecodeError:
            pass

    # Strip markdown code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return raw.strip()


# ── Batch draft for multiple actions ──────────────────────────────────────────

def draft_all_actions(session_id: str, action_types: list[str]) -> list[dict]:
    """
    Generate drafts for multiple actions at once.
    Note: this makes one AI call PER action. Use sparingly.
    """
    results = []
    for action_type in action_types:
        result = draft_message(action_type, session_id)
        results.append(result)
    return results
