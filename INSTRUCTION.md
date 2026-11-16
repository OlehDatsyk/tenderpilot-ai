# TenderPilot AI — Installation, Configuration & Deployment Guide

## 1. Prerequisites

| Software | Version | Notes |
| --- | --- | --- |
| Python | 3.12 or newer | https://www.python.org/downloads/ |
| Node.js | 20+ (22 LTS recommended) | https://nodejs.org/ |
| Docker Desktop | current | Runs the local PostgreSQL 16 container. Without Docker, point `DATABASE_URL` at any PostgreSQL 14+ server. |
| Git | any | For cloning / contributing |

## 2. Run locally with the launcher (recommended)

**Windows:** double-click `Start App.bat`.
**macOS:** run `chmod +x "Start App (Mac).command"` once, then double-click it.

What the launcher does (safe to run repeatedly — it never deletes files or resets the database):

1. Checks Python, Node.js/npm and Docker.
2. Creates `backend/.venv` if missing and installs `backend/requirements.txt`.
3. Installs frontend packages (`npm ci`) if `frontend/node_modules` is missing.
4. Creates `backend/.env` from `.env.example` **only if it does not exist**, generating `SECRET_KEY` and `ENCRYPTION_KEY`.
5. Starts PostgreSQL (`docker compose up -d db`, port `127.0.0.1:5435`) and waits until it is ready.
6. Runs `alembic upgrade head`.
7. Starts the API (http://127.0.0.1:8000) and the web app (http://localhost:5173) and opens the browser.

Stop the app by closing the two server windows (Windows) or pressing Ctrl+C (macOS). The database keeps running in Docker; stop it with `docker compose stop db`. Your data is kept in the `pgdata` Docker volume.

### Demo data (optional)

```bash
cd backend
.venv/Scripts/python -m app.seed --email you@example.com      # macOS: .venv/bin/python
```

Creates a **separate** demo organisation whose records are all prefixed `[DEMO]`, plus a fictional tender document. A random password is printed once (or pass `--password`). It refuses to run for an email that already exists.

## 3. Manual setup

```bash
docker compose up -d db
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy ..\.env.example .env         # macOS/Linux: cp ../.env.example .env
# edit .env: set SECRET_KEY and ENCRYPTION_KEY (commands are in the file)
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173 - /api is proxied to http://127.0.0.1:8000
```

Full stack in containers instead: `docker compose --profile full up --build` (web on http://localhost:8080, API on http://localhost:8000).

## 4. Environment variables

The backend reads `./.env`, then `./backend/.env`, then real environment variables (highest priority). In production, use the hosting platform's environment settings only.

| Variable | Required | Secret | Default | Description / where to get it |
| --- | --- | --- | --- | --- |
| `ENVIRONMENT` | prod: yes | no | `development` | `production` enables strict checks (secret length, no SQLite, no wildcard CORS, persistent storage). |
| `SECRET_KEY` | **yes** (prod) | **yes** | dev: ephemeral | JWT signing key, ≥ 32 chars. `python -c "import secrets; print(secrets.token_urlsafe(48))"` or Render `generateValue`. |
| `DATABASE_URL` | **yes** | **yes** | local Docker URL | PostgreSQL connection string. On Render, use the database's *Internal Database URL* (the Blueprint wires this automatically). |
| `CORS_ORIGINS` | prod: yes | no | localhost:5173 | Comma-separated exact frontend origins, e.g. `https://tenderpilot-ai-frontend.onrender.com`. |
| `FRONTEND_URL` | no | no | localhost:5173 | Informational; used in documentation/links. |
| `TRUSTED_PROXY_HEADERS` | no | no | `false` | `true` behind Render/another trusted proxy so rate limiting uses the real client IP. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | no | `15` | Access token lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | no | `14` | Refresh token lifetime. |
| `REGISTRATION_ENABLED` | no | no | `true` | `false` = invitation-only sign-up. |
| `RATE_LIMIT_AUTH_PER_MINUTE` | no | no | `10` | Per-IP limit for auth endpoints. |
| `RATE_LIMIT_AI_PER_MINUTE` | no | no | `20` | Per-IP limit for AI endpoints. |
| `AI_PROVIDER` | no | no | `none` | `none`, `demo`, `anthropic`, `openai`, `gemini`. |
| `AI_MODEL` | no | no | provider default | Anthropic default `claude-opus-5-5`. Set explicitly for OpenAI/Gemini (model names change often). |
| `ANTHROPIC_API_KEY` | if provider=anthropic | **yes** | — | https://console.anthropic.com/ → API keys |
| `OPENAI_API_KEY` | if provider=openai | **yes** | — | https://platform.openai.com/api-keys |
| `GEMINI_API_KEY` | if provider=gemini | **yes** | — | https://aistudio.google.com/apikey |
| `AI_TIMEOUT_SECONDS` | no | no | `180` | Per-request provider timeout. |
| `AI_MAX_RETRIES` | no | no | `2` | Retries for transient provider errors (429/5xx/network). |
| `AI_MAX_CONTEXT_CHARS` | no | no | `400000` | Max document characters sent per analysis; truncation is reported to users. |
| `ALLOW_ORG_AI_KEYS` | no | no | `true` | Allow organisation admins to store their own provider key. |
| `ENCRYPTION_KEY` | if org keys used | **yes** | — | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (Render `generateValue` also works). |
| `STORAGE_BACKEND` | no | no | `database` | `database` = files in PostgreSQL (persistent). `local` requires a persistent disk in production. |
| `LOCAL_STORAGE_DIR` | no | no | `./storage` | Used only with `STORAGE_BACKEND=local`. |
| `LOCAL_STORAGE_IS_PERSISTENT` | no | no | `false` | Must be `true` to use `local` storage in production (e.g. with a Render disk). |
| `MAX_UPLOAD_MB` | no | no | `20` | Upload size limit. |
| `DOCS_ENABLED` | no | no | `true` | Serve `/api/docs`, `/api/redoc`, `/api/openapi.json`. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | no | no | `5` / `5` | SQLAlchemy pool sizing. Keep small on small database plans. |
| `LOG_LEVEL` | no | no | `INFO` | Python logging level. |
| `VITE_API_URL` (frontend) | prod: yes | no (public) | blank | Backend URL embedded at build time. A bare host is accepted (`https://` is added). |

## 5. AI providers

1. Choose a provider and create an API key (links above). Check the provider's data-processing terms — uploaded tender documents are sent to it during analysis.
2. Either set `AI_PROVIDER` + key on the server, or sign in as an owner/admin and use **Settings → AI provider** (key stored encrypted per organisation).
3. Confirm the status card shows *Configured* and the expected provider/model.

Behaviour without a provider: AI buttons are disabled with an explanation; everything else works. Demo mode output is always marked "Demo mode — rule-based heuristic output. No AI model was used."

## 6. Testing

```bash
cd backend
pytest -q                                                                         # SQLite, isolated temp DB
TEST_DATABASE_URL=postgresql+psycopg://tenderpilot:tenderpilot@127.0.0.1:5435/tenderpilot_test pytest -q   # PostgreSQL
ruff check . && ruff format --check app tests && mypy app

cd ../frontend
npm run lint && npm run typecheck && npm test && npm run build
```

The PostgreSQL test database (`tenderpilot_test`) is created by `docker/initdb` and is **wiped between tests** — never point `TEST_DATABASE_URL` at a database with real data. AI providers are always mocked.

## 7. API documentation

With `DOCS_ENABLED=true`: Swagger UI at `/api/docs`, ReDoc at `/api/redoc`, OpenAPI JSON at `/api/openapi.json`. All endpoints are under `/api/v1`. Health checks: `/health` (liveness) and `/health/ready` (database + migrations).

## Deploying to Render

### Architecture

| Service | Type | Name |
| --- | --- | --- |
| PostgreSQL | Render PostgreSQL | `tenderpilot-ai-db` |
| API | Web service (Python) | `tenderpilot-ai-api` |
| Frontend | Static site | `tenderpilot-ai-frontend` |

Uploaded documents are stored in PostgreSQL (`STORAGE_BACKEND=database`), so no persistent disk or external object storage is required and nothing is lost when Render restarts the API on its ephemeral filesystem. Database size therefore grows with uploads — choose a database plan with enough storage.

### Option A — Blueprint (recommended)

1. Push this repository to GitHub.
2. In the Render Dashboard choose **New → Blueprint**, connect the GitHub repository and select the `main` branch. Render reads `render.yaml`.
3. When prompted for unsynced variables, leave the AI keys empty (or enter one) — `AI_PROVIDER` defaults to `none`.
4. Click **Apply**. Render creates the database first, then the API and the static site.
5. After the first deploy, check the actual service URLs. If Render assigned different subdomains than `tenderpilot-ai-api.onrender.com` / `tenderpilot-ai-frontend.onrender.com`, update:
   - API → Environment: `CORS_ORIGINS` and `FRONTEND_URL` = the frontend URL.
   - Frontend → Environment: `VITE_API_URL` = the API URL, then **Manual Deploy → Clear build cache & deploy** (Vite embeds it at build time).
6. To enable AI: API → Environment → set `AI_PROVIDER` (and `AI_MODEL` if needed) plus the matching key → save (Render redeploys).

### Option B — Manual setup

1. **PostgreSQL:** New → PostgreSQL, name `tenderpilot-ai-db`, database `tenderpilot`. Copy the *Internal Database URL*.
2. **API:** New → Web Service from the repo. Root directory `backend`; Runtime Python; Build command `pip install -r requirements.txt`; Start command:
   `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   Health check path `/health/ready`. Environment: `PYTHON_VERSION=3.12.8`, `ENVIRONMENT=production`, `DATABASE_URL` (internal URL), `SECRET_KEY` and `ENCRYPTION_KEY` (generate), `CORS_ORIGINS`, `TRUSTED_PROXY_HEADERS=true`, `STORAGE_BACKEND=database`, `AI_PROVIDER=none` (or a provider + key).
3. **Frontend:** New → Static Site from the repo. Root directory `frontend`; Build command `npm ci && npm run build`; Publish directory `dist`; Environment `VITE_API_URL=<API URL>`; Redirects/Rewrites: `/*` → `/index.html` (Rewrite).

### Post-deployment verification

```bash
curl https://<api>/health          # {"status":"ok",...}
curl https://<api>/health/ready    # {"status":"ok","database":"ok"}
curl -i -X OPTIONS https://<api>/api/v1/tenders -H "Origin: https://<frontend>" -H "Access-Control-Request-Method: GET"   # allow-origin echoes the frontend
```

Then in the browser: register a test account, create a tender, upload a small TXT file, confirm it is *Processed*, check **Settings → AI provider** status, open the dashboard. Use test data only.

### Operational notes

- Migrations run on every start and are additive; never run `alembic downgrade` against production.
- Free Render web services sleep when idle (first request is slow) and free databases expire — use paid plans for real use.
- Analysis runs execute as in-process background tasks; a restart marks interrupted runs as failed (users can re-run). Use a single API instance, or add a job queue before scaling out.
- Logs never include passwords, tokens, API keys or document content.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Launcher: "Docker is not running" | Start Docker Desktop, or set `DATABASE_URL` in `backend/.env` to another PostgreSQL. |
| Migrations hang/fail locally | Use `127.0.0.1` (not `localhost`) in `DATABASE_URL`; check `docker compose ps`. |
| Port 5173/8000 already in use | Stop the other process (Vite uses a strict port). |
| Frontend shows "Cannot reach the TenderPilot API" | Backend not running, or wrong `VITE_API_URL` / `CORS_ORIGINS` in production. |
| Document status "OCR needed" | The PDF is scanned; upload a text-based PDF, DOCX or TXT. |
| AI says "not configured" | Set a provider and key (section 5). |
