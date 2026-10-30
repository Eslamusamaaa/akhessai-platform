# Akhessai — AI-Assisted Special Education Assessment Platform

**Akhessai** is a multi-role clinical assessment platform for special-education case management. It combines a deterministic rule-based scoring engine, a Retrieval-Augmented Generation (RAG) pipeline over Arabic clinical guidelines, and an LLM report generator to help licensed specialists produce evidence-grounded assessment reports for children with developmental, behavioral, and learning needs.

The application UI and clinical content are in Modern Standard Arabic (RTL) — the platform is built for Arabic-speaking parents, teachers, and clinicians. This document covers the technical architecture in English.

> **Status:** Proof of Concept. Not certified for HIPAA/GDPR or clinical deployment. See [Disclaimers](#disclaimers).

## Live deployment

| | |
|---|---|
| **Platform (frontend)** | [frontend-rust-rho-unmixly180.vercel.app](https://frontend-rust-rho-unmixly180.vercel.app) |
| **API (backend)** | [backend-nine-bice-71.vercel.app](https://backend-nine-bice-71.vercel.app) — interactive docs disabled in production (`docs_url=None` unless `APP_ENV=development`, see [`main.py`](backend/main.py)) |
| **Database** | Neon (managed Postgres), connected via pooled `DATABASE_URL` |
| **Hosting** | Vercel — frontend and backend are two independent projects, wired together by a same-origin `/api/*` rewrite (see [`frontend/vercel.json`](frontend/vercel.json) and [DEPLOYMENT.md](DEPLOYMENT.md)) |

**Getting access** — there are no public demo passwords in this repo on purpose (a README is public; a login system that ships its own passwords isn't one). Two ways in:
- **Parent / Teacher** — self-register from the login screen (`POST /auth/register`, see [API surface](#api-surface)). These two roles are open by design: a parent needs no prior invitation to register their own child.
- **Specialist / Admin** — not self-serve, on purpose (these roles see every case and can approve clinical reports). An existing admin creates the account directly against the database with [`backend/scripts/create_user.py`](backend/scripts/create_user.py) — an interactive script that prompts for the connection string and a password with `getpass` (nothing is echoed, logged, or written to disk).

---

## Table of Contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [How a report gets built — end to end](#how-a-report-gets-built--end-to-end)
4. [The rule-based evaluator](#the-rule-based-evaluator)
5. [The RAG pipeline](#the-rag-pipeline)
6. [LLM report generation](#llm-report-generation)
7. [Roles & access control](#roles--access-control)
8. [Security & privacy](#security--privacy)
9. [Tech stack](#tech-stack)
10. [Project structure](#project-structure)
11. [Frontend architecture — how the React app is built](#frontend-architecture--how-the-react-app-is-built)
12. [Backend integration guide](#backend-integration-guide)
13. [Setup & running locally](#setup--running-locally)
14. [API surface](#api-surface)
15. [Disclaimers](#disclaimers)

---

## What it does

A child goes through a multi-informant screening (parent, teacher, and licensed specialist each answer questions across 17 developmental domains). The platform:

1. Scores every domain with a transparent, auditable rule engine — no black-box scoring.
2. Flags which of 6 clinical specialties are relevant, and how urgently (priority tiering).
3. Retrieves the most relevant clinical guideline documents from a 120-document Arabic knowledge base via semantic vector search.
4. Feeds the scores, flags, and retrieved guidelines to an LLM, which drafts a structured clinical report (summary, differential considerations, SMART goals, intervention plan, school accommodations, home program, referrals, follow-up goals, caveats).
5. Routes the draft to a licensed specialist for review, editing, and approval before it becomes an official record.

The AI never outputs a standalone diagnosis — every generated report is explicitly framed as "indicators requiring specialist review," and every report requires human sign-off before approval.

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Frontend    │────▶│  FastAPI Backend  │────▶│  Rule Evaluator  │────▶│  RAG Search   │
│  React + TS  │     │  JWT + RBAC       │     │  (deterministic) │     │  (Qdrant /    │
│  Tailwind    │◀────│                   │◀────│                  │◀────│   in-memory)  │
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────┬───────┘
                                                                              │
                                                                              ▼
                                                                    ┌──────────────────┐
                                                                    │  LLM (Gemini 2.5  │
                                                                    │  Flash via         │
                                                                    │  OpenRouter)        │
                                                                    └──────────────────┘
```

- **Frontend** — React 18 + TypeScript + Vite + Tailwind CSS, RTL-first layout, 4 role-scoped dashboards (parent, teacher, specialist, admin).
- **Backend** — FastAPI (Python), stateless JWT auth, SQLAlchemy ORM (SQLite for local dev, PostgreSQL in Docker Compose).
- **Rule Evaluator** — pure Python + a YAML rules config. No ML involved; every threshold and weight is inspectable and testable.
- **RAG Pipeline** — `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim) embeddings over a curated 120-document Arabic clinical corpus, served through Qdrant with an in-memory cosine-similarity fallback when Qdrant isn't running.
- **LLM Layer** — Google Gemini 2.5 Flash, called through OpenRouter, constrained to a strict JSON schema validated with Pydantic before it ever reaches the client.

---

## How a report gets built — end to end

1. **Data collection.** Parent, teacher, and specialist each answer questions from a bank tagged by domain (`domain_tags`) and weighted by clinical relevance (`weight`). Answers are 0–4 Likert-style responses converted to a 0–100 points scale.
2. **Domain scoring.** The evaluator computes a weighted average per domain, per informant, and combined across informants.
3. **Specialty triggering.** Each of the 6 specialties has a domain group and two thresholds (an average threshold across its domains, and a higher single-domain threshold). A specialty activates if either condition is met — plus any age-band gating (e.g. `learning_disabilities` requires school age).
4. **Severity & priority.** Every domain gets a 1–5 severity level from its score. The highest severities across domains roll up into a `Priority 1 / 2 / 3` triage tier, with an explicit Arabic rationale string.
5. **Cross-informant discrepancy detection.** If parent and teacher scores for the same domain diverge by more than a configured delta, it's flagged — this is a real clinical signal (context-dependent symptom presentation).
6. **RAG query construction.** The top-scoring domains and active specialties are turned into a natural-language query, filtered by specialty tag and age band, and embedded.
7. **Vector search.** The query embedding is compared via cosine similarity against the pre-computed embeddings of the filtered document subset; the top 6 documents are selected.
8. **Prompt assembly.** A system prompt (fixed rules: no independent diagnosis, no fabricated numbers, must flag insufficient data) plus a structured user prompt (case data, domain scores, strengths, differential-diagnosis hints, redacted specialist notes, the 6 retrieved documents) is sent to the LLM.
9. **Structured generation.** The LLM returns strict JSON (`response_format: json_object`, `temperature: 0.15`), validated against a 10-field Pydantic schema. A safe fallback response is returned if the call fails or validation fails.
10. **Human review.** The specialist edits the draft in the UI and explicitly approves it — only then is it persisted as an official report and logged to the audit trail.

---

## The rule-based evaluator

`backend/rules/evaluator.py` + `backend/rules/rules_config.yaml`

This is intentionally **not** ML — every decision is a readable threshold in YAML, so a clinician can audit exactly why a specialty triggered or a case was marked urgent.

**17 domains**, grouped into **6 specialties**:

| Specialty | Domains | Avg. threshold | Single-domain threshold | Age gate |
|---|---|---|---|---|
| `autism` | social_communication, restricted_repetitive, pragmatic_language | ≥ 55 | ≥ 70 | — |
| `adhd` | attention, hyperactivity, impulsivity, executive_function | ≥ 60 | ≥ 75 | ≥ 48 months |
| `speech_language` | expressive_language, receptive_language, articulation, pragmatic_language | ≥ 50 | ≥ 65 | — |
| `learning_disabilities` | academic_skills, executive_function | ≥ 60 | ≥ 75 | 6–18 only |
| `sensory_processing` | sensory_reactivity, vestibular, proprioceptive | ≥ 55 | ≥ 70 | — |
| `behavior_emotional` | emotional_regulation, externalizing, internalizing | ≥ 55 | ≥ 70 | — |

- `pragmatic_language` is shared between `autism` and `speech_language`; `executive_function` is shared between `adhd` and `learning_disabilities` — a high score there can co-trigger both, which is exactly what feeds the differential-diagnosis hinting in the LLM prompt.
- **Severity bands:** Level 1 (0–19.99, minimal) through Level 5 (80–100, severe).
- **Priority matrix:** Priority 1 (any Level-5 domain, ≥2 Level-4 domains, or a specialist safety flag), Priority 2 (one Level-4, ≥2 Level-3, or a cross-informant discrepancy), else Priority 3.
- **Strengths profile:** any domain scoring ≤ 25 is surfaced as a clinical strength, not just a challenge — the report prompt explicitly requires the LLM to acknowledge it.

---

## The RAG pipeline

`backend/rag/pipeline.py`

**Corpus:** 120 Arabic clinical documents, translated and adapted from ASHA, CDC, CHADD, NIH, AOTA, and IDA guidelines. Distribution: autism (30), speech_language (21), adhd (18), learning_disabilities (18), behavior_emotional (18), sensory_processing (15).

Each document is a flat record:

```python
{
    "id": 1,
    "title": "...",
    "specialty_tag": "autism",              # one of the 6 specialties
    "domain_tag": "social_communication",   # one of the 17 domains
    "age_band": "0-6",                      # "0-6" | "6-18" | "any"
    "category": "guideline",                # guideline | research | intervention | assessment
    "content": "...",                       # 100–300 words, Arabic
}
```

**Retrieval flow:**

1. **Filter** the 120 documents down to those matching the active specialty tag(s) and age band (`age_band == "any"` always passes).
2. **Embed** the query and every candidate document with `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, multilingual, Arabic-capable), L2-normalized.
3. **Score** each candidate via cosine similarity (a dot product, since vectors are pre-normalized).
4. **Rank and select** the top 6 documents.

**Storage:** Qdrant is the primary vector store (`clinical_guidelines_v4` collection); if Qdrant isn't reachable, the pipeline falls back to an in-memory brute-force cosine search over the same embeddings — functionally identical for a 120-document corpus, just not horizontally scalable.

---

## LLM report generation

`backend/llm/client.py`

- **Model:** `google/gemini-2.5-flash`, called via the OpenRouter API.
- **PHI redaction:** before any specialist note reaches the LLM, `redact_phi()` strips phone numbers, email addresses, calendar dates, and a curated list of common Arabic first names, replacing them with placeholders.
- **Prompt structure:** a fixed system prompt (identity, 5 hard rules, a "think before you write" method, and the exact JSON schema) plus a dynamically assembled user prompt: anonymized case header → domain scores with severity labels → strengths → differential-diagnosis hints (only injected when specialties overlap, e.g. autism + ADHD) → redacted specialist notes → the 6 retrieved RAG documents.
- **Output contract:** a 10-field JSON object (`summary`, `differential_considerations`, `suggested_goals`, `intervention_plan`, `school_accommodations`, `home_program`, `suggested_referrals`, `strengths_summary`, `followup_goals`, `caveats`), validated with a Pydantic model before it's ever returned to the frontend.
- **Failure handling:** `temperature=0.15` for clinical consistency; any request failure, timeout, or schema-validation failure returns a safe, clearly-labeled fallback draft instead of a partial or malformed report.

---

## Roles & access control

| Role | What they see |
|---|---|
| **Parent** | Their registered children, assessment progress, and approved reports. |
| **Teacher** | All active cases, can contribute the school-based informant assessment. |
| **Specialist** | Full case list, clinical observation entry, AI draft generation, report editing and approval. |
| **Admin** | Everything a specialist sees, plus a full security audit trail (logins, session starts, LLM generations, approvals — with no raw PHI in the log payload). |

Authentication is JWT-based (30-minute access tokens, 7-day refresh tokens), stored client-side in `sessionStorage`. Server-side RBAC decorators lock sensitive endpoints (AI generation, clinical observations, report approval) to `specialist` / `admin` scopes.

---

## Security & privacy

- **Encryption at rest:** direct child identifiers and specialist clinical notes are encrypted column-by-column with Fernet symmetric encryption before being written to the database.
- **Password hashing:** Argon2id via `passlib`.
- **PHI minimization:** the redaction layer described above runs on every payload sent to the external LLM provider.
- **Audit trail:** a dedicated `audit_logs` table records logins, session starts, LLM draft generations (including which document IDs were retrieved), and report approvals — without embedding raw patient data in the log itself.
- **Secrets:** all credentials (OpenRouter API key, JWT signing secret, Fernet key, database password) are loaded from environment variables — see [`.env.example`](.env.example) and [`backend/.env.example`](backend/.env.example). None are hardcoded in source.

Full breakdown of what's implemented vs. deferred for production: [SECURITY.md](SECURITY.md).

---

## Tech stack

**Backend**
- FastAPI, SQLAlchemy, Pydantic
- PyJWT + Argon2 (`passlib`) for auth
- `cryptography` (Fernet) for PHI encryption
- `sentence-transformers` + `qdrant-client` for the RAG pipeline
- `pyyaml` for the rules engine config
- `pytest` for the evaluator test suite

**Frontend**
- React 18 + TypeScript + Vite
- Tailwind CSS (RTL-first)
- `lucide-react` icons

**Infra**
- Docker Compose (PostgreSQL, Qdrant, backend, frontend)
- SQLite for local (non-Docker) backend development

---

## Project structure

```
akhessai-platform/
├── backend/
│   ├── main.py              # FastAPI app, routes, auth
│   ├── config.py            # env-driven settings, secret loading
│   ├── models.py            # SQLAlchemy models (encrypted PHI columns)
│   ├── security.py          # password hashing, JWT, Fernet helpers
│   ├── seed.py               # demo data + credential seeding
│   ├── llm/
│   │   └── client.py         # prompt assembly + OpenRouter call
│   ├── rag/
│   │   └── pipeline.py       # 120-doc corpus, embeddings, vector search
│   ├── rules/
│   │   ├── evaluator.py      # scoring, triggering, severity, priority
│   │   ├── rules_config.yaml # all thresholds — no logic in YAML, only config
│   │   └── test_evaluator.py
│   └── questions/            # question bank + domain-tag resolver
├── frontend/
│   └── src/
│       ├── App.tsx           # role selection + shell
│       ├── pages/            # Dashboard, AssessmentFlow, ClinicianPortal
│       ├── components/       # QuestionRenderer, ErrorBoundary
│       └── locales/ar.json   # UI copy
├── docs/
│   └── clinical-assessment-framework.md
├── docker-compose.yml
├── .env.example
└── backend/.env.example
```

---

## Frontend architecture — how the React app is built

React 18 + TypeScript + Vite, no router, no state-management library. The whole app is one state machine held in a single root component, which is a deliberate choice for a POC this size — there's exactly one thing on screen at a time (login, or one of three pages), so a router/Redux layer would add indirection without adding capability.

### Entry point and shell

- [`frontend/src/main.tsx`](frontend/src/main.tsx) — mounts `<App />` into the DOM. Nothing else lives here; no providers, no router, no store.
- [`frontend/src/App.tsx`](frontend/src/App.tsx) — the whole shell:
  - `token` / `role` / `userEmail` state, hydrated once from `sessionStorage` on first render (`useState(() => sessionStorage.getItem("token"))`) so a page refresh doesn't log you out.
  - `if (!token)` gates **everything**: no router guard, no protected-route wrapper — the entire authenticated app literally does not render until `handleLogin` succeeds and sets `token`. See [Roles & access control](#roles--access-control) for why this matters.
  - `page` state (`"dashboard" | "assessment_flow" | "clinician_portal"`) is the de-facto router — `setPage(...)` is the only navigation primitive in the app. No URL ever changes; refreshing always lands back on the dashboard (by design — session state is server-side, not URL-encoded).
  - `handleLogin` calls `POST /auth/login` through [`apiFetch`](frontend/src/apiFetch.ts), stores the returned JWT pair in `sessionStorage` (not `localStorage` — cleared when the tab closes, smaller XSS persistence window).
  - `VITE_DEMO_MODE=true` renders 4 role buttons that just prefill the username field — it does **not** bypass the password check; see [`App.tsx:159`](frontend/src/App.tsx#L159).

### Pages (one per role-flow, not per URL)

| File | Used by | Responsibility |
|---|---|---|
| [`pages/Dashboard.tsx`](frontend/src/pages/Dashboard.tsx) | parent, teacher, admin | Case list + stats. For a parent: register a child (`POST /children`), see their sessions. Launches `assessment_flow` for a given `sessionId`. |
| [`pages/AssessmentFlow.tsx`](frontend/src/pages/AssessmentFlow.tsx) | parent, teacher | Pulls one question at a time from `GET /sessions/{id}/next-question`, renders it via `QuestionRenderer`, posts the answer to `POST /sessions/{id}/respond`, repeats until the backend reports `finished: true`. The adaptive sequencing logic lives entirely server-side ([`questions/resolver.py`](backend/questions/resolver.py)) — this component has no branching logic of its own, it just loops. |
| [`pages/ClinicianPortal.tsx`](frontend/src/pages/ClinicianPortal.tsx) | specialist, admin | The biggest page (735 lines): clinical observation form (10 rating-scale fields → `POST /sessions/{id}/observation`), triggers `POST /sessions/{id}/generate-report`, renders the AI draft with every field editable, and submits the specialist's final version to `POST /sessions/{id}/report/approve`. |

### Shared components

- [`components/QuestionRenderer.tsx`](frontend/src/components/QuestionRenderer.tsx) — renders a single question. Branches on the backend-provided `question.type` (`single_select` / `multi_select` / `likert`) and renders the matching control; has no knowledge of clinical content, domain tags, or scoring — purely a dumb renderer driven by the question-bank JSON shape the API returns.
- [`components/ErrorBoundary.tsx`](frontend/src/components/ErrorBoundary.tsx) — wraps each page (see `<ErrorBoundary>` in `App.tsx`) so a render-time exception in one page shows a fallback instead of blanking the whole app.
- [`apiFetch.ts`](frontend/src/apiFetch.ts) — a 15-line `fetch` wrapper. All API calls prefix with `/api` (not a full URL) — in production this is same-origin, resolved by the Vercel rewrite in [`frontend/vercel.json`](frontend/vercel.json); in local dev, Vite's dev-server proxy (or docker-compose networking) does the same job. **This is why the frontend never needs `VITE_API_URL` or CORS configuration in production** — it never makes a cross-origin request.
- [`locales/ar.json`](frontend/src/locales/ar.json) — UI copy. The app is Arabic-only / RTL-only by design (no i18n framework, no language switcher) — `dir="rtl"` is set globally, and every component is written RTL-first (`text-right`, flipped flex directions) rather than LTR-with-an-RTL-override.

### Styling & build tooling

- **Tailwind CSS** ([`tailwind.config.js`](frontend/tailwind.config.js)) — utility-first, no CSS modules, no styled-components. The `brand` color scale used throughout (`bg-brand-500`, `border-brand-200`, etc.) is a custom palette defined in the Tailwind config, not Tailwind's defaults.
- **Vite** ([`vite.config.ts`](frontend/vite.config.ts)) — dev server + production bundler. No SSR, no meta-framework (Next.js/Remix) — it's a plain client-rendered SPA, which matches the single-root-component architecture above.
- **TypeScript** ([`tsconfig.json`](frontend/tsconfig.json)) — strict mode on. Component props are typed inline (no shared `types.ts` — the prop surface between pages is intentionally small: `token`, `role`, `sessionId`, and a couple of callbacks).
- **Icons** — [`lucide-react`](https://lucide.dev/), tree-shaken per-icon imports (`import { LogOut, User } from "lucide-react"`).

---

## Backend integration guide

For a team integrating another service against this backend (a mobile app, an internal ops tool, a different frontend) — everything you need, with no secrets.

### Base URL and transport

- Production API: `https://backend-nine-bice-71.vercel.app` (no trailing slash on paths).
- Everything is JSON in, JSON out. No form-encoded endpoints, no file uploads in the current API surface.
- The backend sets `Cache-Control: no-store` and strict security headers on every response ([`main.py`](backend/main.py), the `security_headers` middleware) — don't rely on HTTP caching for any endpoint.
- CORS (`ALLOWED_ORIGINS`) only needs to include your origin if you're calling the API **directly from a browser**. Server-to-server integrations (no browser involved) aren't subject to CORS at all.

### Authentication flow

JWT, two-token pattern:

```
POST /auth/login
{ "username": "...", "password": "..." }

→ 200 { "access_token": "...", "refresh_token": "...", "token_type": "bearer", "role": "parent", "username": "..." }
```

- **Access token** — 30 minutes, put it on every subsequent request: `Authorization: Bearer <access_token>`.
- **Refresh token** — 7 days, exchange it for a new access token via `POST /auth/refresh` (`{ "refresh_token": "..." }`) once the access token expires. There is no token-revocation endpoint in this version — treat both tokens as sensitive for their full lifetime.
- **Registration** — `POST /auth/register` with `{ "username", "password", "role" }` is **only** open for `role: "parent"` or `role: "teacher"` (enforced server-side, see [`main.py`](backend/main.py) — `SELF_REGISTER_ROLES`). Requesting `specialist` or `admin` through this endpoint returns `403`.
- **Brute-force protection** — 5 failed login attempts per username locks that username out for 15 minutes, in-memory per server instance (`_FAILED_LOGINS` in `main.py`). A 429 is returned while locked.

### Roles and what they can call

Every endpoint except `/auth/login`, `/auth/register`, `/auth/refresh` requires a valid bearer token. Beyond that, role gates apply per-endpoint (see the full table in [API surface](#api-surface)):

| Role | Can call |
|---|---|
| `parent` | `POST /children`, `GET /children`, `GET /sessions`, answer questions while `current_informant == "parent"` |
| `teacher` | Answer questions while `current_informant == "teacher"` |
| `specialist` / `admin` | Clinical observation, report generation/approval, audit log (admin only on the audit log) |

A session has exactly one `current_informant` at a time (`parent` → `teacher` → `specialist`, enforced server-side — see `ROLE_INFORMANT_MAP` in [`main.py`](backend/main.py)). Posting an answer out of turn returns `403` with the expected informant named in the error.

### Session state machine

```
core_screener  →  specialized_screening  →  clinical_observation  →  (report generated)  →  (report approved)
   (parent)            (teacher)               (specialist)
```

Poll `GET /sessions/{id}` for `status` and `current_informant` to know what's next; `GET /sessions/{id}/next-question` returns `{"finished": true}` once a given informant has no more questions, which is the frontend's (and your integration's) signal to move to the next stage.

### Typical integration calls

```bash
# 1. Authenticate
curl -X POST https://backend-nine-bice-71.vercel.app/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_username","password":"your_password"}'

# 2. Everything else: same pattern, with the bearer token
curl https://backend-nine-bice-71.vercel.app/sessions \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 3. Adaptive question loop (see pages/AssessmentFlow.tsx for the reference client implementation)
curl https://backend-nine-bice-71.vercel.app/sessions/$SESSION_ID/next-question \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl -X POST https://backend-nine-bice-71.vercel.app/sessions/$SESSION_ID/respond \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"question_id":"...","selected_options":["..."]}'
```

### Error conventions

- `401` — missing/invalid/expired token.
- `403` — authenticated, but wrong role or wrong turn in the informant sequence.
- `404` — session/child/question not found, or not visible to your role.
- `422` — request body failed Pydantic validation (standard FastAPI shape: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`).
- `429` — login brute-force lockout.
- Error messages for user-facing auth/validation failures are in Arabic (the product is Arabic-only) — don't pattern-match on message text, use the status code.

### What you will never get back

No raw PHI leaves the encryption boundary unexpectedly: child names/contact fields are Fernet-encrypted at rest and only decrypted for a caller with a legitimate relationship to that record (parent of that child, or specialist/admin). The audit log (`GET /audit-logs`, admin-only) records *that* an action happened, never the PHI payload itself — don't expect to reconstruct patient data from the audit trail.

### Reference implementation

The frontend in this repo **is** a complete reference client for this API — see [Frontend architecture](#frontend-architecture--how-the-react-app-is-built) above, particularly [`apiFetch.ts`](frontend/src/apiFetch.ts) for the request wrapper and [`pages/AssessmentFlow.tsx`](frontend/src/pages/AssessmentFlow.tsx) for the full next-question/respond loop.

---

## Setup & running locally

### Prerequisites
- Docker and Docker Compose, **or** Python 3.11+ and Node.js 18+ for a native setup.
- An [OpenRouter](https://openrouter.ai/keys) API key (required for AI report generation; the rest of the app works without it).

### 1. Environment variables

```bash
cp .env.example .env
```

Fill in `.env` with your own values — it's gitignored and never committed:

```bash
python -c "import secrets; print(secrets.token_hex(32))"                                 # JWT_SECRET
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # PHI_ENCRYPTION_KEY
```

### 2a. Run with Docker Compose

```bash
docker-compose up --build
```

Boots PostgreSQL (`:5432`), Qdrant (`:6333`), backend (`:8000`), frontend (`:5173`).

### 2b. Run natively (no Docker)

```bash
# Backend
cd backend
cp .env.example .env   # fill in the same secrets
python -m venv venv && venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Without Qdrant running, the RAG pipeline automatically falls back to in-memory vector search — no extra configuration needed for local development.

### 3. Seed data

The backend auto-seeds demo credentials on first boot. To also populate synthetic clinical records:

```bash
docker-compose exec backend python seed.py
# or, natively:
python seed.py
```

### Deploying to production

For a Vercel deployment (frontend + backend as separate projects, Postgres instead of SQLite), see [DEPLOYMENT.md](DEPLOYMENT.md).

### 4. Demo accounts (local demos only)

There are no built-in passwords. For a local demo, set in `backend/.env`:

```
APP_ENV=development
SEED_DEMO_USERS=true
DEMO_PASSWORD=choose-a-12+-character-password
```

Then run `python seed.py` (or just start the server on an empty database). It creates `parent`, `teacher`, `specialist` and `admin`, all with your `DEMO_PASSWORD`. Set `VITE_DEMO_MODE=true` in the frontend to show role shortcuts that prefill the username. Never enable demo seeding on a deployment with real data.

---

## Demo flow (proof of concept)

One case moves through three roles: a **parent** registers a child and answers an adaptive questionnaire; a **teacher** adds school-environment answers; a **specialist** records a clinical observation and reviews deterministic severity scores, priority tier and parent/teacher discrepancy flags before an AI-drafted report is approved.
Screenshots of each role's flow (fictional data) are in [`docs/walkthrough`](docs/walkthrough/README.md).

---

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /auth/login` | Username/password → JWT access + refresh tokens |
| `POST /auth/register` | Create a new user |
| `POST /auth/refresh` | Exchange a refresh token for a new access token |
| `GET /children` | List children visible to the current role |
| `GET /sessions` / `GET /sessions/{id}` | Assessment session state |
| `POST /sessions/{id}/respond` | Submit an answer to the current question |
| `GET /sessions/{id}/next-question` | Adaptive next-question resolution |
| `POST /sessions/{id}/observation` | Specialist clinical observation entry |
| `POST /sessions/{id}/generate-report` | Run evaluator → RAG → LLM and produce a draft |
| `GET /sessions/{id}/report` | Fetch the current draft/approved report |
| `POST /sessions/{id}/report/approve` | Specialist sign-off, locks the report |
| `GET /audit-logs` | Admin-only security audit trail |

Interactive docs are served by FastAPI at `/docs` (Swagger UI) once the backend is running.

---

## Disclaimers

> **Clinical disclaimer:** This platform is a decision-support tool, not an independent diagnostic instrument. Any AI-generated content is a draft requiring review, editing, and approval by a licensed clinical specialist.
>
> **Technical & privacy disclaimer:** This is a Proof of Concept. It is not currently certified for HIPAA, GDPR, or any national health authority standard. Do not use real patient data with this version — synthetic data only.
