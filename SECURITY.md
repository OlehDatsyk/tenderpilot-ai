# Security

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **"Report a vulnerability"** (Security → Advisories) on this repository rather than opening a public issue. Include steps to reproduce and the affected version/commit. We aim to acknowledge reports within 5 working days.

## Security model

### Authentication
- Passwords are hashed with **Argon2id** (argon2-cffi defaults); hashes are upgraded transparently on login when parameters change. Minimum 10 characters with a letter and a digit.
- **Access tokens:** HS256 JWTs signed with `SECRET_KEY`, 15-minute lifetime, bound to a per-user `token_version` (incremented on password change and member removal, which invalidates all access tokens immediately).
- **Refresh tokens:** opaque random tokens stored only as SHA-256 hashes, rotated on every use. Re-use of a rotated token revokes the whole token family (theft detection). Logout revokes the family.
- Login responses do not reveal whether an account exists, and take similar time either way.
- Tokens are sent as `Authorization: Bearer` headers (no cookies), so the API has no CSRF surface. The SPA stores the session in `localStorage`; this is a deliberate trade-off for a cross-origin static frontend (third-party cookies are increasingly blocked). The frontend renders no user HTML (React escapes all content, no `dangerouslySetInnerHTML`), and the Render static site sends a restrictive Content-Security-Policy to limit XSS impact.

### Authorisation and data isolation
- Every tenant-owned row carries `organization_id`; every lookup by ID is filtered by the caller's organisation (`app/services/access.py`). Objects from other organisations return **404**, indistinguishable from non-existent IDs.
- Assignees (tasks, requirements) must belong to the same organisation.
- Owner/admin roles are required for organisation settings, AI settings, invitations and member management.
- An automated test (`tests/test_isolation.py`) attempts 30+ cross-organisation reads and writes by swapping IDs.

### Uploads
- Allowed types: PDF, DOCX, TXT — checked by extension, declared MIME type **and** file signature (PDF header, DOCX zip structure with a zip-bomb size guard, text without NUL bytes).
- Size limit (`MAX_UPLOAD_MB`, default 20 MB); duplicate uploads are rejected.
- Filenames are sanitised for display only; stored objects use server-generated UUID keys validated against a strict pattern, so path traversal is impossible.
- Files are parsed with pure-Python libraries and never executed. Downloads are always `Content-Disposition: attachment` with `nosniff`.

### AI and prompt injection
- Document text is wrapped in `<untrusted_document>` tags; tag-like sequences that could close the wrapper are neutralised before sending.
- System prompts state that document content is data and must never be followed; the models have **no tools** and cannot take actions.
- All model output is parsed and validated against strict Pydantic schemas before storage; invalid output is rejected (one repair attempt).
- Model-reported quotes and page numbers are verified against the extracted text; unverifiable sources are stored as *unverified* with no page or quote.
- The assistant only receives the selected tender's documents and data from the caller's organisation, plus the caller's own conversation history.

### Secrets
- All secrets come from environment variables; `.env` files are git-ignored and only `.env.example` (placeholders) is committed.
- Organisation-supplied provider keys are encrypted with **Fernet** (AES-CBC + HMAC) using `ENCRYPTION_KEY`, and are never returned to clients (only a masked hint).
- Provider errors are mapped to safe messages; HTTP client debug logging is disabled; validation errors do not echo submitted values (e.g. passwords).

### Transport and headers
- CORS restricted to configured origins (wildcards rejected in production), no credentials.
- Security headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP on API responses, HSTS in production, `Cache-Control: no-store` on API responses.

### Abuse protection
- Sliding-window rate limits per client IP on authentication endpoints (`RATE_LIMIT_AUTH_PER_MINUTE`) and AI endpoints (`RATE_LIMIT_AI_PER_MINUTE`).
- Limits are **in-memory per process**. For multiple instances, add a shared limiter (e.g. Redis) or edge rate limiting.

### Exports
- CSV cells beginning with `=`, `+`, `-`, `@`, tab or CR are prefixed to prevent formula injection.

## Production checklist

- `ENVIRONMENT=production` (the app refuses to start with a short `SECRET_KEY`, SQLite, wildcard CORS, or non-persistent local storage).
- Unique random `SECRET_KEY` and `ENCRYPTION_KEY` (Render's `generateValue` is suitable). Rotating `ENCRYPTION_KEY` makes stored organisation keys unreadable — re-enter them afterwards.
- `CORS_ORIGINS` set to the exact frontend origin; `TRUSTED_PROXY_HEADERS=true` only behind a trusted proxy.
- Consider `REGISTRATION_ENABLED=false` (invitation-only) for private deployments, and `DOCS_ENABLED=false` if the API docs should not be public.
- Review your AI provider's data-processing terms before uploading confidential tender documents.
