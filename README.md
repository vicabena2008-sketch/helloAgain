# HelloAgain AI

AI-powered WhatsApp-first customer follow-up and retention assistant for HelloAgain (Nigeria).
Built with Gradio + FAISS + Groq (Llama 3.3 70B) + SQLite customer tracking.

---

## What's New vs Original

| Feature | Before | Now |
|---|---|---|
| System prompt | Basic sales assistant | HelloAgain-aligned: lead scoring, re-engagement, intent detection |
| Customer tracking | None | SQLite DB — every session logged |
| Lead scoring | None | Cold / Warm / Hot auto-detection per message |
| Customer tagging | None | new / warm / hot / inactive / converted / vip |
| Admin dashboard | None | Full tab: customer list, conversation viewer, manual tagging |
| Re-engagement | None | Returning customer detection + warm opener |
| WhatsApp handoff | Link always | Triggered strategically on HOT intent |
| UI | Single chat | Two tabs: Chat + Admin Dashboard |

---

## Project Structure

```
helloagain/
├── app.py              # Entry point — Gradio UI (2 tabs)
├── chat.py             # Core chat logic + DB integration
├── retrieval.py        # FAISS index + retrieve_context()
├── knowledge_base.py   # All product/shop data (edit here to update products)
├── llm.py              # Groq LLM + HelloAgain system prompt
├── conversation.py     # ConversationState + intent detection + follow-up builder
├── image_fetcher.py    # DuckDuckGo image fetcher
├── dashboard.py        # Admin dashboard Gradio tab
├── db/
│   ├── __init__.py
│   └── customers.py    # SQLite customer store
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Local Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt

cp .env.example .env
# Open .env, paste your GROQ_API_KEY

python app.py
# Open http://localhost:7860
```

---

## Deploy on Render

1. Push this folder to GitHub
2. Render → New Web Service → connect repo
3. Environment Variables:
   - `GROQ_API_KEY` = your key
   - `DB_PATH` = `helloagain.db`
4. Build command: `pip install -r requirements.txt`
5. Start command: `python app.py`

---

## Roadmap (Phase 2)

- [ ] WhatsApp Business API — send/receive real messages
- [ ] Automated follow-up triggers — ping silent customers after 24h
- [ ] Bulk re-engagement campaigns
- [ ] Cloudinary image store (replace DuckDuckGo)
- [ ] Analytics charts in dashboard (conversion rate, revenue recovered)
