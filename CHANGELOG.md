# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-16

### Added
- Authentication: registration, login, logout, rotating refresh tokens with reuse detection, profile, password change, invitations, roles.
- Organisation-scoped tender workspace with search, filters, sorting, pagination, archive and delete.
- Document upload (PDF/DOCX/TXT) with signature validation, database-backed storage and background text extraction; scanned-PDF detection.
- Provider-independent AI layer (Anthropic, OpenAI, Gemini) with Pydantic-validated structured output, retries, timeouts, token tracking and a labelled demo mode.
- AI tender analysis with source-quote verification; compliance matrix; bid/no-bid assessment with recorded final decisions; proposal outline/section drafting with placeholders; per-tender research assistant.
- Tasks with comments and overdue tracking; dashboard; analytics; PDF/DOCX/CSV exports.
- React + TypeScript frontend with responsive layout, loading/empty/error states and confirmation dialogs.
- Test suites (pytest on SQLite and PostgreSQL, Vitest), Ruff, mypy, ESLint, GitHub Actions CI.
- Docker images, Docker Compose, Render Blueprint, Windows and macOS launchers, documentation.

### Security
- Upgraded `react-router-dom` (7.18.5), `zod` (4.6.7) and `vitest` (5.1.0) to resolve `npm audit` advisories found during the audit.
- Fixed a client session bug where a stale refresh promise could be reused and a rejected retry did not end the session.

### Fixed (found during the audit)
- Effect returning `scrollIntoView()`'s Promise crashed the app when leaving the assistant tab in current Chromium; added an error boundary.
- Demo heuristic picked the clarification deadline instead of the submission deadline.
- Local database URL used `localhost`, which could resolve to IPv6 and hang against an IPv4-only Docker port binding.
