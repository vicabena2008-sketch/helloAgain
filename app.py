"""
app.py — HelloAgain AI Customer Chat (Flask)
Share this URL publicly. No admin features.
Run: python app.py
"""

import os
import uuid
import json
import logging
from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

from chat import chat, chat_stream
from conversation import ConversationState
from db.customers import update_customer_info, get_whatsapp_settings
from middleware import apply_middleware
from retrieval import retrieve_context, split_by_stock, rebuild_index
import threading

load_dotenv()

app = Flask(__name__)
CORS(app)
apply_middleware(app)
app.secret_key = os.getenv("SECRET_KEY", "helloagain_super_secret")

# In-memory per-session conversation store
_states: dict[str, ConversationState] = {}

def _get_or_create_state(sid: str) -> ConversationState:
    if sid not in _states:
        _states[sid] = ConversationState()
    return _states[sid]


@app.route("/")
def index():
    # Force a new session on every page load so the backend history
    # matches the empty frontend screen.
    session["sid"] = str(uuid.uuid4())
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data    = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    sid = session.get("sid") or str(uuid.uuid4())
    session["sid"] = sid
    state = _get_or_create_state(sid)

    try:
        reply = chat(message, state)
        is_returning = state.is_returning
    except Exception:
        logging.exception("Unhandled error in /api/chat")
        reply = "Sorry — I ran into a quick issue. Please send your message again!"
        is_returning = False

    state.history.append((message, reply))

    return jsonify({
        "reply": reply,
        "is_returning": is_returning,
        "hot_lead": (state.intent == "hot")
    })

@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """SSE Streaming endpoint for chat."""
    data = request.get_json(force=True) or {}
    msg = data.get("message", "").strip()
    session_id = data.get("session_id", "").strip()

    if not msg or not session_id:
        return jsonify({"error": "Missing message or session_id"}), 400

    state = _get_or_create_state(session_id)
    is_returning = state.is_returning

    def generate():
        reply = ""
        for token in chat_stream(msg, state):
            reply += token
            # We yield it as an SSE data payload
            yield f"data: {json.dumps({'token': token})}\n\n"
        
        state.history.append((msg, reply))
        # End of stream event
        yield f"data: {json.dumps({'done': True, 'hot_lead': (state.intent == 'hot')})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@app.route("/api/suggestions", methods=["GET"])
def api_suggestions():
    """Returns dynamic quick-reply suggestions."""
    session_id = request.args.get("sid", "")
    if not session_id:
        return jsonify([])
    
    state = _get_or_create_state(session_id)
    
    if state.last_suggestions:
        return jsonify(state.last_suggestions)

    # Simple rule-based fallback
    if not state.history:
        suggs = ["Show me the latest laptops", "Do you have phones under 200k?", "How does delivery work?"]
    elif state.intent == "hot":
        suggs = ["Yes, I want to pay now", "Can I get a discount?", "Tell me about warranty"]
    elif state.active_category == "tech":
        suggs = ["Compare with another brand", "Show me accessories", "Is this good for gaming?"]
    else:
        suggs = ["Show me something else", "What's the price?", "Are there other colors?"]
        
    return jsonify(suggs)

@app.route("/api/react", methods=["POST"])
def api_react():
    """Log user reactions to messages."""
    data = request.get_json() or {}
    # Could store this in DB, but for now we just return ok
    return jsonify({"ok": True})

@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check for load balancers."""
    return jsonify({"status": "healthy", "version": "1.1.0-pro"})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    sid = session.get("sid")
    if sid and sid in _states:
        _states[sid].reset()
    return jsonify({"ok": True})


@app.route("/api/internal/reload-index", methods=["POST"])
def reload_index():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "Forbidden"}), 403
    # perform rebuild asynchronously so the endpoint returns quickly
    def _worker():
        try:
            rebuild_index()
        except Exception:
            import logging
            logging.exception("reload-index failed")

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "started": True})


if __name__ == "__main__":
    app.run(port=5000, debug=False)