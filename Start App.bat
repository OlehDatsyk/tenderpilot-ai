@echo off
setlocal EnableExtensions EnableDelayedExpansion
title TenderPilot AI - local launcher
rem ---------------------------------------------------------------------------
rem  TenderPilot AI - Windows launcher
rem  Safe to run repeatedly. Never deletes files or resets the database.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"
set "ROOT=%CD%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"

echo.
echo  ==============================================
echo    TenderPilot AI - starting local environment
echo  ==============================================
echo.

rem --- 1. Required software ----------------------------------------------------
set "PY_CMD="
where py >nul 2>&1 && (py -3.12 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3.12")
if not defined PY_CMD (
  where python >nul 2>&1 && (python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1 && set "PY_CMD=python")
)
if not defined PY_CMD (
  echo [ERROR] Python 3.12 or newer is required. Install it from https://www.python.org/downloads/
  goto :fail
)
echo [OK] Python found: %PY_CMD%

where node >nul 2>&1 || (echo [ERROR] Node.js 20+ is required. Install it from https://nodejs.org/ & goto :fail)
where npm >nul 2>&1 || (echo [ERROR] npm was not found. Reinstall Node.js from https://nodejs.org/ & goto :fail)
for /f "delims=" %%v in ('node --version') do echo [OK] Node.js %%v

set "HAVE_DOCKER=0"
where docker >nul 2>&1 && (docker info >nul 2>&1 && set "HAVE_DOCKER=1")
if "%HAVE_DOCKER%"=="1" (echo [OK] Docker is running) else (echo [WARN] Docker is not running - the local PostgreSQL container cannot be started.)

rem --- 2. Python virtual environment and backend dependencies -----------------
if not exist "%VENV_PY%" (
  echo [..] Creating Python virtual environment in backend\.venv
  %PY_CMD% -m venv "%BACKEND%\.venv" || (echo [ERROR] Could not create the virtual environment. & goto :fail)
)
echo [..] Installing / updating backend dependencies
"%VENV_PY%" -m pip install --disable-pip-version-check -q -r "%BACKEND%\requirements.txt" || (echo [ERROR] Backend dependency installation failed. & goto :fail)
echo [OK] Backend dependencies installed

rem --- 3. Frontend dependencies -------------------------------------------------
if not exist "%FRONTEND%\node_modules" (
  echo [..] Installing frontend dependencies - the first run can take a few minutes
  pushd "%FRONTEND%"
  call npm ci --no-audit --no-fund || (popd & echo [ERROR] Frontend dependency installation failed. & goto :fail)
  popd
)
echo [OK] Frontend dependencies installed

rem --- 4. Environment configuration (created once, never overwritten) ----------
if not exist "%BACKEND%\.env" (
  echo [..] Creating backend\.env from .env.example with freshly generated secrets
  "%VENV_PY%" -c "import secrets,re,pathlib;from cryptography.fernet import Fernet;src=pathlib.Path(r'%ROOT%\.env.example').read_text(encoding='utf-8');src=re.sub(r'(?m)^SECRET_KEY=.*$','SECRET_KEY='+secrets.token_urlsafe(48),src);src=re.sub(r'(?m)^ENCRYPTION_KEY=.*$','ENCRYPTION_KEY='+Fernet.generate_key().decode(),src);pathlib.Path(r'%BACKEND%\.env').write_text(src,encoding='utf-8')" || (echo [ERROR] Could not create backend\.env & goto :fail)
  echo [OK] backend\.env created ^(AI_PROVIDER=demo; edit it to configure a real AI provider^)
) else (
  echo [OK] Using existing backend\.env
)

rem --- 5. Database --------------------------------------------------------------
if "%HAVE_DOCKER%"=="1" (
  call :startdb || goto :fail
) else (
  echo [WARN] Continuing without Docker: DATABASE_URL in backend\.env must point to a running PostgreSQL server.
)

echo [..] Applying database migrations
pushd "%BACKEND%"
"%VENV_PY%" -m alembic upgrade head || (popd & echo [ERROR] Database migrations failed - check DATABASE_URL in backend\.env & goto :fail)
popd
echo [OK] Database is up to date

rem --- 6. Start servers ---------------------------------------------------------
if defined TP_LAUNCHER_DRY_RUN (
  echo [OK] Dry run complete - all checks passed, servers not started.
  exit /b 0
)
echo [..] Starting backend and frontend in new windows
start "TenderPilot API (close to stop)" /D "%BACKEND%" "%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
start "TenderPilot Web (close to stop)" /D "%FRONTEND%" cmd /c "npm run dev"

echo.
echo  ----------------------------------------------
echo   Application : http://localhost:5173
echo   API         : http://127.0.0.1:8000
echo   API docs    : http://127.0.0.1:8000/api/docs
echo   Health      : http://127.0.0.1:8000/health/ready
echo  ----------------------------------------------
echo   Close the two server windows to stop the app.
echo   Optional demo data:  backend\.venv\Scripts\python -m app.seed --email you@example.com  (run inside backend)
echo.
timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"
pause
exit /b 0

:startdb
echo [..] Starting PostgreSQL (docker compose service "db" on 127.0.0.1:5435)
docker compose up -d db || (echo [ERROR] Could not start the database container. & exit /b 1)
set /a TRIES=0
:waitdb
docker compose exec -T db pg_isready -U tenderpilot -d tenderpilot >nul 2>&1 && goto :dbready
set /a TRIES+=1
if %TRIES% GEQ 40 (echo [ERROR] PostgreSQL did not become ready in time. & exit /b 1)
timeout /t 2 /nobreak >nul
goto :waitdb
:dbready
echo [OK] PostgreSQL is ready
exit /b 0

:fail
echo.
echo Startup did not complete. Fix the error above and run "Start App.bat" again.
pause
exit /b 1
