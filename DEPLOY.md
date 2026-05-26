# Deployment & Redeploy Runbook — HelloAgain AI

This document lists the steps to redeploy the project on Render (or locally), post-deploy checks, and troubleshooting notes.

## Quick Summary
- Service: `helloagain-ai` (see `render.yaml`)
- Build: `pip install -r requirements.txt`
- Start: `gunicorn wsgi:application --workers 1 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT`
- Runtime: Python `3.11.9` (see `runtime.txt`)
- Persistent DB disk: mounted at `/data` (SQLite default) — defined in `render.yaml`

---

## Pre-deploy checklist (local)
1. Run tests / smoke-check locally:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python admin.py   # runs admin on :5001
   python app.py     # runs chat on :5000
   ```
2. Verify imports: `flask_cors`, `gunicorn`, `langchain-groq`, `sentence-transformers`, `faiss-cpu`, etc.
3. Ensure `requirements.txt` is up-to-date (we added `Flask-Cors`).
4. Commit and push changes to the branch connected to Render.

---

## Render-specific steps
1. Open your service in Render dashboard.
2. Ensure `render.yaml` is present and correct (autoDeploy: true means pushes will trigger builds).
3. In Service → Environment, add or update these env vars:
   - `GROQ_API_KEY` (required for LLM) — set in dashboard (sync: false in `render.yaml`)
   - `ADMIN_PASSWORD` (or change `ADMIN_USERNAME`) — set a secure value
   - `DB_PATH` (default `/data/helloagain.db`) — matches disk mount
   - `DATABASE_URL` (only if migrating to Postgres)
   - `CHAT_APP_URL` (optional; used when admin triggers remote index reload)
   - `CRON_TOKEN` (optional; used by `/api/automation/run`)
4. Trigger a deploy:
   - Push to Git (if autoDeploy true)
   - OR click "Manual Deploy" in Render.

---

## Post-deploy commands (run in Render shell or as one-off)
- If migrating from SQLite to Postgres (ensure `DATABASE_URL` is set):
  ```bash
  python migrate_db.py
  ```
- Rebuild retrieval index (ensures RAG memory matches KB):
  ```bash
  python -c "import retrieval; retrieval.rebuild_index()"
  ```
- Test the analysis endpoint (admin only):
  - Login to Admin, select a lead, click **Run AI Analysis** and **Suggest Follow-up**.

---

## Troubleshooting
- `ModuleNotFoundError: No module named 'flask_cors'` — add `Flask-Cors` to `requirements.txt` and redeploy.
- `pip` build failures for `faiss-cpu` or `torch`: consider upgrading Render plan (more RAM) or use prebuilt wheels and pin versions.
- If LLM calls fail: ensure `GROQ_API_KEY` is set and the key is valid. Check logs for rate-limit or auth errors.
- `reload-index` ping from admin expects `CHAT_APP_URL` to be reachable; if both apps run under the same service (via `wsgi.py`), local rebuild will handle it.

---

## Rollback
- Use Render dashboard to rollback to previous deploy revision if needed, or revert the commit and push.

---

## Optional: Manual health checks
- Health endpoint: `GET /api/health` should return `{"status":"healthy"}`.
- Admin: visit `/admin` and verify login and run AI Analysis.

---

If you want, I can add this file to the repo now and prepare a one-off command list to run on Render (shell commands) for you to paste into the Render console.
