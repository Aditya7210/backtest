#!/bin/bash
set -uo pipefail

# ===============================================================
# Algo Trading Launcher (macOS)
# - Uses saved project folder or asks once in Terminal
# - Terminal actions: Start/Update, Stop App, Change Project, Exit
# - Auto-stash compatibility before git pull
# ===============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_CONFIG="$HOME/.algo_trading_launcher_path"
LAUNCHER_LOG="$HOME/Library/Logs/AlgoTradingLauncher.log"
PROJECT_DIR=""
AUTO_STASH="no"
STASH_CREATED="no"

mkdir -p "$(dirname "$LAUNCHER_LOG")" >/dev/null 2>&1 || true

log_msg() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LAUNCHER_LOG"
}

show_error() {
  local msg="$1"
  local title="${2:-Launcher Error}"
  echo
  echo "ERROR: $title"
  echo "$msg"
  echo "See log: $LAUNCHER_LOG"
  log_msg "ERROR [$title] $msg"
  read -r -p "Press Enter to continue..." _
}

show_info() {
  local msg="$1"
  local title="${2:-Launcher}"
  echo
  echo "INFO: $title"
  echo "$msg"
  log_msg "INFO [$title] $msg"
  read -r -p "Press Enter to continue..." _
}

is_project_dir() {
  local d="${1:-}"
  [[ -n "$d" ]] || return 1
  [[ -f "$d/docker-compose.yml" && -f "$d/backend/main.py" ]]
}

try_project_dir() {
  local d="${1:-}"
  if is_project_dir "$d"; then
    PROJECT_DIR="$(cd "$d" && pwd)"
    return 0
  fi
  return 1
}

choose_project_folder() {
  local chosen=""
  echo
  echo "Enter the full Algo Trading project folder path."
  echo "It must contain docker-compose.yml and backend/main.py"
  read -r -p "Project folder: " chosen
  [[ -n "$chosen" ]] || return 1
  chosen="${chosen/#\~/$HOME}"
  try_project_dir "$chosen"
}

resolve_project_dir() {
  if [[ -n "${ALGO_TRADING_PROJECT_DIR:-}" ]]; then
    log_msg "Trying project folder from ALGO_TRADING_PROJECT_DIR."
    try_project_dir "$ALGO_TRADING_PROJECT_DIR" || true
  fi

  [[ -z "$PROJECT_DIR" ]] && try_project_dir "$SCRIPT_DIR" || true

  if [[ -z "$PROJECT_DIR" && -f "$LAUNCHER_CONFIG" ]]; then
    local saved
    saved="$(cat "$LAUNCHER_CONFIG" 2>/dev/null || true)"
    if [[ -n "$saved" ]]; then
      log_msg "Trying saved project folder: $saved"
      try_project_dir "$saved" || true
    fi
  fi
}

save_project_dir() {
  [[ -n "$PROJECT_DIR" ]] && printf '%s\n' "$PROJECT_DIR" > "$LAUNCHER_CONFIG"
}

ensure_env_file() {
  [[ -n "$PROJECT_DIR" ]] || return 0
  [[ -f "$PROJECT_DIR/.env" ]] && return 0
  [[ -f "$PROJECT_DIR/.env.example" ]] || return 0
  if cp -n "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env" >/dev/null 2>&1; then
    echo "Created .env from .env.example. Update credentials before running the app."
    log_msg "Created .env from .env.example."
  fi
}

sync_desktop_launcher() {
  local source="$PROJECT_DIR/Launch_Algo_Trading_mac.command"
  local target="$HOME/Desktop/Launch_Algo_Trading_mac.command"
  [[ -f "$source" ]] || return 0
  [[ -d "$HOME/Desktop" ]] || return 0
  [[ "$source" == "$target" ]] && return 0
  cp -f "$source" "$target" >/dev/null 2>&1 || return 0
  chmod +x "$target" >/dev/null 2>&1 || true
  echo "Desktop launcher synced: $target"
}

ensure_mac_permissions() {
  local target
  for target in "$PROJECT_DIR/compose-up.sh" "$PROJECT_DIR/Launch_Algo_Trading_mac.command"; do
    [[ -f "$target" ]] || continue
    chmod +x "$target" >/dev/null 2>&1 || true
  done
}

auto_stash_changes() {
  local before after
  before="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
  if ! git stash push -u -m "launcher-auto-stash $(date '+%Y-%m-%d %H:%M:%S')" >/dev/null 2>&1; then
    show_error "Auto-stash failed. Please stash or commit local changes manually." "Git Error"
    return 1
  fi
  after="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${after:-0}" -gt "${before:-0}" ]]; then
    STASH_CREATED="yes"
    echo "Auto-stashed local changes."
  fi
  return 0
}

wait_for_docker() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  echo "Docker not ready. Attempting to start Docker Desktop..."
  open -a Docker >/dev/null 2>&1 || true
  for _ in $(seq 1 180); do
    docker info >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

start_docker_flow() {
  local mode="${1:-start}"
  local force_build="${2:-no}"

  echo
  if [[ "$mode" == "update" ]]; then
    echo "[2/5] Verifying Docker..."
  else
    echo "[1/3] Verifying Docker..."
  fi
  if ! wait_for_docker; then
    show_error "Docker did not become ready within 3 minutes." "Docker Error"
    return
  fi
  echo "Docker is ready."

  echo
  if [[ "$mode" == "update" ]]; then
    echo "[3/5] Rebuilding and starting containers..."
  else
    echo "[2/3] Starting containers..."
  fi
  if [[ "$force_build" == "yes" ]]; then
    if ! docker compose up -d --build >/dev/null 2>&1; then
      show_error "docker compose up failed." "Docker Error"
      return
    fi
  elif ! docker compose up -d >/dev/null 2>&1; then
    if ! docker compose up -d --build >/dev/null 2>&1; then
      show_error "docker compose up failed." "Docker Error"
      return
    fi
  fi

  echo
  if [[ "$mode" == "update" ]]; then
    echo "[4/5] Waiting for Backend API health..."
  else
    echo "[3/3] Waiting for Backend API health..."
  fi
  local health_url="http://localhost:8000/api/health"
  for _ in $(seq 1 180); do
    if curl -fsS --max-time 3 "$health_url" >/dev/null 2>&1; then
      if [[ "$mode" == "update" ]]; then
        echo "[5/5] Backend API is healthy."
      else
        echo "Backend API is healthy."
      fi
      open "http://localhost:3000" >/dev/null 2>&1 || true
      show_info "App is running at http://localhost:3000"
      return
    fi
    sleep 1
  done

  show_error "Backend API health check timed out. Run: docker compose logs -f" "Startup Timeout"
}

start_app_flow() {
  command -v docker >/dev/null 2>&1 || { show_error "Docker CLI not found in PATH." "Missing Tool"; return; }
  command -v curl >/dev/null 2>&1 || { show_error "curl not found in PATH." "Missing Tool"; return; }

  ensure_mac_permissions
  start_docker_flow "start" "no"
}

update_flow() {
  command -v docker >/dev/null 2>&1 || { show_error "Docker CLI not found in PATH." "Missing Tool"; return; }
  command -v git >/dev/null 2>&1 || { show_error "Git not found in PATH." "Missing Tool"; return; }
  command -v curl >/dev/null 2>&1 || { show_error "curl not found in PATH." "Missing Tool"; return; }

  ensure_mac_permissions

  git rev-parse --is-inside-work-tree >/dev/null 2>&1
  if [[ "$?" -ne 0 ]]; then
    show_error "Selected folder is not a git repository." "Git Error"
    return
  fi

  echo
  echo "[1/5] Checking repository status..."
  local dirty="no"
  [[ -n "$(git status --porcelain 2>/dev/null)" ]] && dirty="yes"
  AUTO_STASH="no"
  STASH_CREATED="no"

  if [[ "$dirty" == "yes" ]]; then
    local reply=""
    echo
    echo "Uncommitted local changes detected."
    echo "Auto-stash will save local changes before pull and restore after pull."
    read -r -p "Continue with auto-stash? [Y/N]: " reply
    case "$reply" in
      y|Y|yes|YES) AUTO_STASH="yes" ;;
      *) echo "Update cancelled by user."; return ;;
    esac
  fi

  echo
  echo "[1/5] Fetching latest updates from GitHub..."
  if ! git fetch --all --prune; then
    show_error "git fetch failed." "Git Error"
    return
  fi

  local branch
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"

  if [[ "$dirty" == "yes" && "$AUTO_STASH" == "yes" ]]; then
    auto_stash_changes || return
  fi

  if ! git pull --ff-only origin "$branch"; then
    [[ "$STASH_CREATED" == "yes" ]] && echo "Your stash is still available: git stash list"
    show_error "git pull failed (non-fast-forward/conflict)." "Git Error"
    return
  fi

  if [[ "$STASH_CREATED" == "yes" ]]; then
    echo "Restoring auto-stashed changes..."
    if ! git stash pop >/dev/null 2>&1; then
      show_error "Stash restore had conflicts. Resolve manually with git stash list." "Git Warning"
    fi
  fi

  start_docker_flow "update" "yes"
}

stop_flow() {
  command -v docker >/dev/null 2>&1 || { show_error "Docker CLI not found in PATH." "Missing Tool"; return; }
  echo
  echo "Stopping containers..."
  if ! docker compose down >/dev/null 2>&1; then
    show_error "docker compose down failed." "Docker Error"
    return
  fi
  show_info "Algo Trading app stopped successfully."
}

menu_loop() {
  while true; do
    save_project_dir
    cd "$PROJECT_DIR" || {
      show_error "Failed to open project folder: $PROJECT_DIR" "Launcher Error"
      exit 1
    }

    echo
    echo "==============================================================="
    echo "ALGO TRADING LAUNCHER"
    echo "==============================================================="
    echo "Project: $PROJECT_DIR"
    echo
    echo "  1. Start App"
    echo "  2. Update App"
    echo "  3. Stop App"
    echo "  4. Change Project"
    echo "  5. Exit Launcher"
    echo
    read -r -p "Select action [1-5]: " action

    case "$action" in
      1) log_msg "Menu action selected: START"; start_app_flow ;;
      2) log_msg "Menu action selected: UPDATE"; update_flow ;;
      3) log_msg "Menu action selected: STOP"; stop_flow ;;
      4)
        log_msg "Menu action selected: CHANGE"
        PROJECT_DIR=""
        if choose_project_folder; then
          ensure_env_file
          save_project_dir
          sync_desktop_launcher
        else
          show_info "Project selection cancelled."
          resolve_project_dir
        fi
        ;;
      5) log_msg "Menu action selected: EXIT"; exit 0 ;;
      *) echo "Invalid action selected." ;;
    esac
  done
}

log_msg "Launcher started. Script=$0 CWD=$PWD"
resolve_project_dir
if [[ -z "$PROJECT_DIR" ]]; then
  choose_project_folder || true
fi
if [[ -z "$PROJECT_DIR" ]]; then
  show_error $'Could not find a valid project folder.\nRequired files:\n- docker-compose.yml\n- backend/main.py'
  exit 1
fi

log_msg "Using project folder: $PROJECT_DIR"
ensure_env_file
sync_desktop_launcher
menu_loop
