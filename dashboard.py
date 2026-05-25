"""
dashboard.py
Admin dashboard — customer list, tagging, conversation viewer.
Renders as a Gradio tab inside app.py.
"""

import gradio as gr
from db.customers import get_all_customers, get_conversation, tag_customer

TAG_COLORS = {
    "active":      "🔴",
    "follow_up":   "🟡",
    "recoverable": "🔵",
    "normal":      "⚫",
    "converted":   "🟢",
}


def load_customer_table():
    customers = get_all_customers()
    rows = []
    for c in customers:
        icon = TAG_COLORS.get(c.get("tag", "normal"), "⚫")
        rows.append([
            c["session_id"][:8] + "...",
            f"{icon} {c.get('tag', 'normal')}",
            c.get("topic") or "—",
            c.get("budget") or "—",
            c.get("turn_count", 0),
            c.get("last_seen", "")[:16].replace("T", " "),
        ])
    headers = ["Session", "Tag", "Topic", "Budget", "Turns", "Last Seen"]
    return rows, headers


def view_conversation(session_prefix: str):
    if not session_prefix or len(session_prefix.strip()) < 4:
        return "Enter at least 4 characters of a session ID."
    customers = get_all_customers()
    match = next(
        (c for c in customers if c["session_id"].startswith(session_prefix.strip())),
        None,
    )
    if not match:
        return "No session found with that prefix."
    msgs = get_conversation(match["session_id"])
    lines = []
    for m in msgs:
        role  = "🧑 Customer" if m["role"] == "user" else "🤖 HelloAgain AI"
        ts    = m["ts"][:16].replace("T", " ")
        lines.append(f"[{ts}] {role}:\n{m['content']}\n")
    return "\n---\n".join(lines) if lines else "No messages found."


def manual_tag(session_prefix: str, new_tag: str):
    if not session_prefix.strip():
        return "Please enter a session ID prefix."
    customers = get_all_customers()
    match = next(
        (c for c in customers if c["session_id"].startswith(session_prefix.strip())),
        None,
    )
    if not match:
        return "No session found."
    tag_customer(match["session_id"], new_tag)
    return f"✅ Tagged session {session_prefix[:8]}... as '{new_tag}'"


def build_dashboard_tab():
    with gr.Tab("📊 Admin Dashboard"):
        gr.Markdown("## HelloAgain — Customer Intelligence Dashboard")
        gr.Markdown("Track leads, view conversations, and manually tag customers.")

        with gr.Row():
            refresh_btn = gr.Button("🔄 Refresh Customer List", variant="secondary")

        table_output = gr.Dataframe(
            headers=["Session", "Tag", "Topic", "Budget", "Turns", "Last Seen"],
            label="All Customers",
            interactive=False,
            wrap=True,
        )

        gr.Markdown("### 🔍 View Conversation")
        with gr.Row():
            session_input = gr.Textbox(label="Session ID prefix (first 4+ chars)", scale=3)
            view_btn      = gr.Button("View", variant="primary", scale=1)
        convo_output = gr.Textbox(label="Conversation History", lines=15, interactive=False)

        gr.Markdown("### 🏷️ Manually Tag a Customer")
        with gr.Row():
            tag_session_input = gr.Textbox(label="Session ID prefix", scale=2)
            tag_dropdown      = gr.Dropdown(
                choices=["active", "follow_up", "recoverable", "normal", "converted"],
                label="New Tag",
                scale=2,
            )
            tag_btn = gr.Button("Apply Tag", variant="primary", scale=1)
        tag_result = gr.Textbox(label="Result", interactive=False)

        # Wire up
        def refresh():
            rows, _ = load_customer_table()
            return rows

        refresh_btn.click(refresh, outputs=table_output)
        view_btn.click(view_conversation, inputs=session_input, outputs=convo_output)
        tag_btn.click(manual_tag, inputs=[tag_session_input, tag_dropdown], outputs=tag_result)

        # Load on tab open
        table_output.value = refresh()
