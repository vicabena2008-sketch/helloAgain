"""
analytics.py
AI-powered conversation analyzer.
Reads the full chat history and uses the LLM to detect:
  - Classification: active / follow_up / recoverable / normal
  - Engagement score (0-100)
  - Buying intent summary
  - Recommended next action for the sales team
"""

import logging
import json
import time
from db.customers import get_conversation, tag_customer, get_all_customers, save_engagement_score
from utils.llm import llm

# NOTE: {conversation} is the only real placeholder here.
# The JSON example uses {{ }} to escape the braces so .format() ignores them.
ANALYSIS_PROMPT = """
You are a sales analyst for HelloAgain, a retail platform in Nigeria.
You will be given a full customer conversation. Read it carefully and return a JSON object with exactly these fields:

{{
  "tag": "<one of: active, follow_up, recoverable, normal>",
  "engagement_score": <integer 0-100>,
  "tone": "<one of: cold, warm, hot>",
  "intent_summary": "<1 sentence describing what the customer wants>",
  "next_action": "<1 sentence recommending what the sales team should do next>",
  "confidence": "<one of: low, medium, high>"
}}

CLASSIFICATION DEFINITIONS:
- active      : Currently engaged — asked about price, delivery, payment, or is actively comparing products.
                Engagement score >= 50. They are IN the funnel right now.
- follow_up   : Was interested but has gone quiet in the last 24+ hours. Needs a gentle nudge.
                Engagement score 25–49. Use the "Still Interested?" or "Offer a Discount" strategy.
- recoverable : Showed real interest earlier but conversation stalled or they said maybe later.
                Engagement score 10–24. They can be won back with re-engagement.
- normal      : Just browsing, no real intent, or conversation was too short to classify.
                Engagement score 0–9. Low priority.

ENGAGEMENT SCORE GUIDE (0-100):
- 80-100 : HOT — actively asked about payment, delivery, or how to order.
- 50-79  : WARM — asked specific questions, mentioned budget, comparing products.
- 25-49  : COOLING — was interested but conversation ended without resolution.
- 10-24  : COLD — general browsing, vague questions.
- 0-9    : NONE — no meaningful engagement.

RULES:
- Base your analysis ONLY on what is said in the conversation below
- Do NOT assume hot just because a price was asked once
- Look at the FULL arc of the conversation, not just one message
- Return ONLY valid JSON, no extra text, no markdown, no explanation

CONVERSATION:
{conversation}
"""


def analyze_conversation(session_id: str) -> dict:
    from db.customers import _conn
    msgs = get_conversation(session_id)
    if not msgs:
        return {
            "tag": "normal",
            "engagement_score": 0,
            "tone": "cold",
            "intent_summary": "No conversation yet.",
            "next_action": "Wait for customer to initiate.",
            "confidence": "low",
        }
        
    last_msg_ts = msgs[-1]["ts"]
    
    # Check cache
    with _conn() as con:
        row = con.execute("SELECT analysis_json, cached_at FROM analytics_cache WHERE session_id=?", (session_id,)).fetchone()
        if row and row["cached_at"] >= last_msg_ts:
            try:
                return json.loads(row["analysis_json"])
            except:
                pass

    lines = []
    for m in msgs:
        role = "Customer" if m["role"] == "user" else "HelloAgain"
        lines.append(f"{role}: {m['content']}")
    conversation_text = "\n".join(lines)

    if len(conversation_text) > 3000:
        conversation_text = "...[earlier messages trimmed]...\n" + conversation_text[-3000:]

    prompt = ANALYSIS_PROMPT.format(conversation=conversation_text)

    try:
        response = llm.invoke(prompt)
        raw = (response.content or "").strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)

        valid_tags  = {"active", "follow_up", "recoverable", "normal"}
        valid_tones = {"cold", "warm", "hot"}
        valid_conf  = {"low", "medium", "high"}

        result["tag"]              = result.get("tag", "normal") if result.get("tag") in valid_tags else "normal"
        result["tone"]             = result.get("tone", "cold") if result.get("tone") in valid_tones else "cold"
        result["confidence"]       = result.get("confidence", "low") if result.get("confidence") in valid_conf else "low"
        result["engagement_score"] = max(0, min(100, int(result.get("engagement_score", 0))))
        result.setdefault("intent_summary", "Unable to determine.")
        result.setdefault("next_action", "Review conversation manually.")
        
        # Save to cache
        with _conn() as con:
            now = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            con.execute("INSERT OR REPLACE INTO analytics_cache (session_id, analysis_json, cached_at) VALUES (?, ?, ?)",
                        (session_id, json.dumps(result), now))

        return result

    except Exception as e:
        logging.exception(f"[analytics] LLM analysis failed for {session_id}: {e}")
        return {
            "tag": "normal",
            "engagement_score": 0,
            "tone": "cold",
            "intent_summary": "Analysis failed - review manually.",
            "next_action": "Open the conversation and read it directly.",
            "confidence": "low",
        }


def analyze_and_update_tag(session_id: str) -> dict:
    result = analyze_conversation(session_id)
    try:
        tag_customer(session_id, result["tag"])
        save_engagement_score(session_id, result["engagement_score"])
        logging.info(
            f"[analytics] Updated {session_id[:8]} -> tag={result['tag']} score={result['engagement_score']}"
        )
    except Exception as e:
        logging.exception(f"[analytics] Failed to update tag for {session_id}: {e}")
    return result



# ── Co-Pilot: Lean Intent Analysis (called only after a signal is detected) ────

INTENT_ANALYSIS_PROMPT = """You are a sales analyst for HelloAgain, a WhatsApp-based retail business.
A sales signal was just detected in this customer conversation.
Read the last few messages and return a JSON object with EXACTLY these fields:

{{
  "intent": "<short label: e.g. price_hesitation, delivery_concern, ready_to_buy, negotiating, considering, trust_needed, seeking_alternatives, re_engagement_needed>",
  "sales_stage": "<one short phrase describing where customer is in the journey>",
  "confidence": <integer 0-100>,
  "recommended_action": "<one of: still_interested, offer_discount, negotiate_price, share_testimonial, re_engage, share_benefits, close_sale, share_delivery_info, suggest_alternatives>",
  "reasoning": "<one sentence explaining why>"
}}

RULES:
- Base analysis ONLY on the conversation below
- Return ONLY valid JSON — no extra text, no markdown
- Be precise: choose the single most relevant intent

RECENT CONVERSATION:
{conversation}
"""


def analyze_intent_for_signal(session_id: str) -> dict:
    """
    Lean AI intent analysis — called ONLY after a rule-based signal is detected.
    Makes one focused LLM call on the last 8 messages.
    Returns intent + recommended_action for the co-pilot dashboard.
    """
    msgs = get_conversation(session_id)
    if not msgs:
        return {
            "intent": "unknown",
            "sales_stage": "No conversation yet",
            "confidence": 0,
            "recommended_action": "re_engage",
            "reasoning": "No messages found.",
        }

    # Only use last 8 messages to keep token cost minimal
    recent = msgs[-8:]
    lines = []
    for m in recent:
        role = "Customer" if m["role"] == "user" else "Seller"
        lines.append(f"{role}: {m['content']}")
    conversation_text = "\n".join(lines)

    prompt = INTENT_ANALYSIS_PROMPT.format(conversation=conversation_text)

    try:
        response = llm.invoke(prompt)
        raw = (response.content or "").strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)

        # Validate fields
        valid_actions = {
            "still_interested", "offer_discount", "negotiate_price",
            "share_testimonial", "re_engage", "share_benefits",
            "close_sale", "share_delivery_info", "suggest_alternatives"
        }
        result["confidence"] = max(0, min(100, int(result.get("confidence", 50))))
        if result.get("recommended_action") not in valid_actions:
            result["recommended_action"] = "still_interested"
        result.setdefault("intent", "unknown")
        result.setdefault("sales_stage", "Unknown")
        result.setdefault("reasoning", "")

        return result

    except Exception as e:
        logging.exception(f"[analytics] Intent analysis failed for {session_id}: {e}")
        return {
            "intent": "unknown",
            "sales_stage": "Analysis failed",
            "confidence": 0,
            "recommended_action": "still_interested",
            "reasoning": "AI analysis failed — using default action.",
        }


def bulk_reanalyze_all(limit: int = 50) -> list[dict]:

    """
    Re-analyze the most recent `limit` customers and update their tags + scores.
    Sleeps 3 seconds between each call to respect Groq's 6000 TPM rate limit.
    """
    customers = get_all_customers()[:limit]
    results = []
    total = len(customers)

    for i, c in enumerate(customers, 1):
        sid = c["session_id"]
        print(f"[{i}/{total}] Analyzing {sid[:8]}...")

        result = analyze_and_update_tag(sid)
        results.append({
            "session_id":      sid[:8],
            "old_tag":         c.get("tag", "normal"),
            "new_tag":         result["tag"],
            "engagement_score": result["engagement_score"],
            "tone":            result["tone"],
            "intent_summary":  result["intent_summary"],
            "next_action":     result["next_action"],
            "confidence":      result["confidence"],
        })

        if i < total:
            time.sleep(3)

    return results