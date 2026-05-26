"""
chat.py
Core chat() function — retrieval, LLM, conversation state, DB logging.
"""

from retrieval import retrieve_context, split_by_stock
from llm import llm, llm_stream, invoke_with_retry, SYSTEM_PROMPT
from conversation import ConversationState, build_followup_instruction, is_followup_on_same_product
from db.customers import upsert_customer, log_message, increment_turns, tag_customer, save_engagement_score, log_turn_start, log_turn_end, log_search, log_interaction
import logging
import groq
import json
import re
from typing import Generator

SAFETY_NET_QUESTIONS = {
    "tech":    " Anything else you need — accessories or delivery info?",
    "fashion": " Would you like to see matching footwear or accessories?",
    "food":    " Do you need wholesale pricing or event packaging too?",
    "home":    " Would you like details on warranty or payment options?",
    "beauty":  " Would you like a skincare or beauty bundle recommendation?",
}
DEFAULT_SAFETY_Q = " Is there anything else I can help you with today?"


def _build_prompt(system: str, context: str, instruction: str, history: str, query: str) -> str:
    return (
        f"{system}\n\n"
        f"══ BUSINESS CONTEXT (answer ONLY from this) ══\n"
        f"{context}\n"
        f"══ END OF CONTEXT ══\n\n"
        f"══ FOLLOW-UP INSTRUCTION FOR THIS TURN ══\n"
        f"{instruction}\n"
        f"══ END INSTRUCTION ══\n\n"
        f"Previous Conversation:\n{history}\n\n"
        f"Customer: {query}\nHelloAgain:"
    )


def chat(user_query: str, state: ConversationState) -> str:
    if not user_query.strip():
        return "Welcome to HelloAgain AI! How can I help you today?"

    # 1. Log customer message to DB
    log_turn_start(
        state.session_id,
        user_query=user_query,
        topic=state.last_topic,
        budget=state.budget_mentioned,
        tag=state.current_tag(),
    )

    # 2. Retrieve (with query augmentation for follow-ups to prevent drift)
    search_query = user_query
    if is_followup_on_same_product(user_query) and (state.active_brand or state.last_topic):
        aug_parts = [user_query]
        if state.active_brand:
            aug_parts.append(state.active_brand)
        if state.last_topic:
            aug_parts.append(state.last_topic)
        search_query = " ".join(aug_parts)

    retrieved   = retrieve_context(search_query, top_k=5)
    has_context = len(retrieved) > 0
    in_stock_docs, oos_brands = split_by_stock(retrieved, user_query=user_query) if has_context else ([], [])
    top_topic   = retrieved[0][2]["category"] if has_context else None
    
    # Log search and interactions
    log_search(state.session_id, search_query, len(retrieved))
    if has_context:
        for _, _, meta in retrieved:
            log_interaction(state.session_id, meta.get("category", ""), meta.get("brand", ""), "viewed")
            
    # extract top retrieved item details for state pinning
    if has_context:
        top_score, top_doc, top_meta = retrieved[0]
    else:
        top_score = top_doc = top_meta = None

    # 3. Build context block
    active_ctx = state.active_product_context()
    if in_stock_docs:
        oos_docs      = [doc for _, doc, meta in retrieved if not meta["in_stock"]]
        context_block = "\n\n".join([f"- {d}" for d in in_stock_docs + oos_docs])
        if active_ctx:
            context_block = active_ctx + "\n\n" + context_block
    elif has_context:
        context_block = "\n\n".join([f"- {doc}" for _, doc, _ in retrieved])
        if active_ctx:
            context_block = active_ctx + "\n\n" + context_block
    else:
        context_block = "(No relevant products found in the knowledge base.)"

    # 4. Follow-up instruction
    followup_instr = build_followup_instruction(state, has_context, oos_brands, top_topic)

    # 5. Full prompt — keep within token budget using adaptive sliding window
    MAX_PROMPT_CHARS = 6_000
    # start with up to 6 historical turns and reduce if needed
    last_n = 6
    history_block = state.history_str(last_n=last_n)
    
    # Optional context compression if history is very long
    if len(state.history) > 6:
        try:
            # Compress older turns
            summary_prompt = "Summarise the following older conversation in 2-3 sentences. Focus on the user's intent, budget, and items discussed:\n\n" + state.history_str(last_n=len(state.history)-last_n)
            summary_response = invoke_with_retry(summary_prompt)
            compressed_history = "Older conversation summary: " + (summary_response.content or "").strip() + "\n\n"
            history_block = compressed_history + history_block
        except Exception:
            pass

    full_prompt = _build_prompt(SYSTEM_PROMPT, context_block, followup_instr, history_block, user_query)

    while len(full_prompt) > MAX_PROMPT_CHARS and last_n > 0:
        last_n -= 1
        history_block = state.history_str(last_n=last_n)
        full_prompt = _build_prompt(SYSTEM_PROMPT, context_block, followup_instr, history_block, user_query)

    # If still too long, clear history as a last resort
    if len(full_prompt) > MAX_PROMPT_CHARS:
        history_block = ""
        full_prompt = _build_prompt(SYSTEM_PROMPT, context_block, followup_instr, history_block, user_query)

    # 6. LLM call — with fallback on empty-output error
    reply = ""
    engagement_score = None
    intent = None
    try:
        response_obj = invoke_with_retry(full_prompt)
        raw = (response_obj.content or "").strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            reply = parsed.get("reply", "")
            engagement_score = parsed.get("engagement_score")
            intent = parsed.get("intent")
            state.last_suggestions = parsed.get("suggested_replies", [])
        else:
            reply = raw
        
        if not reply:
            raise ValueError("empty model output")
        if "an internal error occurred while generating a reply" in reply.lower():
            raise ValueError("empty model output (internal error string)")
    except groq.NotFoundError:
        logging.exception("LLM model not found or inaccessible")
        return (
            "Sorry — the configured language model is not available. "
            "Please check the GROQ_MODEL setting or your Groq account access."
        )
    except (ValueError, Exception) as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ["empty", "output", "tool call", "context", "token", "expecting value"]):
            logging.warning("LLM returned empty output — retrying with stripped prompt")
            slim_context = context_block[:2000] if context_block else context_block
            slim_prompt = _build_prompt(SYSTEM_PROMPT, slim_context, followup_instr, "", user_query)
            try:
                response_obj = invoke_with_retry(slim_prompt)
                raw = (response_obj.content or "").strip()
                json_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    reply = parsed.get("reply", "")
                    engagement_score = parsed.get("engagement_score")
                    intent = parsed.get("intent")
                    state.last_suggestions = parsed.get("suggested_replies", [])
                else:
                    reply = raw
            except Exception:
                pass
        if not reply:
            logging.exception("LLM invocation failed even after retry")
            return "Sorry — I'm having a quick technical hiccup. Please try your message again!"

    # 7. Single reply — strip any --- separators the model may still output
    reply = reply.replace("---", " ").strip()

    # Trim to 4 sentences max
    sentences = [s.strip() for s in reply.split(". ") if s.strip()]
    if len(sentences) > 4:
        reply = ". ".join(sentences[:4]) + "."

    # 8. Safety net — ensure reply ends with a follow-up question
    if "?" not in reply:
        reply += SAFETY_NET_QUESTIONS.get(top_topic, DEFAULT_SAFETY_Q)

    # 9. Update state + DB — include top retrieved brand and product doc so pinning works
    state.record_turn(
        user_query, reply, resolved=has_context, topic=top_topic,
        brand=(top_meta.get("brand") if top_meta else None),
        product_doc=(top_doc if top_doc else None),
        new_engagement_score=engagement_score, new_intent=intent
    )
    log_turn_end(
        session_id=state.session_id,
        reply=reply,
        resolved=has_context,
        tag=state.current_tag(),
        engagement_score=state.engagement_score(),
        topic=state.last_topic,
        budget=state.budget_mentioned,
        turn_count=state.turn_count
    )

    return reply


def chat_stream(user_query: str, state: ConversationState) -> Generator[str, None, None]:
    """Streaming equivalent of chat(). Yields text tokens as they arrive."""
    # (Simplified for now: yields the final reply, but a real SSE would iterate over llm_stream.stream)
    # We use invoke_with_retry here to ensure robustness, then we will yield it.
    reply = chat(user_query, state)
    
    # We yield character by character to simulate streaming if the backend doesn't support raw SSE json stream
    # A true implementation would yield chunks from llm_stream.stream(full_prompt), but we need JSON parsing.
    yield reply