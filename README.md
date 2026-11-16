# TenderPilot AI

**AI-assisted tender and proposal management — understand tenders faster, decide where to bid, and respond with confidence.**

[![CI](https://github.com/OlehDatsyk/tenderpilot-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/OlehDatsyk/tenderpilot-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 🔗 Live demo

| | URL |
| --- | --- |
| **Application** | https://tenderpilot-ai-frontend.onrender.com |
| API | https://tenderpilot-ai-api.onrender.com |
| API documentation | https://tenderpilot-ai-api.onrender.com/api/docs |

> **This is a free demo deployment.** It has no database server: data is temporary and is deleted whenever the server restarts or sleeps (after ~15 minutes without traffic — the first visit afterwards takes about a minute to wake up). AI features run in clearly labelled demo mode. Please don't upload confidential documents. See [INSTRUCTION.md](INSTRUCTION.md#deploying-to-render) to deploy with a persistent PostgreSQL database.

TenderPilot AI is a full-stack SaaS application for teams that respond to public and private tenders, RFPs, RFQs, RFIs, procurement opportunities and supplier questionnaires. It extracts requirements from tender documents with **verifiable source references**, tracks compliance, supports bid/no-bid decisions, drafts proposals **without inventing company facts**, and keeps the whole team's work in one place.

> AI output is always labelled. Extracted items show whether their source quote was verified in the uploaded document, demo-mode output is marked as a rule-based heuristic, and generated proposal text uses `[COMPANY INFORMATION REQUIRED]` placeholders wherever verified company information is missing.

---

## Main features

| Area | What it does |
| --- | --- |
| **Accounts & organisations** | Registration, login, JWT access tokens with rotating refresh tokens (reuse detection), profile, password change, organisation members & roles (owner/admin/member), invitation links. |
| **Dashboard** | Totals, active tenders, awaiting review, upcoming deadlines, completed proposals, win/loss, pipeline, recent projects and activity, alerts — all computed from real records. |
| **Tender workspace** | Create/edit/archive/delete tenders with buyer, reference, type, status, priority, deadline, value & currency, notes; search, filter, sort and paginate. |
| **Document intelligence** | Upload PDF, DOCX and TXT (validated by extension, MIME and file signature; size-limited). Text extraction with page numbers for PDFs; scanned PDFs are reported as *OCR needed* — no text is fabricated. |
| **AI tender analysis** | Extracts overview, requirements (eligibility, mandatory, technical, commercial, certifications, supporting documents, submission), evaluation criteria & weights, important dates, risks and missing information. Every quote is checked against the extracted text; page numbers are only kept when verified. |
| **Compliance matrix** | Requirement status (Not Started → Compliant/Partially/Non-Compliant/Needs Review), assignee, evidence and comments, filters, and completion percentages from real records. Provenance badge on every row (AI-extracted / Demo / User-entered). |
| **Bid / no-bid** | Nine-factor assessment, 0–100 score, advantages, risks, missing information and next steps — clearly presented as a decision aid. Users record the final decision and reasoning (overrides are tracked). |
| **Proposal generator** | Outline from requirements and evaluation criteria, section drafting and "improve clarity" rewrites, requirement coverage, editable sections saved to the database. Factual claims may only come from the verified **company profile** and recorded compliance evidence. |
| **Research assistant** | Per-tender Q&A over that tender's documents and compliance data only, with cited sources; says clearly when the documents do not support an answer. Conversations are private per user. |
| **Tasks** | Tasks per tender or organisation, assignees from the same organisation, due dates, priorities, statuses, comments, overdue highlighting. |
| **Analytics** | Pipeline by status, bid decisions (recommended vs final), win/loss, compliance completion, upcoming deadlines, monthly activity, pipeline value. |
| **Export centre** | Tender summary, analysis report, compliance matrix, bid/no-bid report and proposal drafts as PDF / DOCX (+ CSV for the matrix). Generated content is labelled in every file. |

## Technology

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL (psycopg 3), PyJWT, Argon2id (argon2-cffi), cryptography (Fernet), pypdf, python-docx, ReportLab.
- **AI:** provider-independent layer with adapters for **Anthropic Claude** (official `anthropic` SDK), **OpenAI** and **Google Gemini** (REST), plus a deterministic, clearly labelled **demo mode**. Structured outputs are validated with Pydantic before storage.
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, Radix UI primitives, Lucide icons, Recharts, React Router, TanStack Query, React Hook Form + Zod, Sonner toasts.
- **Quality:** pytest (SQLite + PostgreSQL), Ruff, mypy, Vitest + Testing Library, ESLint, GitHub Actions.
- **Deployment:** Docker images, Docker Compose for local PostgreSQL, Render Blueprint (`render.yaml`).

## Architecture

```
 React SPA (Vite build)  ──HTTPS + Bearer JWT──►  FastAPI  /api/v1/*
   TanStack Query                                   │
   React Router                                     ├─ Auth (Argon2id, JWT, rotating refresh tokens)
                                                    ├─ Org-scoped services (every query filtered by organisation)
                                                    ├─ Document pipeline (validate → store → extract, background task)
                                                    ├─ AI layer: prompts (untrusted-data wrapping) → adapter
                                                    │     (Anthropic | OpenAI | Gemini | demo) → Pydantic validation
                                                    │     → source verification → persistence
                                                    ├─ Exports (ReportLab PDF, python-docx DOCX, CSV)
                                                    ▼
                                               PostgreSQL (all data, incl. uploaded files in `stored_files`)
```

More detail: [INSTRUCTION.md](INSTRUCTION.md) (setup, configuration, deployment) and [SECURITY.md](SECURITY.md).

## Screenshots

_Screenshots are not yet included in the repository._ Placeholders:

- `docs/screenshots/dashboard.png` — Dashboard
- `docs/screenshots/compliance.png` — Compliance matrix with source verification
- `docs/screenshots/bid.png` — Bid / no-bid assessment
- `docs/screenshots/proposal.png` — Proposal editor

## Quick start (local)

**Requirements:** Python 3.12+, Node.js 20+ (22 LTS recommended), Docker Desktop (for the local PostgreSQL container).

- **Windows:** double-click **`Start App.bat`**
- **macOS:** double-click **`Start App (Mac).command`** (first time: `chmod +x "Start App (Mac).command"`)

The launcher checks prerequisites, creates `backend/.venv`, installs dependencies, creates `backend/.env` with freshly generated secrets (only if it does not exist), starts PostgreSQL with Docker Compose, applies migrations and starts both servers:

| | URL |
| --- | --- |
| Application | http://localhost:5173 |
| API | http://127.0.0.1:8000 |
| API docs (OpenAPI) | http://127.0.0.1:8000/api/docs |

Local development runs in **demo mode** (`AI_PROVIDER=demo`) by default — no API key needed, and all demo output is labelled. Optional demo data: `cd backend && .venv/Scripts/python -m app.seed --email you@example.com` (macOS: `.venv/bin/python`).

### Manual setup

```bash
docker compose up -d db                       # PostgreSQL on 127.0.0.1:5435
cd backend
python -m venv .venv && .venv/Scripts/activate # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env                       # then set SECRET_KEY and ENCRYPTION_KEY
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# new terminal
cd frontend && npm ci && npm run dev
```

## Configuration

All settings are environment variables — see [`.env.example`](.env.example) for the complete, commented list. The most important:

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `development` or `production` (production refuses unsafe settings). |
| `SECRET_KEY` | JWT signing key (≥ 32 random characters). **Secret.** |
| `DATABASE_URL` | PostgreSQL URL (`postgres://` and `postgresql://` are normalised automatically). **Secret.** |
| `CORS_ORIGINS` | Comma-separated frontend origins. |
| `AI_PROVIDER` / `AI_MODEL` | `none`, `demo`, `anthropic`, `openai`, `gemini`; model name (blank = provider default). |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | Provider keys. **Secret.** |
| `ENCRYPTION_KEY` | Fernet key used to encrypt organisation-supplied provider keys. **Secret.** |
| `STORAGE_BACKEND` | `database` (default, persistent in PostgreSQL) or `local`. |
| `VITE_API_URL` | Frontend build-time backend URL (public, not secret). |

## Database

PostgreSQL 16 locally (Docker Compose, port 5435, bound to 127.0.0.1). Schema changes are managed by Alembic (`backend/alembic/versions`); the test suite verifies that migrations apply, roll back, and match the ORM models exactly. All tables use UUID keys, timestamps, foreign keys with cascade rules and indexes on organisation-scoped lookups.

## AI provider configuration

- **Server-wide:** set `AI_PROVIDER` and the matching API key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY`).
- **Per organisation:** owners/admins can choose a provider/model in **Settings → AI provider** and store their own key; keys are encrypted with `ENCRYPTION_KEY` and never returned to the browser.
- **No provider:** everything except AI features keeps working, and the UI explains how to enable AI.
- **Demo mode:** deterministic keyword heuristic for evaluation and tests — always labelled, never presented as AI.

Defaults: Anthropic uses `claude-opus-5-5` with streaming, adaptive thinking (`effort: high`) and server-side refusal fallbacks. OpenAI and Gemini model names change often — set `AI_MODEL` explicitly for them.

## Running tests

```bash
cd backend && pytest -q                                   # SQLite
TEST_DATABASE_URL=postgresql+psycopg://tenderpilot:tenderpilot@127.0.0.1:5435/tenderpilot_test pytest -q
ruff check . && mypy app
cd ../frontend && npm run lint && npm run typecheck && npm test && npm run build
```

AI providers are mocked in all automated tests — no paid API calls are made.

## Deployment

The repository includes a Render Blueprint (`render.yaml`) that creates `tenderpilot-ai-api` (FastAPI) and `tenderpilot-ai-frontend` (static site) on free plans, using an external PostgreSQL database such as a free Neon database (Render allows one free database per workspace). Uploaded documents are stored in PostgreSQL, so nothing depends on Render's ephemeral disk. Step-by-step instructions, the environment-variable checklist and post-deploy checks are in [INSTRUCTION.md](INSTRUCTION.md#deploying-to-render).

## Security

Argon2id password hashing, short-lived JWTs with rotating refresh tokens and reuse detection, organisation-level isolation on every query (cross-organisation IDs return 404), rate limiting on auth and AI endpoints, strict upload validation, encrypted provider keys, security headers, CSV-injection protection, and prompt-injection defences for document content. See [SECURITY.md](SECURITY.md) for details and how to report vulnerabilities.

## Project structure

```
tenderpilot-ai/
├── backend/
│   ├── app/
│   │   ├── ai/            # provider adapters, prompts, output schemas, demo engine
│   │   ├── api/v1/        # REST routers (auth, organisation, tenders, documents, analysis, proposals, tasks, insights, exports)
│   │   ├── core/          # settings, security, rate limiting
│   │   ├── db/            # SQLAlchemy base & session
│   │   ├── models/        # ORM models
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── services/      # access control, extraction, storage, AI workflows, compliance, exports
│   │   ├── main.py        # FastAPI app factory
│   │   └── seed.py        # explicit demo-data command
│   ├── alembic/           # migrations
│   ├── tests/             # pytest suite (mocked AI)
│   └── Dockerfile
├── frontend/
│   ├── src/ (components, lib, pages, test)
│   ├── Dockerfile, nginx.conf
├── docker/initdb/         # creates the separate test database
├── .github/workflows/ci.yml
├── docker-compose.yml, render.yaml, .env.example
├── Start App.bat, Start App (Mac).command
└── README.md, INSTRUCTION.md, PROJECT_REVIEW.md, SECURITY.md, CHANGELOG.md, LICENSE
```

## Current limitations

- No OCR: scanned PDFs are detected and reported, but not read.
- DOCX/TXT have no fixed pages, so their sources are shown as sections, not page numbers.
- Real AI providers are integrated and unit-tested with mocks, but no live paid API call was made during development.
- Invitations produce a link to share manually; no email is sent. One organisation per user.
- Rate limiting and background processing are in-process (single instance). Use a shared limiter and a job queue to scale horizontally.
- Very long tender packs are truncated to `AI_MAX_CONTEXT_CHARS`; the analysis says so explicitly when this happens.

## License

[MIT](LICENSE)
