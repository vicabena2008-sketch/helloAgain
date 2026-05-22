"""
app.py — HelloAgain AI Customer Chat (Flask)
Share this URL publicly. No admin features.
Run: python app.py
"""

import os, re, uuid
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
load_dotenv()

from chat import chat as ai_chat
from conversation import ConversationState
from retrieval import retrieve_context, split_by_stock

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", uuid.uuid4().hex)

# In-memory per-session conversation store
_states: dict[str, ConversationState] = {}


@app.route("/")
def index():
    if "sid" not in session:
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
    if sid not in _states:
        _states[sid] = ConversationState()

    state      = _states[sid]
    reply_text = ai_chat(message, state)

    # Pull image if mentioned in reply
    image_url = None
    img_match = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', reply_text)
    if img_match:
        image_url  = img_match.group(2)
        reply_text = reply_text[:img_match.start()].strip()

    return jsonify({"reply": reply_text, "image_url": image_url})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    sid = session.get("sid")
    if sid and sid in _states:
        _states[sid].reset()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(port=5000, debug=False)
