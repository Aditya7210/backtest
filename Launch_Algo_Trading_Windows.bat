@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Algo Trading Launcher

REM ===============================================================
REM Algo Trading Launcher (Windows)
REM - Project folder name agnostic (marker-based detection)
REM - GUI actions: Start/Update, Stop App, Change Project, Exit
REM - Auto-stash compatibility before git pull
REM ===============================================================

REM ---- Self-elevate to Administrator ----
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting Administrator privileges...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "LAUNCHER_CONFIG=%USERPROFILE%\.algo_trading_launcher_path.txt"
set "PROJECT_DIR="
set "ACTION="
set "AUTO_STASH=0"
set "STASH_CREATED=0"
set "WORKTREE_DIRTY=0"

call :ResolveProjectDir
if not defined PROJECT_DIR (
  call :ChooseProjectFolder
)
if not defined PROJECT_DIR (
  call :ShowError "Could not find a valid project folder." "Project Not Found"
  exit /b 1
)

call :SyncDesktopLauncher

:menu_loop
call :SaveProjectDir
cd /d "%PROJECT_DIR%" || (
  call :ShowError "Failed to open project folder: %PROJECT_DIR%" "Launcher Error"
  exit /b 1
)

for /f "usebackq delims=" %%A in (
  `powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; ^
     $form=New-Object Windows.Forms.Form; ^
     $form.Text='Algo Trading Launcher'; ^
     $form.Size=New-Object Drawing.Size(560,320); ^
     $form.StartPosition='CenterScreen'; ^
     $form.FormBorderStyle='FixedDialog'; ^
     $form.MaximizeBox=$false; $form.MinimizeBox=$false; ^
     $form.BackColor=[Drawing.Color]::FromArgb(24,24,34); ^
     $title=New-Object Windows.Forms.Label; ^
     $title.Text='ALGO TRADING LAUNCHER'; ^
     $title.Font=New-Object Drawing.Font('Segoe UI',14,[Drawing.FontStyle]::Bold); ^
     $title.ForeColor=[Drawing.Color]::FromArgb(24,210,170); ^
     $title.AutoSize=$false; $title.TextAlign='MiddleCenter'; ^
     $title.Size=New-Object Drawing.Size(540,40); $title.Location=New-Object Drawing.Point(10,14); ^
     $subtitle=New-Object Windows.Forms.Label; ^
     $subtitle.Text='Choose an action'; ^
     $subtitle.Font=New-Object Drawing.Font('Segoe UI',9); ^
     $subtitle.ForeColor=[Drawing.Color]::FromArgb(180,180,200); ^
     $subtitle.AutoSize=$false; $subtitle.TextAlign='MiddleCenter'; ^
     $subtitle.Size=New-Object Drawing.Size(540,20); $subtitle.Location=New-Object Drawing.Point(10,56); ^
     $pathBox=New-Object Windows.Forms.TextBox; ^
     $pathBox.ReadOnly=$true; ^
     $pathBox.Text='Project: %PROJECT_DIR%'; ^
     $pathBox.Font=New-Object Drawing.Font('Segoe UI',8); ^
     $pathBox.BackColor=[Drawing.Color]::FromArgb(32,32,46); ^
     $pathBox.ForeColor=[Drawing.Color]::FromArgb(210,210,220); ^
     $pathBox.BorderStyle='FixedSingle'; ^
     $pathBox.Size=New-Object Drawing.Size(520,24); $pathBox.Location=New-Object Drawing.Point(18,84); ^
     $result='EXIT'; ^
     function New-ActionButton([string]$txt,[int]$x,[int]$y,[string]$tag,[Drawing.Color]$bg){ ^
       $b=New-Object Windows.Forms.Button; ^
       $b.Text=$txt; $b.Tag=$tag; ^
       $b.Size=New-Object Drawing.Size(240,54); ^
       $b.Location=New-Object Drawing.Point($x,$y); ^
       $b.Font=New-Object Drawing.Font('Segoe UI',10,[Drawing.FontStyle]::Bold); ^
       $b.BackColor=$bg; ^
       $b.ForeColor=[Drawing.Color]::White; ^
       $b.FlatStyle='Flat'; ^
       $b.FlatAppearance.BorderSize=0; ^
       $b.Add_Click({ $script:result=$this.Tag; $form.Close() }); ^
       return $b ^
     } ^
     $b1=New-ActionButton 'Start / Update App' 18 124 'START' ([Drawing.Color]::FromArgb(0,130,92)); ^
     $b2=New-ActionButton 'Stop App'           298 124 'STOP'  ([Drawing.Color]::FromArgb(170,52,52)); ^
     $b3=New-ActionButton 'Change Project'     18 194 'CHANGE' ([Drawing.Color]::FromArgb(58,90,170)); ^
     $b4=New-ActionButton 'Exit Launcher'      298 194 'EXIT'  ([Drawing.Color]::FromArgb(70,70,90)); ^
     $form.Controls.AddRange(@($title,$subtitle,$pathBox,$b1,$b2,$b3,$b4)); ^
     $form.Add_Shown({$form.Activate()}); ^
     [void]$form.ShowDialog(); ^
     $script:result"`
) do set "ACTION=%%A"

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
where docker >nul 2>&1 || (
  call :ShowError "Docker CLI not found in PATH." "Missing Tool"
  exit /b 1
)
where git >nul 2>&1 || (
  call :ShowError "Git not found in PATH." "Missing Tool"
  exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>&1 || (
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
  for /f "usebackq delims=" %%R in (
    `powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Add-Type -AssemblyName System.Windows.Forms; ^
       $r=[System.Windows.Forms.MessageBox]::Show('Uncommitted local changes detected.`n`nAuto-stash will save your local changes before pulling and restore them after pull.`n`nContinue?', 'Local Changes Detected', [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Warning); ^
       if($r -eq [System.Windows.Forms.DialogResult]::Yes){'YES'} else {'NO'}"`
  ) do set "STASH_REPLY=%%R"
  if /I "!STASH_REPLY!"=="YES" (
    set "AUTO_STASH=1"
  ) else (
    echo Update cancelled by user.
    goto menu_loop
  )
)

echo.
echo [1/5] Fetching latest updates from GitHub...
git fetch --all --prune || (
  call :ShowError "git fetch failed." "Git Error"
  goto menu_loop
)

for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%i"
if not defined CURRENT_BRANCH set "CURRENT_BRANCH=main"

if "%WORKTREE_DIRTY%"=="1" if "%AUTO_STASH%"=="1" (
  for /f %%I in ('git stash list ^| find /c /v ""') do set "STASH_BEFORE=%%I"
  if not defined STASH_BEFORE set "STASH_BEFORE=0"
  git stash push -u -m "launcher-auto-stash %DATE% %TIME%" >nul 2>&1
  for /f %%I in ('git stash list ^| find /c /v ""') do set "STASH_AFTER=%%I"
  if not defined STASH_AFTER set "STASH_AFTER=0"
  if !STASH_AFTER! GTR !STASH_BEFORE! (
    set "STASH_CREATED=1"
    echo Auto-stashed local changes.
  )
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
if not "%errorlevel%"=="0" (
  echo Docker not ready. Attempting to start Docker Desktop...
  for %%P in (
    "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
    "%LOCALAPPDATA%\Docker\Docker Desktop.exe"
  ) do (
    if exist "%%P" start "" "%%P"
  )
  for /l %%I in (1,1,180) do (
    docker info >nul 2>&1
    if "!errorlevel!"=="0" goto :docker_ready
    timeout /t 1 >nul
  )
  call :ShowError "Docker did not become ready within 3 minutes." "Docker Error"
  goto menu_loop
)

:docker_ready
echo Docker is ready.

echo.
echo [3/5] Starting containers...
docker compose up -d >nul 2>&1
if not "%errorlevel%"=="0" (
  docker compose up -d --build >nul 2>&1 || (
    call :ShowError "docker compose up failed." "Docker Error"
    goto menu_loop
  )
)

echo.
echo [4/5] Waiting for Streamlit health...
set "HEALTH_URL=http://localhost:8501/_stcore/health"
for /l %%I in (1,1,180) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '%HEALTH_URL%'; if($r.StatusCode -lt 500){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
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
where docker >nul 2>&1 || (
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
if not "%ALGO_TRADING_PROJECT_DIR%"=="" call :TryProject "%ALGO_TRADING_PROJECT_DIR%"
if not defined PROJECT_DIR call :TryProject "%~dp0"
if not defined PROJECT_DIR call :TryProject "%CD%"

if not defined PROJECT_DIR if exist "%LAUNCHER_CONFIG%" (
  set /p SAVED_DIR=<"%LAUNCHER_CONFIG%"
  if not "!SAVED_DIR!"=="" call :TryProject "!SAVED_DIR!"
)

if not defined PROJECT_DIR (
  for /f "usebackq delims=" %%P in (
    `powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$roots=@('%~dp0','%~dp0..',$env:USERPROFILE+'\Desktop',$env:USERPROFILE+'\Documents',$env:USERPROFILE+'\PROJECTS',$env:USERPROFILE+'\dev',$env:USERPROFILE+'\src','C:\Projects','C:\Dev','C:\src'); ^
       function Test-Proj([string]$p){ if(-not $p){return $false}; $p=[IO.Path]::GetFullPath($p); return (Test-Path (Join-Path $p 'docker-compose.yml')) -and (Test-Path (Join-Path $p 'Dashboard\dashboard.py')) }; ^
       function Scan-Level([string]$root,[int]$depth){ if(-not (Test-Path $root)){ return $null }; if(Test-Proj $root){ return (Resolve-Path $root).Path }; if($depth -le 0){ return $null }; $dirs=Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue; foreach($d in $dirs){ $r=Scan-Level $d.FullName ($depth-1); if($r){ return $r } }; return $null }; ^
       foreach($r in $roots){ $f=Scan-Level $r 2; if($f){ Write-Output $f; break } }"`
  ) do set "PROJECT_DIR=%%P"
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
for /f "usebackq delims=" %%P in (
  `powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Add-Type -AssemblyName System.Windows.Forms; ^
     $d=New-Object System.Windows.Forms.FolderBrowserDialog; ^
     $d.Description='Select your Algo Trading project folder (must contain docker-compose.yml)'; ^
     $d.ShowNewFolderButton=$false; ^
     if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}else{'CANCELLED'}"`
) do set "BROWSE_RESULT=%%P"
if /I not "%BROWSE_RESULT%"=="CANCELLED" call :TryProject "%BROWSE_RESULT%"
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
for /f "usebackq delims=" %%D in (
  `powershell -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::GetFolderPath('Desktop')"`
) do set "DESKTOP_DIR=%%D"
if not defined DESKTOP_DIR goto :eof

set "TARGET_LAUNCHER=%DESKTOP_DIR%\Launch_Algo_Trading_Windows.bat"
if /I "%SOURCE_LAUNCHER%"=="%TARGET_LAUNCHER%" goto :eof

copy /Y "%SOURCE_LAUNCHER%" "%TARGET_LAUNCHER%" >nul 2>&1
if "%errorlevel%"=="0" (
  echo Desktop launcher synced: "%TARGET_LAUNCHER%"
)
goto :eof

:ShowError
set "MSG=%~1"
set "TTL=%~2"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('%MSG%','%TTL%',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null"
goto :eof

:ShowInfo
set "MSG=%~1"
set "TTL=%~2"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('%MSG%','%TTL%',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null"
goto :eof
