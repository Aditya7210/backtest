@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Algo Trading Launcher

set "LAUNCHER_LOG=%TEMP%\AlgoTradingLauncher.log"
call :Log "Launcher started. Script=%~f0 Args=%* CWD=%CD%"

set "LAUNCHER_CONFIG=%USERPROFILE%\.algo_trading_launcher_path.txt"
set "PROJECT_DIR="
set "ACTION="
set "AUTO_STASH=0"
set "STASH_CREATED=0"
set "WORKTREE_DIRTY=0"

REM ===============================================================
REM Algo Trading Launcher (Windows)
REM - Project folder name agnostic (marker-based detection)
REM - GUI actions: Start/Update, Stop App, Change Project, Exit
REM - Auto-stash compatibility before git pull
REM ===============================================================

REM ---- Self-elevate to Administrator ----
net session >nul 2>&1
if "%errorlevel%"=="0" goto :admin_ready

echo Requesting Administrator privileges...
call :Log "Requesting Administrator privileges."
set "ELEVATED_WORKDIR=%~dp0"
set "ELEVATED_TARGET=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $q=[char]34; $arg='/d /k call ' + $q + $env:ELEVATED_TARGET + $q + ' --elevated'; Start-Process -FilePath $env:ComSpec -ArgumentList $arg -WorkingDirectory $env:ELEVATED_WORKDIR -Verb RunAs"
if "%errorlevel%"=="0" exit /b

echo Failed to request Administrator privileges.
echo See log: %LAUNCHER_LOG%
call :Log "Administrator elevation request failed."
pause
exit /b 1

:admin_ready
if /I "%~1"=="--elevated" shift
call :Log "Running with Administrator privileges."

call :ResolveProjectDir
if not defined PROJECT_DIR (
  call :Log "Project folder was not resolved automatically; opening folder picker."
  call :ChooseProjectFolder
)
if not defined PROJECT_DIR (
  call :Log "Project folder could not be resolved."
  call :ShowError "Could not find a valid project folder." "Project Not Found"
  exit /b 1
)
call :Log "Using project folder: %PROJECT_DIR%"

call :SyncDesktopLauncher

:menu_loop
call :SaveProjectDir
cd /d "%PROJECT_DIR%"
if not "%errorlevel%"=="0" (
  call :ShowError "Failed to open project folder: %PROJECT_DIR%" "Launcher Error"
  exit /b 1
)

echo.
echo ===============================================================
echo ALGO TRADING LAUNCHER
echo ===============================================================
echo Project: %PROJECT_DIR%
echo.
echo   1. Start / Update App
echo   2. Stop App
echo   3. Change Project
echo   4. Exit Launcher
echo.
choice /c 1234 /n /m "Select action [1-4]: "
set "ACTION=EXIT"
if "%errorlevel%"=="1" set "ACTION=START"
if "%errorlevel%"=="2" set "ACTION=STOP"
if "%errorlevel%"=="3" set "ACTION=CHANGE"
if "%errorlevel%"=="4" set "ACTION=EXIT"

call :Log "Menu action selected: %ACTION%"

if /I "%ACTION%"=="EXIT" exit /b 0
if /I "%ACTION%"=="CHANGE" (
  call :ChooseProjectFolder
  if defined PROJECT_DIR (
    call :SyncDesktopLauncher
    goto menu_loop
  )
  call :ShowError "No project folder selected." "Launcher"
  goto menu_loop
)
if /I "%ACTION%"=="STOP" goto :stop_app
if /I "%ACTION%"=="START" goto :start_app

call :ShowError "Invalid action selected." "Launcher Error"
exit /b 1

:start_app
where docker >nul 2>&1
if not "%errorlevel%"=="0" (
  call :ShowError "Docker CLI not found in PATH." "Missing Tool"
  exit /b 1
)
where git >nul 2>&1
if not "%errorlevel%"=="0" (
  call :ShowError "Git not found in PATH." "Missing Tool"
  exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>&1
if not "%errorlevel%"=="0" (
  call :ShowError "Project folder is not a git repository." "Git Error"
  goto menu_loop
)

echo.
echo [1/5] Checking repository status...
set "WORKTREE_DIRTY=0"
for /f "tokens=*" %%I in ('git status --porcelain 2^>nul') do set "WORKTREE_DIRTY=1"

set "AUTO_STASH=0"
set "STASH_CREATED=0"
if "%WORKTREE_DIRTY%"=="1" (
  echo.
  echo Uncommitted local changes detected.
  echo Auto-stash will save your local changes before pulling and restore them after pull.
  choice /c YN /n /m "Continue with auto-stash? [Y/N]: "
  if "!errorlevel!"=="1" set "AUTO_STASH=1"
  if "!errorlevel!"=="2" (
    echo Update cancelled by user.
    goto menu_loop
  )
)

echo.
echo [1/5] Fetching latest updates from GitHub...
git fetch --all --prune
if not "%errorlevel%"=="0" (
  call :ShowError "git fetch failed." "Git Error"
  goto menu_loop
)

for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%i"
if not defined CURRENT_BRANCH set "CURRENT_BRANCH=main"

set "AUTO_STASH_FAILED=0"
if "%WORKTREE_DIRTY%"=="1" if "%AUTO_STASH%"=="1" call :AutoStashChanges
if "%AUTO_STASH_FAILED%"=="1" (
  call :ShowError "Auto-stash failed. Please stash or commit local changes manually." "Git Error"
  goto menu_loop
)

git pull --ff-only origin !CURRENT_BRANCH!
if not "%errorlevel%"=="0" (
  if "%STASH_CREATED%"=="1" echo Your stash is safe. Run: git stash list
  call :ShowError "git pull failed (non-fast-forward/conflict)." "Git Error"
  goto menu_loop
)

if "%STASH_CREATED%"=="1" (
  echo Restoring auto-stashed changes...
  git stash pop >nul 2>&1
  if not "%errorlevel%"=="0" (
    call :ShowError "Stash restore had conflicts. Please resolve manually." "Git Warning"
  )
)

echo.
echo [2/5] Verifying Docker...
docker info >nul 2>&1
if "%errorlevel%"=="0" goto :docker_ready
  echo Docker not ready. Attempting to start Docker Desktop...
  call :StartDockerDesktop
  for /l %%I in (1,1,180) do (
    docker info >nul 2>&1
    if "!errorlevel!"=="0" goto :docker_ready
    timeout /t 1 >nul
  )
  call :ShowError "Docker did not become ready within 3 minutes." "Docker Error"
  goto menu_loop

:docker_ready
echo Docker is ready.

echo.
echo [3/5] Starting containers...
docker compose up -d >nul 2>&1
if "%errorlevel%"=="0" goto :compose_started
docker compose up -d --build >nul 2>&1
if not "%errorlevel%"=="0" (
  call :ShowError "docker compose up failed." "Docker Error"
  goto menu_loop
)
:compose_started

echo.
echo [4/5] Waiting for Streamlit health...
set "HEALTH_URL=http://localhost:8501/_stcore/health"
for /l %%I in (1,1,180) do (
  curl.exe -fsS "%HEALTH_URL%" >nul 2>&1
  if "!errorlevel!"=="0" goto :streamlit_ready
  timeout /t 1 >nul
)
call :ShowError "Streamlit health check timed out. Run: docker compose logs -f" "Startup Timeout"
goto menu_loop

:streamlit_ready
echo [5/5] Streamlit is healthy. Opening browser...
start "" "http://localhost:8501"
call :ShowInfo "App is running at http://localhost:8501" "Launcher"
goto menu_loop

:stop_app
where docker >nul 2>&1
if not "%errorlevel%"=="0" (
  call :ShowError "Docker CLI not found in PATH." "Missing Tool"
  goto menu_loop
)
echo.
echo Stopping containers...
docker compose down >nul 2>&1
if not "%errorlevel%"=="0" (
  call :ShowError "docker compose down failed." "Docker Error"
  goto menu_loop
)
call :ShowInfo "Algo Trading app stopped successfully." "Launcher"
goto menu_loop

REM ===============================================================
REM Helpers
REM ===============================================================
:ResolveProjectDir
if not "%ALGO_TRADING_PROJECT_DIR%"=="" (
  call :Log "Trying project folder from ALGO_TRADING_PROJECT_DIR."
  call :TryProject "%ALGO_TRADING_PROJECT_DIR%"
)

if not defined PROJECT_DIR call :TryProject "%~dp0"

if not defined PROJECT_DIR if exist "%LAUNCHER_CONFIG%" (
  set /p SAVED_DIR=<"%LAUNCHER_CONFIG%"
  if not "!SAVED_DIR!"=="" (
    call :Log "Trying saved project folder: !SAVED_DIR!"
    call :TryProject "!SAVED_DIR!"
  )
)
goto :eof

:TryProject
set "TRY_DIR=%~1"
if "%TRY_DIR%"=="" goto :eof
if exist "%TRY_DIR%\docker-compose.yml" if exist "%TRY_DIR%\Dashboard\dashboard.py" (
  for %%F in ("%TRY_DIR%") do set "PROJECT_DIR=%%~fF"
)
goto :eof

:ChooseProjectFolder
set "BROWSE_RESULT="
echo.
echo Enter the full Algo Trading project folder path.
echo It must contain docker-compose.yml and Dashboard\dashboard.py
set /p "BROWSE_RESULT=Project folder: "
if not "%BROWSE_RESULT%"=="" call :TryProject "%BROWSE_RESULT%"
goto :eof

:SaveProjectDir
if defined PROJECT_DIR (
  >"%LAUNCHER_CONFIG%" echo %PROJECT_DIR%
)
goto :eof

:SyncDesktopLauncher
if not defined PROJECT_DIR goto :eof
set "SOURCE_LAUNCHER=%PROJECT_DIR%\Launch_Algo_Trading_Windows.bat"
if not exist "%SOURCE_LAUNCHER%" goto :eof

set "DESKTOP_DIR="
if exist "%USERPROFILE%\OneDrive\Desktop" set "DESKTOP_DIR=%USERPROFILE%\OneDrive\Desktop"
if not defined DESKTOP_DIR if exist "%USERPROFILE%\Desktop" set "DESKTOP_DIR=%USERPROFILE%\Desktop"
if not defined DESKTOP_DIR goto :eof

set "TARGET_LAUNCHER=%DESKTOP_DIR%\Launch_Algo_Trading_Windows.bat"
if /I "%SOURCE_LAUNCHER%"=="%TARGET_LAUNCHER%" goto :eof

copy /Y "%SOURCE_LAUNCHER%" "%TARGET_LAUNCHER%" >nul 2>&1
if "%errorlevel%"=="0" (
  echo Desktop launcher synced: "%TARGET_LAUNCHER%"
)
goto :eof

:AutoStashChanges
set "AUTO_STASH_FAILED=0"
set "STASH_BEFORE=0"
set "STASH_AFTER=0"
for /f %%I in ('git stash list ^| find /c /v ""') do set "STASH_BEFORE=%%I"
git stash push -u -m "launcher-auto-stash %DATE% %TIME%" >nul 2>&1
if not "%errorlevel%"=="0" (
  set "AUTO_STASH_FAILED=1"
  goto :eof
)
for /f %%I in ('git stash list ^| find /c /v ""') do set "STASH_AFTER=%%I"
if !STASH_AFTER! GTR !STASH_BEFORE! (
  set "STASH_CREATED=1"
  echo Auto-stashed local changes.
)
goto :eof

:StartDockerDesktop
set "DOCKER_DESKTOP_PATH=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if exist "%DOCKER_DESKTOP_PATH%" start "" "%DOCKER_DESKTOP_PATH%"
set "DOCKER_DESKTOP_PATH=%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
if exist "%DOCKER_DESKTOP_PATH%" start "" "%DOCKER_DESKTOP_PATH%"
set "DOCKER_DESKTOP_PATH=%LOCALAPPDATA%\Docker\Docker Desktop.exe"
if exist "%DOCKER_DESKTOP_PATH%" start "" "%DOCKER_DESKTOP_PATH%"
goto :eof

:ShowError
set "MSG=%~1"
set "TTL=%~2"
call :Log "ERROR [%TTL%] %MSG%"
echo.
echo ERROR: %TTL%
echo %MSG%
echo See log: %LAUNCHER_LOG%
pause
goto :eof

:ShowInfo
set "MSG=%~1"
set "TTL=%~2"
call :Log "INFO [%TTL%] %MSG%"
echo.
echo INFO: %TTL%
echo %MSG%
pause
goto :eof

:Log
set "LOG_MSG=%~1"
>>"%LAUNCHER_LOG%" echo [%DATE% %TIME%] %LOG_MSG%
goto :eof
