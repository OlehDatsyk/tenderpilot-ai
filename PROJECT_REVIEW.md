# Project Review & Audit Report — TenderPilot AI 1.0.0

**Audit date:** 16 November 2026
**Scope:** full repository — backend, frontend, database/migrations, authentication, authorisation, AI layer, document processing, storage, exports, configuration, Docker, Render Blueprint, launch scripts, CI, documentation, tests.
**Method:** code review of the actual implementation, automated tests (unit, integration, security-focused), linting and type checking, dependency vulnerability scanning, migration drift checks, Docker image builds, and an end-to-end run of the real application (FastAPI + PostgreSQL + Vite) exercised through the API and the browser.

## 1. Results summary

| Check | Result |
| --- | --- |
| Backend tests — SQLite | **70 passed, 0 failed** |
| Backend tests — PostgreSQL 16 | **70 passed, 0 failed** |
| Frontend tests (Vitest + Testing Library) | **11 passed, 0 failed** |
| Ruff lint / format check | Pass / Pass |
| mypy (`app/`, 46 files) | No issues |
| TypeScript (`tsc -b`) | No errors |
| ESLint | 0 errors, 1 warning (react-refresh hint in `lib/auth.tsx`, cosmetic) |
| Production frontend build | Pass |
| Alembic: upgrade, downgrade, model drift | Pass (test + `alembic check`) |
| `pip-audit` (runtime requirements) | No known vulnerabilities |
| `npm audit` (all dependencies) | 0 vulnerabilities (after upgrades, see §3) |
| Docker images (`backend/`, `frontend/`) | Both build successfully |
| Windows launcher (`Start App.bat`, dry-run mode) | All steps pass (checks, deps, env, DB, migrations) |
| macOS launcher | Shell syntax check only (`bash -n`) — **not executed on macOS** |
| End-to-end run (real servers, PostgreSQL, demo AI) | Register → tender → upload → extraction → analysis → compliance update → bid assessment + decision → proposal outline + section draft → assistant → task → 4 exports → dashboard/analytics: all succeeded |
| UI pages rendered with real data (dashboard, tenders, tender tabs, proposal editor, tasks, analytics, exports, company, settings, 404) | Rendered; no new console errors after fixes |
| Mobile width (375 px) | No horizontal page overflow on dashboard, tenders, tender workspace, proposal editor; sidebar collapses to a menu |

Not verified: visual appearance via screenshots (the browser pane was not visible during the audit, so rendering was checked through page text and DOM measurements); live calls to paid AI providers (adapters are tested with mocked SDK/HTTP only); the macOS launcher on real macOS; the Render deployment itself.

## 2. Areas reviewed

- **Functional:** all 18 functional areas listed in the brief — registration/login, profile/settings, tender CRUD/search/filter, uploads, PDF/DOCX/TXT extraction, processing states, AI analysis, requirement extraction, compliance updates, bid/no-bid, proposals, company profile, assistant, tasks/comments, analytics, exports, error and empty states.
- **Backend:** HTTP methods/status codes (201/202/204/401/403/404/409/422/429/502), Pydantic validation on every input, pagination/sorting/filtering, transaction handling (single commit per request; background jobs use their own sessions and always record a final state), cascade rules, exception handling (generic 500 without internals; validation errors without echoing values).
- **Security:** see [SECURITY.md](SECURITY.md). Cross-organisation access was tested by swapping IDs on 19 read and 15 write endpoints plus assignee checks — all return 404/422.
- **AI:** adapters, key handling, model config, structured-output validation and repair, timeouts/retries, token tracking, refusal/max-token handling, prompt-injection wrapping and sanitisation, source verification, demo labelling, per-tender/per-user context isolation.
- **Render readiness:** start command binds `0.0.0.0:$PORT`, `DATABASE_URL` normalisation, migrations on start, health checks, persistent storage in PostgreSQL, CORS restricted to configured origins, production configuration guards.

## 3. Problems found and changes made

| # | Severity | Problem | Fix |
| --- | --- | --- | --- |
| 1 | **High** | `react-router-dom` 6.x advisories (open redirect via backslash in `<Link>`/`useNavigate`), `zod` < 4.6.6 (memory exhaustion on oversized collections), `vitest`/`tinypool` advisories (dev tooling, rated critical). | Upgraded to react-router-dom 7.18.5, zod 4.6.7 (+ @hookform/resolvers 5), vitest 5.1.0. `npm audit`: 0. |
| 2 | **High** | Rate-limit bypass: with `--forwarded-allow-ips='*'` and left-most `X-Forwarded-For` parsing, a client could send a fake IP per request. | Client IP now taken from the right-most (proxy-appended) entry; removed blanket forwarded-IP trust from start commands. Regression test added. |
| 3 | **High** | Frontend crash: an effect returned the Promise from `scrollIntoView()` (current Chromium), React treated it as a cleanup and the whole app unmounted when leaving the assistant tab. | Effect bodies fixed; added an error boundary around routed pages so a page error can no longer blank the app. |
| 4 | Medium | Session handling: a stale single-flight refresh promise could be reused, and a 401 after a successful refresh did not end the session. | Refresh promise cleared deterministically; any final 401 ends the session. Covered by tests. |
| 5 | Medium | Render `generateValue` produces standard base64, Fernet expects URL-safe base64. | Encryption key is normalised to the URL-safe alphabet. |
| 6 | Medium | Local `DATABASE_URL` used `localhost`, which can resolve to IPv6 and hang against Docker's IPv4-only port binding. | Defaults use `127.0.0.1`; documented in troubleshooting. |
| 7 | Medium | A developer's local `.env` could leak into the test run. | Tests set `TENDERPILOT_IGNORE_ENV_FILE`; settings skip `.env` files then. |
| 8 | Low | Demo heuristic chose the clarification-question date as the submission deadline; demo outline titles were not descriptive. | Deadline phrases are matched from most to least specific; outline titles include the requirement text. |
| 9 | Low | 47 mypy findings (Optional narrowing, literal types, SDK union types). | All resolved; mypy added to CI. |
| 10 | Low | Batch-script labels inside parenthesised blocks (unsupported by `cmd`). | Database wait moved into a subroutine; script verified by a dry run. |

No secrets were found in the repository (see §5). No misleading controls remain: every visible button performs an action or is disabled with an explanation (e.g. AI actions when no provider is configured, "Improve" in demo mode).

## 4. Tests added during the audit

- `test_providers.py` — Anthropic adapter request shape (model, streaming, effort, refusal fallbacks, no sampling params), refusal and max-token handling, OpenAI retry on 503 and no retry on 401 (key not leaked in the error), Gemini key sent in a header (never in the URL).
- `test_config.py` — production refuses short secrets, SQLite, wildcard CORS and non-persistent local storage; DB URL normalisation.
- Rate-limit spoofing regression test; frontend session-refresh tests.

## 5. Secret scan

Tracked files were scanned for API-key prefixes (`sk-`, `sk-ant-`, `AKIA`, `gho_`, `ghp_`, `AIza`), private-key headers, and `password=`/`secret=` assignments with literal values. Findings: only placeholders in `.env.example`, development-only database credentials in `docker-compose.yml`/CI (local container `tenderpilot/tenderpilot`, bound to 127.0.0.1, not used in production), and obviously fake test strings in tests (e.g. `sk-test-not-real-0000`). `backend/.env` (generated local secrets) is git-ignored and was never committed. The repository had no Git history before publication, so there is no historical exposure to rotate.

## 6. Performance & reliability notes

- List endpoints aggregate counts with grouped queries (no N+1) — tender list, compliance percentages, task comment counts, proposal section counts.
- Uploads are capped (`MAX_UPLOAD_MB`), DOCX zip size is bounded, PDFs over 2,000 pages are rejected, and AI context is capped with an explicit truncation warning.
- Document extraction and tender analysis run as background tasks; the UI polls status. Interrupted runs are marked failed on restart.
- The frontend lazy-loads pages; the chart library is split into its own chunk loaded only on the analytics page. Main bundle ≈ 146 kB gzipped.

## 7. Remaining risks / known limitations

1. **No OCR** for scanned PDFs (detected and reported, not processed).
2. **Live AI providers not exercised** — adapters follow the documented APIs and are covered by mocked tests, but the first real call should be made with a test key and a small document. OpenAI/Gemini default model names may need updating (`AI_MODEL`).
3. **In-process rate limiting and background jobs** — correct for a single API instance; multi-instance deployments need a shared limiter and a job queue.
4. **Files in PostgreSQL** — simple and persistent, but database storage grows with uploads; for very large volumes add S3-compatible storage (not implemented).
5. **Session in `localStorage`** — mitigated by CSP and the absence of HTML rendering, but an XSS bug would expose tokens (documented trade-off).
6. **Single organisation per user**; invitations are links, no email delivery.
7. ESLint warning (react-refresh) in `lib/auth.tsx` is cosmetic.

## 8. Deployment readiness

- **GitHub publication:** published at https://github.com/OlehDatsyk/tenderpilot-ai (public); CI passes.
- **Render:** **deployed and verified** as a free *demo* deployment (16 Nov 2026):
  - Frontend https://tenderpilot-ai-frontend.onrender.com, API https://tenderpilot-ai-api.onrender.com (Frankfurt), docs at `/api/docs`.
  - Verified live: `/health` and `/health/ready` OK; CORS allows only the frontend origin; SPA deep links and security headers served; frontend bundle targets the public API URL; the browser loads the app without console errors; a full workflow (register → tender → upload → extraction → demo analysis → compliance → bid decision → proposal → assistant → task → PDF/DOCX/CSV exports → dashboard/analytics) succeeded against the live API with a throwaway test account.
  - **Not persistent:** `EPHEMERAL_DEMO=true` with SQLite on Render's ephemeral disk — data is deleted on restart, redeploy and idle spin-down. A permanent banner says so. For persistent data, set `DATABASE_URL` to PostgreSQL (e.g. Neon) and remove `EPHEMERAL_DEMO`.
  - Deployment fixes found during verification: an external database rejected the first pasted credentials (switched to demo mode at the owner's request), and Render's `fromService … host` gave the frontend an internal, unreachable hostname — replaced with the explicit public API URL.
