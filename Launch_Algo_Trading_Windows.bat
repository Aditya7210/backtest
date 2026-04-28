@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Algo Trading Launcher (Windows)

REM ---------------------------
REM Windows one-click launcher:
REM 1) Resolve project directory
REM 2) Pull latest from GitHub
REM 3) Ensure Docker is running
REM 4) Start docker compose
REM 5) Open Streamlit once healthy
REM ---------------------------

REM ---- Self-elevate to Administrator (best effort) ----
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting Administrator privileges...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "LAUNCHER_CONFIG=%USERPROFILE%\.algo_trading_launcher_path.txt"
set "PROJECT_DIR="

REM ---- Helper: validate project folder ----
set "CANDIDATE=%ALGO_TRADING_PROJECT_DIR%"
if not "%CANDIDATE%"=="" call :TryProject "%CANDIDATE%"
if not defined PROJECT_DIR call :TryProject "%~dp0"
if not defined PROJECT_DIR call :TryProject "%~dp0Algo_Trading_System"
if not defined PROJECT_DIR call :TryProject "%USERPROFILE%\PROJECTS\Algo_Trading_System"
if not defined PROJECT_DIR call :TryProject "%USERPROFILE%\Desktop\Algo_Trading_System"

if not defined PROJECT_DIR if exist "%LAUNCHER_CONFIG%" (
  set /p SAVED_DIR=<"%LAUNCHER_CONFIG%"
  if not "!SAVED_DIR!"=="" call :TryProject "!SAVED_DIR!"
)

if not defined PROJECT_DIR (
  echo Could not auto-detect project folder.
  set /p USER_DIR=Enter full path to Algo_Trading_System:
  call :TryProject "%USER_DIR%"
)

if not defined PROJECT_DIR (
  echo.
  echo ERROR: Invalid project path.
  echo Required files not found: docker-compose.yml and Dashboard\dashboard.py
  pause
  exit /b 1
)

> "%LAUNCHER_CONFIG%" echo %PROJECT_DIR%
echo Project directory: %PROJECT_DIR%
cd /d "%PROJECT_DIR%" || (echo ERROR: Failed to open project folder.& pause & exit /b 1)

REM ---- Check tools ----
where git >nul 2>&1 || (echo ERROR: git is not installed or not in PATH.& pause & exit /b 1)
where docker >nul 2>&1 || (echo ERROR: Docker CLI is not installed or not in PATH.& pause & exit /b 1)

REM ---- Pull latest updates ----
echo.
echo [1/4] Fetching latest updates from GitHub...
git rev-parse --is-inside-work-tree >nul 2>&1 || (echo ERROR: This folder is not a git repository.& pause & exit /b 1)
git fetch --all --prune || (echo ERROR: git fetch failed.& pause & exit /b 1)
for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%i"
if not defined CURRENT_BRANCH set "CURRENT_BRANCH=main"
git pull --ff-only origin %CURRENT_BRANCH%
if not "%errorlevel%"=="0" (
  echo.
  echo ERROR: git pull failed.
  echo This usually means local changes must be committed or stashed first.
  pause
  exit /b 1
)

REM ---- Ensure Docker daemon is ready ----
echo.
echo [2/4] Verifying Docker...
docker info >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Docker is not ready. Attempting to start Docker Desktop...
  if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  ) else if exist "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe" (
    start "" "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
  )

  for /l %%I in (1,1,180) do (
    docker info >nul 2>&1
    if "!errorlevel!"=="0" goto docker_ready
    timeout /t 1 >nul
  )
  echo ERROR: Docker did not become ready within timeout.
  pause
  exit /b 1
)

:docker_ready
echo Docker is ready.

REM ---- Start app via docker compose ----
echo.
echo [3/4] Starting containers...
docker compose up -d
if not "%errorlevel%"=="0" (
  echo docker compose up failed. Retrying with --build...
  docker compose up -d --build || (echo ERROR: docker compose failed.& pause & exit /b 1)
)

REM ---- Wait for Streamlit health ----
echo.
echo [4/4] Waiting for Streamlit health endpoint...
set "HEALTH_URL=http://localhost:8501/_stcore/health"

for /l %%I in (1,1,180) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '%HEALTH_URL%'; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if "!errorlevel!"=="0" goto streamlit_ready
  timeout /t 1 >nul
)

echo ERROR: Streamlit health check did not pass in time.
echo Check logs using: docker compose logs -f
pause
exit /b 1

:streamlit_ready
echo Streamlit is healthy. Opening browser...
start "" "http://localhost:8501"
echo Done.
exit /b 0

:TryProject
set "TRY_DIR=%~1"
if "%TRY_DIR%"=="" goto :eof
if exist "%TRY_DIR%\docker-compose.yml" if exist "%TRY_DIR%\Dashboard\dashboard.py" (
  set "PROJECT_DIR=%TRY_DIR%"
)
goto :eof

