#!/usr/bin/env bash
# TenderPilot AI - macOS launcher. Double-click in Finder (or run in Terminal).
# Safe to run repeatedly. Never deletes files or resets the database.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_PY="$BACKEND/.venv/bin/python"

fail() { echo; echo "[ERROR] $1"; echo "Startup did not complete. Fix the error above and run the launcher again."; read -r -p "Press Enter to close..." _; exit 1; }

echo
echo "  =============================================="
echo "    TenderPilot AI - starting local environment"
echo "  =============================================="
echo

# 1. Required software
PY_CMD=""
for candidate in python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
    PY_CMD="$candidate"; break
  fi
done
[ -n "$PY_CMD" ] || fail "Python 3.12+ is required (https://www.python.org/downloads/ or 'brew install python@3.12')."
echo "[OK] Python: $($PY_CMD --version)"
command -v node >/dev/null 2>&1 || fail "Node.js 20+ is required (https://nodejs.org/ or 'brew install node')."
command -v npm >/dev/null 2>&1 || fail "npm was not found; reinstall Node.js."
echo "[OK] Node.js $(node --version)"
HAVE_DOCKER=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then HAVE_DOCKER=1; echo "[OK] Docker is running"; else echo "[WARN] Docker is not running - the local PostgreSQL container cannot be started."; fi

# 2. Backend environment
if [ ! -x "$VENV_PY" ]; then
  echo "[..] Creating Python virtual environment"
  "$PY_CMD" -m venv "$BACKEND/.venv" || fail "Could not create the virtual environment."
fi
echo "[..] Installing / updating backend dependencies"
"$VENV_PY" -m pip install --disable-pip-version-check -q -r "$BACKEND/requirements.txt" || fail "Backend dependency installation failed."

# 3. Frontend dependencies
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "[..] Installing frontend dependencies"
  (cd "$FRONTEND" && npm ci --no-audit --no-fund) || fail "Frontend dependency installation failed."
fi
echo "[OK] Dependencies installed"

# 4. Environment configuration (created once, never overwritten)
if [ ! -f "$BACKEND/.env" ]; then
  echo "[..] Creating backend/.env from .env.example with freshly generated secrets"
  ROOT="$ROOT" BACKEND="$BACKEND" "$VENV_PY" - <<'PY' || fail "Could not create backend/.env"
import os, pathlib, re, secrets
from cryptography.fernet import Fernet
src = pathlib.Path(os.environ["ROOT"], ".env.example").read_text(encoding="utf-8")
src = re.sub(r"(?m)^SECRET_KEY=.*$", "SECRET_KEY=" + secrets.token_urlsafe(48), src)
src = re.sub(r"(?m)^ENCRYPTION_KEY=.*$", "ENCRYPTION_KEY=" + Fernet.generate_key().decode(), src)
pathlib.Path(os.environ["BACKEND"], ".env").write_text(src, encoding="utf-8")
PY
  echo "[OK] backend/.env created (AI_PROVIDER=demo; edit it to configure a real AI provider)"
else
  echo "[OK] Using existing backend/.env"
fi

# 5. Database
if [ "$HAVE_DOCKER" = "1" ]; then
  echo "[..] Starting PostgreSQL (docker compose service 'db' on 127.0.0.1:5435)"
  docker compose up -d db || fail "Could not start the database container."
  for _ in $(seq 1 40); do
    docker compose exec -T db pg_isready -U tenderpilot -d tenderpilot >/dev/null 2>&1 && break
    sleep 2
  done
  docker compose exec -T db pg_isready -U tenderpilot -d tenderpilot >/dev/null 2>&1 || fail "PostgreSQL did not become ready in time."
  echo "[OK] PostgreSQL is ready"
else
  echo "[WARN] Continuing without Docker: DATABASE_URL in backend/.env must point to a running PostgreSQL server."
fi
echo "[..] Applying database migrations"
(cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head) || fail "Database migrations failed - check DATABASE_URL in backend/.env"

# 6. Start servers (stopped together with Ctrl+C)
(cd "$BACKEND" && "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
API_PID=$!
(cd "$FRONTEND" && npm run dev) &
WEB_PID=$!
trap 'echo; echo "Stopping..."; kill $API_PID $WEB_PID 2>/dev/null || true' INT TERM EXIT

echo
echo "  ----------------------------------------------"
echo "   Application : http://localhost:5173"
echo "   API         : http://127.0.0.1:8000"
echo "   API docs    : http://127.0.0.1:8000/api/docs"
echo "  ----------------------------------------------"
echo "   Press Ctrl+C in this window to stop both servers."
sleep 4
open "http://localhost:5173" 2>/dev/null || true
wait
