"""
chat.py
Core chat() function — retrieval, LLM, conversation state, DB logging.
"""

from retrieval import retrieve_context, split_by_stock
from llm import llm, SYSTEM_PROMPT
from conversation import ConversationState, build_followup_instruction
from db.customers import upsert_customer, log_message, increment_turns, tag_customer

SAFETY_NET_QUESTIONS = {
    "tech":    " Anything else you need — accessories or delivery info?",
    "fashion": " Would you like to see matching footwear or accessories?",
    "food":    " Do you need wholesale pricing or event packaging too?",
    "home":    " Would you like details on warranty or payment options?",
    "beauty":  " Would you like a skincare or beauty bundle recommendation?",
}
DEFAULT_SAFETY_Q = " Is there anything else I can help you with today?"


def chat(user_query: str, state: ConversationState) -> str:
    if not user_query.strip():
        return "Welcome to HelloAgain AI! How can I help you today?"

    # 1. Log customer message to DB
    upsert_customer(
        state.session_id,
        topic=state.last_topic,
        budget=state.budget_mentioned,
        tag=state.current_tag(),
    )
    log_message(state.session_id, "user", user_query)

    # 2. Retrieve
    retrieved     = retrieve_context(user_query, top_k=5)
    has_context   = len(retrieved) > 0
    in_stock_docs, oos_brands = split_by_stock(retrieved) if has_context else ([], [])
    top_topic     = retrieved[0][2]["category"] if has_context else None

    # 3. Build context block
    if in_stock_docs:
        oos_docs      = [doc for _, doc, meta in retrieved if not meta["in_stock"]]
        context_block = "\n\n".join([f"- {d}" for d in in_stock_docs + oos_docs])
    elif has_context:
        context_block = "\n\n".join([f"- {doc}" for _, doc, _ in retrieved])
    else:
        context_block = "(No relevant products found in the knowledge base.)"

    # 4. Follow-up instruction
    followup_instr = build_followup_instruction(state, has_context, oos_brands, top_topic)

    # 5. Full prompt
    full_prompt = f"""{SYSTEM_PROMPT}

══ BUSINESS CONTEXT (answer ONLY from this) ══
{context_block}
══ END OF CONTEXT ══

══ FOLLOW-UP INSTRUCTION FOR THIS TURN ══
{followup_instr}
══ END INSTRUCTION ══

Previous Conversation:
{state.history_str()}

Customer: {user_query}
HelloAgain:"""

    # 6. LLM call
    response_obj = llm.invoke(full_prompt)
    reply = response_obj.content.strip()

    # 7. (Removed trimming logic, LLM handles brevity via bubbles)

    # 8. Safety net — ensure reply ends with a follow-up
    if "?" not in reply:
        reply += SAFETY_NET_QUESTIONS.get(top_topic, DEFAULT_SAFETY_Q)

    # 9. Update state + DB
    state.record_turn(user_query, reply, resolved=has_context, topic=top_topic)
    increment_turns(state.session_id, resolved=has_context)
    tag_customer(state.session_id, state.current_tag())
    log_message(state.session_id, "assistant", reply)

    # Update topic + budget in DB after state update
    upsert_customer(
        state.session_id,
        topic=state.last_topic,
        budget=state.budget_mentioned,
        tag=state.current_tag(),
        turn_count=state.turn_count,
    )

    return reply
