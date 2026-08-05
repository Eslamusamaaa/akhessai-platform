# Deploying to Vercel

This project deploys as **two separate Vercel projects** — one for the frontend (static Vite build), one for the backend (FastAPI as a Python serverless function). They're wired together with a `rewrites` rule so the frontend's existing `/api/*` calls transparently proxy to the backend, with no CORS issues and no frontend code changes.

Run every command below yourself in your own terminal, logged into your own Vercel account (`vercel login`). Never paste API tokens into chat — Claude will not use or store them.

---

## 0. Prerequisites

- Vercel CLI installed and logged in: `vercel login`
- An [OpenRouter](https://openrouter.ai/keys) API key
- A managed Postgres database (SQLite does not work on Vercel — serverless functions have no persistent disk). Easiest options:
  - [Neon](https://neon.tech) — generous free tier, works great with Vercel, sign up and create a project to get a connection string.
  - Or Vercel's own Storage tab (Vercel Postgres, also Neon-backed) — from the [Vercel dashboard](https://vercel.com/dashboard) → **Storage** → **Create Database** → **Postgres**.

Either way, you'll end up with a connection string like:
```
postgresql://user:password@host/dbname?sslmode=require
```
Use the **pooled** connection string variant if offered — serverless functions open many short-lived connections, and a connection pooler (PgBouncer/Neon's pooler) handles that far better than a direct connection.

---

## 1. Generate secrets

```bash
python -c "import secrets; print(secrets.token_hex(32))"                                 # JWT_SECRET
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # PHI_ENCRYPTION_KEY
```

Keep these values somewhere safe — you'll paste them into Vercel's environment variable UI in the next step (not into any file in the repo).

---

## 2. Deploy the backend

```bash
cd backend
vercel
```

Follow the prompts — Vercel auto-detects the Python/FastAPI framework from `requirements.txt` and `main.py`. Accept the defaults (or link to a new project, e.g. `akhessai-backend`).

Then set the required environment variables — either via `vercel env add <NAME>` (prompts for the value, run once per variable, for both `production` and `preview`), or via **Project → Settings → Environment Variables** in the dashboard:

| Variable | Value |
|---|---|
| `DATABASE_URL` | your Postgres connection string from step 0 |
| `OPENROUTER_API_KEY` | your OpenRouter key |
| `JWT_SECRET` | generated in step 1 |
| `PHI_ENCRYPTION_KEY` | generated in step 1 |
| `VERCEL_SUPPORT_LARGE_FUNCTIONS` | `1` |

`VERCEL_SUPPORT_LARGE_FUNCTIONS=1` is required — the RAG pipeline's ML dependencies (`sentence-transformers` + `torch`) exceed Vercel's default 500 MB function bundle limit; this opts the project into Vercel's large-function allowance (up to 5 GB, Fluid Compute). Expect a slower cold start on the first request after a deploy or period of inactivity (the embedding model has to load into memory) — subsequent requests on a warm instance are fast.

Leave `QDRANT_URL` unset — the pipeline automatically falls back to in-memory cosine search over the 120-document corpus, which is what you want here (running a standalone Qdrant server isn't practical on Vercel).

Redeploy to production with the env vars applied:
```bash
vercel --prod
```

Note the production URL it prints, e.g. `https://akhessai-backend.vercel.app`.

---

## 3. Point the frontend at the backend

Edit `frontend/vercel.json` and replace the placeholder with your actual backend URL from step 2:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://akhessai-backend.vercel.app/:path*"
    }
  ]
}
```

Commit and push this change (or edit it directly before the first frontend deploy).

---

## 4. Deploy the frontend

```bash
cd frontend
vercel
```

Vercel auto-detects Vite. Accept the defaults, then deploy to production:

```bash
vercel --prod
```

No environment variables are required on the frontend project — all API calls go through the same-origin `/api/*` rewrite configured in step 3.

---

## 5. Verify

1. Open the frontend's production URL.
2. Log in with a demo account (`specialist` / `specialist123`).
3. Confirm the dashboard loads with case data — this proves the frontend → rewrite → backend → Postgres chain is wired correctly.
4. Check **Project → Logs** on the backend Vercel project if anything fails — startup errors (bad `DATABASE_URL`, missing secrets) show up there immediately.

---

## Known trade-offs of this deployment shape

- **Cold starts**: the first request to a cold backend instance loads the `sentence-transformers` embedding model into memory — this can take several seconds. Traffic keeps the instance warm between requests.
- **No persistent local file storage**: everything must go through Postgres. This is already how the app is built (`DATABASE_URL` is fully configurable) — no code changes were needed beyond pointing it at Postgres instead of SQLite.
- **Serverless Postgres connections**: use a pooled connection string (see step 0) to avoid exhausting your database's connection limit under concurrent serverless invocations.
