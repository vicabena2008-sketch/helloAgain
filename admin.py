"""
admin.py — HelloAgain AI Admin Dashboard (Flask, Private)
Run: python admin.py
"""

import os
import requests as http_requests
import threading
import logging
import csv
import io
import json
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from dotenv import load_dotenv
load_dotenv()

from db.customers import (
    get_all_customers, get_conversation, tag_customer,
    get_analytics, get_silent_customers, mark_followup_sent,
    update_customer_info, get_all_kb_items, add_kb_item,
    update_kb_item, delete_kb_item, get_whatsapp_settings,
    save_whatsapp_settings
)
import db.customers

app = Flask(__name__)
app.secret_key = os.getenv("ADMIN_SECRET_KEY", "helloagain_admin_secret")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "helloagain2024")

# ── Chat app URL (where the customer-facing app.py is running) ─────────────────
CHAT_APP_URL = os.getenv("CHAT_APP_URL", "http://127.0.0.1:5000")

TAG_LABEL = {
    "active": "Active", "follow_up": "Follow-Up",
    "recoverable": "Recoverable", "normal": "Normal",
}


# ── Shared helper: rebuild index in BOTH processes ─────────────────────────────
def _rebuild_everywhere():
    """Rebuild the FAISS index in this process AND ping the chat app to do the same.

    Runs the rebuild in a background thread so the admin HTTP request returns
    immediately and does not block or trigger upstream 502/timeout errors.
    """
    def _worker():
        try:
            import sys
            # Only rebuild locally if retrieval was already imported (e.g., simulator used)
            # This avoids loading the heavy ~300MB SentenceTransformer if unused
            if 'retrieval' in sys.modules:
                import retrieval
                retrieval.rebuild_index()
        except Exception:
            logging.exception("Admin: local rebuild_index() failed")

        try:
            http_requests.post(f"{CHAT_APP_URL}/api/internal/reload-index", timeout=3)
            print("[admin] Chat app index reload triggered successfully.")
        except Exception as e:
            print(f"[admin] WARNING: Could not ping chat app to reload index: {e}")
            print("[admin] The chat app will use its old index until it restarts.")

    threading.Thread(target=_worker, daemon=True).start()


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
        "session_id":       c["session_id"],
        "session_short":    c["session_id"][:8],
        "tag":              c.get("tag", "normal"),
        "tag_label":        TAG_LABEL.get(c.get("tag", "normal"), c.get("tag", "normal")),
        "name":             c.get("name") or "",
        "phone":            c.get("phone") or "",
        "topic":            c.get("topic") or "",
        "budget":           c.get("budget") or "",
        "turn_count":       c.get("turn_count", 0),
        "engagement_score": c.get("engagement_score", 0),
        "last_seen":        (c.get("last_seen") or "")[:16].replace("T", " "),
        "followup_sent":    c.get("followup_sent", 0),
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


@app.route("/api/automation/run", methods=["POST", "GET"])
def api_automation_run():
    # Simple endpoint for a cron service to ping
    # Processes silent active/follow_up customers (inactive for >24h)
    token = request.args.get("token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    expected_token = os.getenv("CRON_TOKEN", "helloagain_cron_secret")
    if token != expected_token:
        return jsonify({"error": "Unauthorized"}), 401
    
    silent_customers = get_silent_customers(24)
    if not silent_customers:
        return jsonify({"ok": True, "message": "No silent customers to process.", "processed": 0})
        
    from analytics import analyze_and_update_tag
    import time
    
    results = []
    for c in silent_customers:
        res = analyze_and_update_tag(c["session_id"])
        results.append({"session_id": c["session_id"][:8], "new_tag": res.get("tag")})
        # Sleep to respect Groq rate limits
        time.sleep(2)
        
    return jsonify({"ok": True, "processed": len(results), "results": results})


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
        _rebuild_everywhere()

        return jsonify({"ok": True, "id": item_id, "message": "Product added. AI context index rebuilt."})

    return jsonify(get_all_kb_items())


@app.route("/api/kb/<int:item_id>", methods=["PUT", "DELETE"])
@login_required
def api_kb_item(item_id):
    if request.method == "DELETE":
        delete_kb_item(item_id)
        _rebuild_everywhere()
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
    _rebuild_everywhere()

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
        user_msg = None
        for m in history:
            if m["role"] == "user":
                user_msg = m["content"]
            elif m["role"] == "assistant" and user_msg is not None:
                state.history.append((user_msg, m["content"]))
                user_msg = None

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


# ── Bulk Operations ────────────────────────────────────────────────────────────
@app.route("/api/bulk-tag", methods=["POST"])
@login_required
def api_bulk_tag():
    data = request.get_json(force=True) or {}
    session_ids = data.get("session_ids", [])
    new_tag = data.get("tag", "")
    if not session_ids or not new_tag:
        return jsonify({"error": "Missing session_ids or tag"}), 400
    for sid in session_ids:
        tag_customer(sid, new_tag)
    return jsonify({"ok": True, "message": f"Tagged {len(session_ids)} customers as '{new_tag}'"})


@app.route("/api/bulk-export", methods=["GET"])
@login_required
def api_bulk_export():
    customers = get_all_customers()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Session ID", "Name", "Phone", "Status", "Tag", "Topic", "Budget", "Turns", "Score", "Last Seen"])
    for c in customers:
        writer.writerow([
            c.get("session_id"), c.get("name"), c.get("phone"), c.get("status"), 
            c.get("tag"), c.get("topic"), c.get("budget"), c.get("turn_count"), 
            c.get("engagement_score"), c.get("last_seen")
        ])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=helloagain_customers.csv"})


# ── AI Follow-Up Generator ──────────────────────────────────────────────────────
@app.route("/api/generate-followup", methods=["POST"])
@login_required
def api_generate_followup():
    data = request.get_json(force=True) or {}
    session_prefix = data.get("session_prefix", "")
    customers = get_all_customers()
    match = next((c for c in customers if c["session_id"].startswith(session_prefix)), None)
    if not match:
        return jsonify({"error": "Not found"}), 404
        
    msgs = get_conversation(match["session_id"])
    conversation_text = "\n".join([f"{'Customer' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in msgs[-10:]])
    
    from llm import llm
    prompt = f"""
    You are an expert sales representative. Generate a personalized, friendly WhatsApp follow-up message (under 3 sentences) to re-engage this customer who has gone silent.
    Do NOT include greetings like [Customer Name], use their actual name '{match.get("name") or "there"}' if available.
    
    Recent conversation:
    {conversation_text}
    """
    
    try:
        res = llm.invoke(prompt)
        return jsonify({"ok": True, "message": (res.content or "").strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Knowledge Base Import/Export ───────────────────────────────────────────────
@app.route("/api/kb/export", methods=["GET"])
@login_required
def api_kb_export():
    items = get_all_kb_items()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Category", "Brand", "In Stock", "Stock Count", "Image URL", "Content"])
    for i in items:
        writer.writerow([
            i.get("category"), i.get("brand"), i.get("in_stock"), 
            i.get("stock_count", ""), i.get("image_url", ""), i.get("content")
        ])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=helloagain_kb.csv"})


@app.route("/api/kb/import", methods=["POST"])
@login_required
def api_kb_import():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename.endswith(".csv"):
        return jsonify({"error": "Must be a CSV file"}), 400
        
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    csv_input = csv.DictReader(stream)
    count = 0
    for row in csv_input:
        cat = row.get("Category", "").strip().lower()
        brand = row.get("Brand", "").strip()
        in_stock = str(row.get("In Stock", "1")).strip() in ("1", "true", "True", "yes")
        try:
            stock_count = int(row.get("Stock Count", ""))
        except:
            stock_count = None
        img_url = row.get("Image URL", "").strip() or None
        content = row.get("Content", "").strip()
        
        if cat and brand and content:
            add_kb_item(cat, brand, in_stock, stock_count, img_url, content)
            count += 1
            
    if count > 0:
        _rebuild_everywhere()
        
    return jsonify({"ok": True, "message": f"Imported {count} items successfully."})


# ── Tasks & Notifications ───────────────────────────────────────────────────────
@app.route("/api/tasks/schedule", methods=["POST"])
@login_required
def api_schedule_task():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")
    task_type = data.get("task_type")
    scheduled_time = data.get("scheduled_time")
    payload = data.get("payload", "")
    if not all([session_id, task_type, scheduled_time]):
        return jsonify({"error": "Missing fields"}), 400
        
    with db.customers._conn() as con:
        con.execute(
            "INSERT INTO scheduled_tasks (session_id, task_type, scheduled_time, payload) VALUES (?, ?, ?, ?)",
            (session_id, task_type, scheduled_time, json.dumps(payload))
        )
    return jsonify({"ok": True, "message": "Task scheduled"})


@app.route("/api/tasks/pending", methods=["GET"])
@login_required
def api_pending_tasks():
    with db.customers._conn() as con:
        rows = con.execute("SELECT * FROM scheduled_tasks WHERE status='pending' ORDER BY scheduled_time ASC").fetchall()
        return jsonify([dict(r) for r in rows])


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def api_delete_task(task_id):
    with db.customers._conn() as con:
        con.execute("DELETE FROM scheduled_tasks WHERE id=?", (task_id,))
    return jsonify({"ok": True})


@app.route("/api/notifications", methods=["GET"])
@login_required
def api_notifications():
    with db.customers._conn() as con:
        rows = con.execute("SELECT * FROM notifications ORDER BY ts DESC LIMIT 20").fetchall()
        return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(port=5001, debug=False)