"""
admin.py — HelloAgain AI Admin Dashboard (Flask, Private)
Run: python admin.py
"""

import os
from functools import wraps
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
load_dotenv()

from db.customers import (
    get_all_customers, get_conversation, tag_customer,
    get_analytics, get_silent_customers, mark_followup_sent,
    update_customer_info, get_all_kb_items, add_kb_item,
    update_kb_item, delete_kb_item, get_whatsapp_settings,
    save_whatsapp_settings
)

app = Flask(__name__)
app.secret_key = os.getenv("ADMIN_SECRET_KEY", "helloagain_admin_secret")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "helloagain2024")

TAG_LABEL = {
    "new": "New", "warm": "Warm", "hot": "Hot",
    "inactive": "Inactive", "converted": "Converted", "vip": "VIP",
}


# ── Auth decorator ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_ok"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Helpers ────────────────────────────────────────────────────────────────────
def wa_link(phone: str, msg: str) -> str:
    number = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not number.startswith("234"):
        number = "234" + number.lstrip("0")
    return f"https://wa.me/{number}?text={quote(msg)}"


def followup_text(c: dict) -> str:
    name  = c.get("name") or "there"
    topic = c.get("topic") or "your inquiry"
    bstr  = f" (budget: {c['budget']})" if c.get("budget") else ""
    if c.get("tag") == "hot":
        return (f"Hi {name}! This is HelloAgain AI. You were asking about {topic}{bstr} "
                "and seemed ready to go. We still have it — shall we sort delivery today?")
    return (f"Hi {name}! It's HelloAgain AI. You were checking out {topic}{bstr} earlier. "
            "Still interested? We'd love to help.")


def fmt_customer(c: dict) -> dict:
    return {
        "session_id":    c["session_id"],
        "session_short": c["session_id"][:8],
        "tag":           c.get("tag", "new"),
        "tag_label":     TAG_LABEL.get(c.get("tag", "new"), c.get("tag", "new")),
        "name":          c.get("name") or "",
        "phone":         c.get("phone") or "",
        "topic":         c.get("topic") or "",
        "budget":        c.get("budget") or "",
        "turn_count":    c.get("turn_count", 0),
        "last_seen":     (c.get("last_seen") or "")[:16].replace("T", " "),
    }


# ── Auth routes ────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME and
                request.form.get("password") == ADMIN_PASSWORD):
            session["admin_ok"] = True
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("admin_ok", None)
    return redirect(url_for("login"))


# ── Pages ──────────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    return render_template("admin.html")


# ── API ────────────────────────────────────────────────────────────────────────
@app.route("/api/analytics")
@login_required
def api_analytics():
    return jsonify(get_analytics())


@app.route("/api/customers")
@login_required
def api_customers():
    return jsonify([fmt_customer(c) for c in get_all_customers()])


@app.route("/api/silent")
@login_required
def api_silent():
    return jsonify([fmt_customer(c) for c in get_silent_customers(24)])


@app.route("/api/customer/<session_prefix>")
@login_required
def api_customer_detail(session_prefix):
    customers = get_all_customers()
    match = next((c for c in customers if c["session_id"].startswith(session_prefix)), None)
    if not match:
        return jsonify({"error": "Not found"}), 404
    msgs = get_conversation(match["session_id"])
    phone   = match.get("phone") or ""
    fmsg    = followup_text(match)
    wa_url  = wa_link(phone, fmsg) if phone else ""
    return jsonify({
        "customer":     fmt_customer(match),
        "messages":     [{"role": m["role"], "content": m["content"],
                          "ts": m["ts"][:16].replace("T", " ")} for m in msgs],
        "followup_msg": fmsg,
        "wa_url":       wa_url,
    })


@app.route("/api/tag", methods=["POST"])
@login_required
def api_tag():
    data   = request.get_json(force=True) or {}
    prefix = data.get("session_prefix", "")
    new_tag= data.get("tag", "")
    if not prefix or not new_tag:
        return jsonify({"error": "Missing fields"}), 400
    customers = get_all_customers()
    match = next((c for c in customers if c["session_id"].startswith(prefix)), None)
    if not match:
        return jsonify({"error": "Not found"}), 404
    tag_customer(match["session_id"], new_tag)
    return jsonify({"ok": True, "message": f"Tagged as '{new_tag}'"})


@app.route("/api/save", methods=["POST"])
@login_required
def api_save():
    data   = request.get_json(force=True) or {}
    prefix = data.get("session_prefix", "")
    if not prefix:
        return jsonify({"error": "Missing session_prefix"}), 400
    customers = get_all_customers()
    match = next((c for c in customers if c["session_id"].startswith(prefix)), None)
    if not match:
        return jsonify({"error": "Not found"}), 404
    update_customer_info(
        match["session_id"],
        name  = data.get("name") or None,
        phone = data.get("phone") or None,
        notes = data.get("notes") or None,
    )
    return jsonify({"ok": True, "message": "Customer info saved."})


@app.route("/api/mark-sent", methods=["POST"])
@login_required
def api_mark_sent():
    data   = request.get_json(force=True) or {}
    prefix = data.get("session_prefix", "")
    if not prefix:
        return jsonify({"error": "Missing session_prefix"}), 400
    customers = get_all_customers()
    match = next((c for c in customers if c["session_id"].startswith(prefix)), None)
    if not match:
        return jsonify({"error": "Not found"}), 404
    mark_followup_sent(match["session_id"])
    return jsonify({"ok": True, "message": "Follow-up marked as sent."})


# ── Knowledge Base CRUD Endpoints ──────────────────────────────────────────────
@app.route("/api/kb", methods=["GET", "POST"])
@login_required
def api_kb():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        cat = (data.get("category") or "").strip().lower()
        brand = (data.get("brand") or "").strip()
        in_stock = bool(data.get("in_stock", True))
        try:
            stock_count = int(data["stock_count"]) if data.get("stock_count") not in (None, "") else None
        except Exception:
            stock_count = None
        img_url = (data.get("image_url") or "").strip() or None
        content = (data.get("content") or "").strip()

        if not cat or not brand or not content:
            return jsonify({"error": "Category, brand, and details are required."}), 400

        item_id = add_kb_item(cat, brand, in_stock, stock_count, img_url, content)
        
        # Rebuild AI semantic vector store instantly!
        import retrieval
        retrieval.rebuild_index()

        return jsonify({"ok": True, "id": item_id, "message": "Product added. AI context index rebuilt."})
    
    return jsonify(get_all_kb_items())


@app.route("/api/kb/<int:item_id>", methods=["PUT", "DELETE"])
@login_required
def api_kb_item(item_id):
    if request.method == "DELETE":
        delete_kb_item(item_id)
        
        # Rebuild AI semantic vector store instantly!
        import retrieval
        retrieval.rebuild_index()
        
        return jsonify({"ok": True, "message": "Product deleted. AI context index rebuilt."})
    
    data = request.get_json(force=True) or {}
    cat = (data.get("category") or "").strip().lower()
    brand = (data.get("brand") or "").strip()
    in_stock = bool(data.get("in_stock", True))
    try:
        stock_count = int(data["stock_count"]) if data.get("stock_count") not in (None, "") else None
    except Exception:
        stock_count = None
    img_url = (data.get("image_url") or "").strip() or None
    content = (data.get("content") or "").strip()

    if not cat or not brand or not content:
        return jsonify({"error": "Category, brand, and details are required."}), 400

    update_kb_item(item_id, cat, brand, in_stock, stock_count, img_url, content)
    
    # Rebuild AI semantic vector store instantly!
    import retrieval
    retrieval.rebuild_index()

    return jsonify({"ok": True, "message": "Product updated. AI context index rebuilt."})


# ── WhatsApp settings simulated endpoints ─────────────────────────────────────
@app.route("/api/whatsapp/simulate", methods=["POST"])
@login_required
def api_whatsapp_simulate():
    data = request.get_json(force=True) or {}
    phone = (data.get("phone") or "").strip()
    msg_text = (data.get("message") or "").strip()
    
    if not phone or not msg_text:
        return jsonify({"error": "Phone and message are required."}), 400
        
    cleaned_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    session_id = f"wa-{cleaned_phone}"
    
    from chat import chat as ai_chat
    from conversation import ConversationState
    
    state = ConversationState()
    state.session_id = session_id
    
    from db.customers import get_customer, get_conversation, update_customer_info
    existing = get_customer(session_id)
    if existing:
        state.name = existing.get("name") or ""
        state.phone = existing.get("phone") or cleaned_phone
        state.last_topic = existing.get("topic") or ""
        state.budget_mentioned = existing.get("budget") or ""
        state.turn_count = existing.get("turn_count", 0)
        history = get_conversation(session_id)
        for m in history:
            state.turns.append((m["role"], m["content"]))
            
    reply_text = ai_chat(msg_text, state)
    
    # Ensure phone number is saved explicitly
    update_customer_info(session_id, phone=phone)
    
    return jsonify({
        "ok": True,
        "session_id": session_id,
        "reply": reply_text
    })


@app.route("/api/whatsapp-settings", methods=["GET", "POST"])
@login_required
def api_whatsapp_settings():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        save_whatsapp_settings(data)
        return jsonify({"ok": True, "message": "WhatsApp credentials saved."})
    
    settings = get_whatsapp_settings()
    settings.setdefault("webhook_url", request.url_root.rstrip("/") + "api/whatsapp/webhook")
    settings.setdefault("verify_token", "helloagain_token_2026")
    settings.setdefault("phone_number_id", "")
    settings.setdefault("access_token", "")
    settings.setdefault("live_mode", "0")
    return jsonify(settings)


if __name__ == "__main__":
    app.run(port=5001, debug=False)
