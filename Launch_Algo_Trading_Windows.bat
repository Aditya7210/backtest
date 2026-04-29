@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Algo Trading Launcher

REM ---------------------------------------------------------------
REM Windows one-click launcher
REM 1) Resolve project directory (name-agnostic, scans common paths)
REM 2) Custom GUI: Start/Update  |  Stop  |  Exit
REM 3) Pull latest from GitHub (auto-stash only prompted if dirty)
REM 4) Ensure Docker is running
REM 5) Start/Stop docker compose
REM 6) Open Streamlit once healthy (start path)
REM ---------------------------------------------------------------

REM ---- Self-elevate to Administrator ----
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting Administrator privileges...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "LAUNCHER_CONFIG=%USERPROFILE%\.algo_trading_launcher_path.txt"
set "PROJECT_DIR="
set "ACTION="
set "AUTO_STASH=0"
set "STASH_CREATED=0"

REM ================================================================
REM  PROJECT DIRECTORY RESOLUTION
REM  Strategy (in order):
REM   1. Env var override
REM   2. Script's own directory
REM   3. Saved path from last run
REM   4. Scan subdirs of common locations (name-agnostic)
REM   5. Folder-browser dialog
REM ================================================================

REM -- 1. Env var override --
if not "%ALGO_TRADING_PROJECT_DIR%"=="" call :TryProject "%ALGO_TRADING_PROJECT_DIR%"

REM -- 2. Script's own dir (launcher placed inside the project) --
if not defined PROJECT_DIR call :TryProject "%~dp0"

REM -- 3. Saved path --
if not defined PROJECT_DIR if exist "%LAUNCHER_CONFIG%" (
  set /p SAVED_DIR=<"%LAUNCHER_CONFIG%"
  if not "!SAVED_DIR!"=="" call :TryProject "!SAVED_DIR!"
)

REM -- 4. Scan one level deep under common parent directories --
if not defined PROJECT_DIR (
  for %%B in (
    "%~dp0.."
    "%USERPROFILE%\PROJECTS"
    "%USERPROFILE%\Desktop"
    "%USERPROFILE%\Documents"
    "%USERPROFILE%"
    "C:\Projects"
    "C:\Dev"
    "C:\src"
  ) do (
    if not defined PROJECT_DIR (
      for /d %%S in ("%%~B\*") do (
        if not defined PROJECT_DIR call :TryProject "%%S"
      )
    )
  )
)

REM -- 5. Folder-browser dialog as last resort --
if not defined PROJECT_DIR (
  echo.
  echo Could not auto-detect the project folder.
  echo Please select it using the folder browser...
  for /f "usebackq delims=" %%P in (
    `powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Add-Type -AssemblyName System.Windows.Forms; $b=New-Object System.Windows.Forms.FolderBrowserDialog; $b.Description='Select your Algo Trading project folder (contains docker-compose.yml)'; $b.ShowNewFolderButton=$false; if($b.ShowDialog() -eq 'OK'){$b.SelectedPath} else {'CANCELLED'}"`)  do (
    set "BROWSE_RESULT=%%P"
  )
  if not "!BROWSE_RESULT!"=="CANCELLED" call :TryProject "!BROWSE_RESULT!"
)

if not defined PROJECT_DIR (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Could not find a valid project folder.`n`nRequired files:`n  docker-compose.yml`n  Dashboard\dashboard.py`n`nSet ALGO_TRADING_PROJECT_DIR env var or place the launcher inside the project.','Project Not Found',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Error)"
  exit /b 1
)

REM -- Save resolved path for next run --
>"#LAUNCHER_CONFIG#" echo !PROJECT_DIR!
set "LAUNCHER_CONFIG_WRITE=%LAUNCHER_CONFIG%"
>"!LAUNCHER_CONFIG_WRITE!" echo !PROJECT_DIR!

echo Project directory: !PROJECT_DIR!
cd /d "!PROJECT_DIR!" || (echo ERROR: Failed to cd into project folder. & pause & exit /b 1)

REM ================================================================
REM  MAIN GUI  –  custom WinForms dialog (no raw MessageBox)
REM ================================================================
for /f "usebackq delims=" %%A in (
  `powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; ^
     $f=New-Object System.Windows.Forms.Form; ^
     $f.Text='Algo Trading Launcher'; ^
     $f.Size=New-Object System.Drawing.Size(420,260); ^
     $f.StartPosition='CenterScreen'; ^
     $f.FormBorderStyle='FixedDialog'; ^
     $f.MaximizeBox=$false; $f.MinimizeBox=$false; ^
     $f.BackColor=[System.Drawing.Color]::FromArgb(18,18,28); ^
     $hdr=New-Object System.Windows.Forms.Label; ^
     $hdr.Text='ALGO TRADING LAUNCHER'; ^
     $hdr.Font=New-Object System.Drawing.Font('Segoe UI',13,[System.Drawing.FontStyle]::Bold); ^
     $hdr.ForeColor=[System.Drawing.Color]::FromArgb(0,210,180); ^
     $hdr.AutoSize=$false; $hdr.TextAlign='MiddleCenter'; ^
     $hdr.Size=New-Object System.Drawing.Size(420,45); ^
     $hdr.Location=New-Object System.Drawing.Point(0,12); ^
     $sub=New-Object System.Windows.Forms.Label; ^
     $sub.Text='Select an action to continue'; ^
     $sub.Font=New-Object System.Drawing.Font('Segoe UI',9); ^
     $sub.ForeColor=[System.Drawing.Color]::FromArgb(160,160,180); ^
     $sub.AutoSize=$false; $sub.TextAlign='MiddleCenter'; ^
     $sub.Size=New-Object System.Drawing.Size(420,22); ^
     $sub.Location=New-Object System.Drawing.Point(0,56); ^
     $result='EXIT'; ^
     $mkBtn={ param($txt,$desc,$x,$clr) ^
       $p=New-Object System.Windows.Forms.Panel; ^
       $p.Size=New-Object System.Drawing.Size(108,80); ^
       $p.Location=New-Object System.Drawing.Point($x,95); ^
       $p.BackColor=$clr; $p.Cursor='Hand'; ^
       $lbl=New-Object System.Windows.Forms.Label; ^
       $lbl.Text=$txt; ^
       $lbl.Font=New-Object System.Drawing.Font('Segoe UI',10,[System.Drawing.FontStyle]::Bold); ^
       $lbl.ForeColor=[System.Drawing.Color]::White; ^
       $lbl.AutoSize=$false; $lbl.TextAlign='MiddleCenter'; ^
       $lbl.Size=New-Object System.Drawing.Size(108,30); ^
       $lbl.Location=New-Object System.Drawing.Point(0,10); ^
       $d=New-Object System.Windows.Forms.Label; ^
       $d.Text=$desc; ^
       $d.Font=New-Object System.Drawing.Font('Segoe UI',7.5); ^
       $d.ForeColor=[System.Drawing.Color]::FromArgb(220,220,220); ^
       $d.AutoSize=$false; $d.TextAlign='MiddleCenter'; ^
       $d.Size=New-Object System.Drawing.Size(108,28); ^
       $d.Location=New-Object System.Drawing.Point(0,40); ^
       $p.Controls.AddRange(@($lbl,$d)); ^
       return $p }; ^
     $bStart=&$mkBtn 'START / UPDATE' 'Pull + launch app' 30 ([System.Drawing.Color]::FromArgb(0,140,100)); ^
     $bStop =&$mkBtn 'STOP'           'Shut down containers' 156 ([System.Drawing.Color]::FromArgb(180,50,50)); ^
     $bExit =&$mkBtn 'EXIT'           'Close this launcher' 282 ([System.Drawing.Color]::FromArgb(60,60,80)); ^
     $act={param($v) $script:result=$v; $f.Close()}; ^
     foreach($ctrl in $bStart.Controls){ $ctrl.Add_Click({&$act 'START'}) }; $bStart.Add_Click({&$act 'START'}); ^
     foreach($ctrl in $bStop.Controls) { $ctrl.Add_Click({&$act 'STOP' }) }; $bStop.Add_Click( {&$act 'STOP' }); ^
     foreach($ctrl in $bExit.Controls) { $ctrl.Add_Click({&$act 'EXIT' }) }; $bExit.Add_Click( {&$act 'EXIT' }); ^
     $proj=New-Object System.Windows.Forms.Label; ^
     $proj.Text='Project: ' + '!PROJECT_DIR!'; ^
     $proj.Font=New-Object System.Drawing.Font('Segoe UI',7.5); ^
     $proj.ForeColor=[System.Drawing.Color]::FromArgb(120,120,140); ^
     $proj.AutoSize=$false; $proj.TextAlign='MiddleCenter'; ^
     $proj.Size=New-Object System.Drawing.Size(400,18); ^
     $proj.Location=New-Object System.Drawing.Point(10,200); ^
     $f.Controls.AddRange(@($hdr,$sub,$bStart,$bStop,$bExit,$proj)); ^
     $f.Add_Shown({$f.Activate()}); ^
     [void]$f.ShowDialog(); ^
     $script:result"`) do set "ACTION=%%A"

if /I "%ACTION%"=="EXIT" exit /b 0
if /I not "%ACTION%"=="START" if /I not "%ACTION%"=="STOP" (
  echo ERROR: No valid action selected.
  pause
  exit /b 1
)

REM ================================================================
REM  TOOL CHECKS
REM ================================================================
where docker >nul 2>&1 || (
  echo ERROR: Docker CLI not found in PATH.
  pause & exit /b 1
)
if /I "%ACTION%"=="START" (
  where git >nul 2>&1 || (
    echo ERROR: git not found in PATH.
    pause & exit /b 1
  )
)

if /I "%ACTION%"=="STOP" goto stop_app

REM ================================================================
REM  START / UPDATE PATH
REM ================================================================

REM ---- Git sanity check ----
git rev-parse --is-inside-work-tree >nul 2>&1 || (
  echo ERROR: Project folder is not a git repository.
  pause & exit /b 1
)

REM ---- Check dirty state BEFORE asking about stash ----
echo.
echo [1/5] Checking repository status...
set "WORKTREE_DIRTY=0"
for /f "tokens=*" %%I in ('git status --porcelain 2^>nul') do set "WORKTREE_DIRTY=1"

if "!WORKTREE_DIRTY!"=="1" (
  REM Only now ask about auto-stash (dirty tree detected)
  for /f "usebackq delims=" %%A in (
    `powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; ^
       $f=New-Object System.Windows.Forms.Form; ^
       $f.Text='Local Changes Detected'; ^
       $f.Size=New-Object System.Drawing.Size(400,200); ^
       $f.StartPosition='CenterScreen'; ^
       $f.FormBorderStyle='FixedDialog'; ^
       $f.MaximizeBox=$false; $f.MinimizeBox=$false; ^
       $f.BackColor=[System.Drawing.Color]::FromArgb(25,25,38); ^
       $ico=New-Object System.Windows.Forms.Label; ^
       $ico.Text='⚠  Uncommitted local changes found'; ^
       $ico.Font=New-Object System.Drawing.Font('Segoe UI',10,[System.Drawing.FontStyle]::Bold); ^
       $ico.ForeColor=[System.Drawing.Color]::FromArgb(255,190,0); ^
       $ico.AutoSize=$false; $ico.TextAlign='MiddleCenter'; ^
       $ico.Size=New-Object System.Drawing.Size(380,36); $ico.Location=New-Object System.Drawing.Point(10,12); ^
       $msg=New-Object System.Windows.Forms.Label; ^
       $msg.Text='Auto-stash will save your changes before pulling`nand restore them afterward.'; ^
       $msg.Font=New-Object System.Drawing.Font('Segoe UI',9); ^
       $msg.ForeColor=[System.Drawing.Color]::FromArgb(190,190,200); ^
       $msg.AutoSize=$false; $msg.TextAlign='MiddleCenter'; ^
       $msg.Size=New-Object System.Drawing.Size(380,40); $msg.Location=New-Object System.Drawing.Point(10,50); ^
       $result='ABORT'; ^
       $bY=New-Object System.Windows.Forms.Button; ^
       $bY.Text='Auto-Stash && Continue'; ^
       $bY.Size=New-Object System.Drawing.Size(160,34); $bY.Location=New-Object System.Drawing.Point(30,108); ^
       $bY.BackColor=[System.Drawing.Color]::FromArgb(0,130,100); $bY.ForeColor=[System.Drawing.Color]::White; ^
       $bY.FlatStyle='Flat'; $bY.Add_Click({$script:result='YES'; $f.Close()}); ^
       $bN=New-Object System.Windows.Forms.Button; ^
       $bN.Text='Abort Update'; ^
       $bN.Size=New-Object System.Drawing.Size(140,34); $bN.Location=New-Object System.Drawing.Point(210,108); ^
       $bN.BackColor=[System.Drawing.Color]::FromArgb(140,40,40); $bN.ForeColor=[System.Drawing.Color]::White; ^
       $bN.FlatStyle='Flat'; $bN.Add_Click({$script:result='NO'; $f.Close()}); ^
       $f.Controls.AddRange(@($ico,$msg,$bY,$bN)); ^
       $f.Add_Shown({$f.Activate()}); ^
       [void]$f.ShowDialog(); $script:result"`) do set "STASH_REPLY=%%A"

  if /I "!STASH_REPLY!"=="YES" (
    set "AUTO_STASH=1"
  ) else (
    echo Update aborted. Resolve local changes manually and re-run.
    pause & exit /b 0
  )
)

REM ---- Pull latest ----
echo.
echo [1/5] Fetching latest updates from GitHub...
git fetch --all --prune || (echo ERROR: git fetch failed. & pause & exit /b 1)

for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%i"
if not defined CURRENT_BRANCH set "CURRENT_BRANCH=main"

if "!WORKTREE_DIRTY!"=="1" if "!AUTO_STASH!"=="1" (
  for /f %%I in ('git stash list ^| find /c /v ""') do set "STASH_BEFORE=%%I"
  git stash push -u -m "launcher-auto-stash %DATE% %TIME%" >nul 2>&1
  for /f %%I in ('git stash list ^| find /c /v ""') do set "STASH_AFTER=%%I"
  if not defined STASH_BEFORE set "STASH_BEFORE=0"
  if not defined STASH_AFTER  set "STASH_AFTER=0"
  if !STASH_AFTER! GTR !STASH_BEFORE! (
    set "STASH_CREATED=1"
    echo Auto-stashed local changes.
  )
)

git pull --ff-only origin !CURRENT_BRANCH!
if not "%errorlevel%"=="0" (
  echo.
  echo ERROR: git pull failed ^(possible merge conflict or non-fast-forward^).
  if "!STASH_CREATED!"=="1" echo Your stash is intact. Run: git stash list
  pause & exit /b 1
)

if "!STASH_CREATED!"=="1" (
  echo Restoring auto-stashed changes...
  git stash pop >nul 2>&1
  if not "%errorlevel%"=="0" (
    echo WARNING: Stash pop had conflicts. Resolve manually ^(git stash list^).
  )
)

REM ================================================================
REM  DOCKER
REM ================================================================
echo.
echo [2/5] Verifying Docker...
docker info >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Docker not ready — attempting to start Docker Desktop...
  for %%P in (
    "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
    "%LOCALAPPDATA%\Docker\Docker Desktop.exe"
  ) do (
    if exist "%%P" start "" "%%P" & goto docker_wait
  )
  :docker_wait
  for /l %%I in (1,1,180) do (
    docker info >nul 2>&1
    if "!errorlevel!"=="0" goto docker_ready
    timeout /t 1 >nul
  )
  echo ERROR: Docker did not become ready within 3 minutes.
  pause & exit /b 1
)
:docker_ready
echo Docker is ready.

REM ================================================================
REM  CONTAINERS
REM ================================================================
echo.
echo [3/5] Starting containers...
docker compose up -d
if not "%errorlevel%"=="0" (
  echo Retrying with --build...
  docker compose up -d --build || (echo ERROR: docker compose up failed. & pause & exit /b 1)
)

REM ================================================================
REM  HEALTH CHECK
REM ================================================================
echo.
echo [4/5] Waiting for Streamlit to become healthy...
set "HEALTH_URL=http://localhost:8501/_stcore/health"

for /l %%I in (1,1,180) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '%HEALTH_URL%'; if($r.StatusCode -lt 500){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
  if "!errorlevel!"=="0" goto streamlit_ready
  timeout /t 1 >nul
)
echo ERROR: Streamlit health check timed out.
echo Run: docker compose logs -f
pause & exit /b 1

:streamlit_ready
echo [5/5] Streamlit is healthy. Opening browser...
start "" "http://localhost:8501"
echo.
echo All done. App is running at http://localhost:8501
exit /b 0

REM ================================================================
REM  STOP PATH
REM ================================================================
:stop_app
echo.
echo Stopping containers...
docker compose down
if not "%errorlevel%"=="0" (
  echo ERROR: docker compose down failed.
  pause & exit /b 1
)
echo App stopped successfully.
exit /b 0

REM ================================================================
REM  SUBROUTINE: validate a candidate project folder
REM  Requires:  docker-compose.yml  AND  Dashboard\dashboard.py
REM ================================================================
:TryProject
set "TRY_DIR=%~1"
if "%TRY_DIR%"=="" goto :eof
if exist "%TRY_DIR%\docker-compose.yml" if exist "%TRY_DIR%\Dashboard\dashboard.py" (
  set "PROJECT_DIR=%TRY_DIR%"
)
goto :eof