#!/bin/bash
set -euo pipefail

# ===============================================================
# Algo Trading Launcher (macOS)
# - Project folder name agnostic (marker-based detection)
# - GUI actions: Start/Update, Stop App, Change Project, Exit
# - Auto-stash compatibility before git pull
# ===============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_CONFIG="$HOME/.algo_trading_launcher_path"
PROJECT_DIR=""
AUTO_STASH="no"
STASH_CREATED="no"

is_project_dir() {
  local d="${1:-}"
  [[ -n "$d" ]] || return 1
  [[ -f "$d/docker-compose.yml" && -f "$d/Dashboard/dashboard.py" ]]
}

try_project_dir() {
  local d="${1:-}"
  if is_project_dir "$d"; then
    PROJECT_DIR="$(cd "$d" && pwd)"
    return 0
  fi
  return 1
}

scan_candidates() {
  local root="${1:-}"
  [[ -d "$root" ]] || return 1

  if is_project_dir "$root"; then
    echo "$(cd "$root" && pwd)"
    return 0
  fi

  while IFS= read -r -d '' d1; do
    if is_project_dir "$d1"; then
      echo "$(cd "$d1" && pwd)"
      return 0
    fi
    while IFS= read -r -d '' d2; do
      if is_project_dir "$d2"; then
        echo "$(cd "$d2" && pwd)"
        return 0
      fi
    done < <(find "$d1" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)
  done < <(find "$root" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)
  return 1
}

choose_project_folder() {
  local chosen=""
  chosen="$(osascript <<'OSA' 2>/dev/null || true
set picked to choose folder with prompt "Select your Algo Trading project folder (must contain docker-compose.yml):"
return POSIX path of picked
OSA
)"
  chosen="${chosen%/}"
  [[ -n "$chosen" ]] || return 1
  try_project_dir "$chosen"
}

show_error() {
  local msg="$1"
  local title="${2:-Launcher Error}"
  osascript -e "display dialog \"$msg\" buttons {\"OK\"} default button \"OK\" with title \"$title\" with icon stop" >/dev/null 2>&1 || true
}

show_info() {
  local msg="$1"
  local title="${2:-Launcher}"
  osascript -e "display dialog \"$msg\" buttons {\"OK\"} default button \"OK\" with title \"$title\" with icon note" >/dev/null 2>&1 || true
}

ensure_mac_permissions() {
  local target
  for target in "$PROJECT_DIR/compose-up.sh" "$PROJECT_DIR/entrypoint.sh"; do
    [[ -f "$target" ]] || continue
    chmod +x "$target" >/dev/null 2>&1 || true
  done
}

resolve_project_dir() {
  if [[ -n "${ALGO_TRADING_PROJECT_DIR:-}" ]]; then
    try_project_dir "$ALGO_TRADING_PROJECT_DIR" || true
  fi

  [[ -z "$PROJECT_DIR" ]] && try_project_dir "$SCRIPT_DIR" || true
  [[ -z "$PROJECT_DIR" ]] && try_project_dir "$PWD" || true

  if [[ -z "$PROJECT_DIR" && -f "$LAUNCHER_CONFIG" ]]; then
    local saved
    saved="$(cat "$LAUNCHER_CONFIG" 2>/dev/null || true)"
    [[ -n "$saved" ]] && try_project_dir "$saved" || true
  fi

  if [[ -z "$PROJECT_DIR" ]]; then
    local roots=(
      "$SCRIPT_DIR"
      "$SCRIPT_DIR/.."
      "$HOME/Desktop"
      "$HOME/Documents"
      "$HOME/PROJECTS"
      "$HOME/dev"
      "$HOME/src"
      "$HOME"
    )
    local found=""
    for r in "${roots[@]}"; do
      found="$(scan_candidates "$r" || true)"
      if [[ -n "$found" ]]; then
        PROJECT_DIR="$found"
        break
      fi
    done
  fi
}

resolve_project_dir
if [[ -z "$PROJECT_DIR" ]]; then
  choose_project_folder || true
fi
if [[ -z "$PROJECT_DIR" ]]; then
  show_error "Could not find a valid project folder.\n\nRequired files:\n- docker-compose.yml\n- Dashboard/dashboard.py"
  exit 1
fi

sync_desktop_launcher() {
  local source="$PROJECT_DIR/Launch_Algo_Trading_mac.command"
  local target="$HOME/Desktop/Launch_Algo_Trading_mac.command"
  [[ -f "$source" ]] || return 0
  [[ "$source" == "$target" ]] && return 0
  cp -f "$source" "$target" >/dev/null 2>&1 || return 0
  chmod +x "$target" >/dev/null 2>&1 || true
  echo "Desktop launcher synced: $target"
}

sync_desktop_launcher

menu_loop() {
  echo "$PROJECT_DIR" > "$LAUNCHER_CONFIG"
  cd "$PROJECT_DIR"

  local project_name
  project_name="$(basename "$PROJECT_DIR")"
  local action
  action="$(osascript <<OSA 2>/dev/null || echo "Exit Launcher"
set msgText to "Project: $project_name" & return & "$PROJECT_DIR" & return & return & "Choose an action:"
tell application "System Events"
  set pressed to button returned of (display dialog msgText buttons {"Exit Launcher", "Change Project", "Stop App", "Start / Update App"} default button "Start / Update App" cancel button "Exit Launcher" with title "Algo Trading Launcher" with icon note)
  return pressed
end tell
OSA
)"

  case "$action" in
    "Start / Update App") start_update_flow ;;
    "Stop App") stop_flow ;;
    "Change Project")
      if choose_project_folder; then
        echo "$PROJECT_DIR" > "$LAUNCHER_CONFIG"
        sync_desktop_launcher
      else
        show_info "Project selection cancelled."
      fi
      ;;
    *) exit 0 ;;
  esac

  menu_loop
}

start_update_flow() {
  command -v docker >/dev/null 2>&1 || { show_error "Docker CLI not found in PATH." "Missing Tool"; return; }
  command -v git >/dev/null 2>&1 || { show_error "Git not found in PATH." "Missing Tool"; return; }
  command -v curl >/dev/null 2>&1 || { show_error "curl not found in PATH." "Missing Tool"; return; }

  ensure_mac_permissions

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    show_error "Selected folder is not a git repository." "Git Error"
    return
  }

  echo "[1/5] Checking repository status..."
  local dirty="no"
  [[ -n "$(git status --porcelain 2>/dev/null)" ]] && dirty="yes"
  AUTO_STASH="no"
  STASH_CREATED="no"

  if [[ "$dirty" == "yes" ]]; then
    local stash_answer
    stash_answer="$(osascript <<'OSA' 2>/dev/null || echo "Abort Update"
tell application "System Events"
  set pressed to button returned of (display dialog "Uncommitted local changes detected.\n\nAuto-stash will save local changes before pull and restore after pull.\n\nContinue?" buttons {"Abort Update", "Auto-Stash & Continue"} default button "Auto-Stash & Continue" cancel button "Abort Update" with title "Local Changes Detected" with icon caution)
  return pressed
end tell
OSA
)"
    if [[ "$stash_answer" == "Auto-Stash & Continue" ]]; then
      AUTO_STASH="yes"
    else
      echo "Update cancelled by user."
      return
    fi
  fi

  echo "[1/5] Fetching latest updates from GitHub..."
  git fetch --all --prune || { show_error "git fetch failed." "Git Error"; return; }

  local branch
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"

  if [[ "$dirty" == "yes" && "$AUTO_STASH" == "yes" ]]; then
    local before after
    before="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
    git stash push -u -m "launcher-auto-stash $(date '+%Y-%m-%d %H:%M:%S')" >/dev/null 2>&1 || true
    after="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "${after:-0}" -gt "${before:-0}" ]]; then
      STASH_CREATED="yes"
      echo "Auto-stashed local changes."
    fi
  fi

  if ! git pull --ff-only origin "$branch"; then
    [[ "$STASH_CREATED" == "yes" ]] && echo "Your stash is still available: git stash list"
    show_error "git pull failed (non-fast-forward/conflict)." "Git Error"
    return
  fi

  if [[ "$STASH_CREATED" == "yes" ]]; then
    echo "Restoring auto-stashed changes..."
    if ! git stash pop >/dev/null 2>&1; then
      show_error "Stash restore had conflicts. Resolve manually (git stash list)." "Git Warning"
    fi
  fi

  echo "[2/5] Verifying Docker..."
  if ! docker info >/dev/null 2>&1; then
    echo "Docker not ready. Attempting to start Docker Desktop..."
    open -a Docker 2>/dev/null || true
    for _ in $(seq 1 180); do
      docker info >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  docker info >/dev/null 2>&1 || { show_error "Docker did not become ready within 3 minutes." "Docker Error"; return; }

  echo "[3/5] Starting containers..."
  if [[ -f "$PROJECT_DIR/compose-up.sh" ]]; then
    if ! "$PROJECT_DIR/compose-up.sh" >/dev/null 2>&1; then
      docker compose up -d --build >/dev/null 2>&1 || { show_error "compose-up.sh and docker compose up failed." "Docker Error"; return; }
    fi
  elif ! docker compose up -d >/dev/null 2>&1; then
    docker compose up -d --build >/dev/null 2>&1 || { show_error "docker compose up failed." "Docker Error"; return; }
  fi

  echo "[4/5] Waiting for Streamlit health..."
  local health_url="http://localhost:8501/_stcore/health"
  for _ in $(seq 1 180); do
    if curl -fsS --max-time 3 "$health_url" >/dev/null 2>&1; then
      echo "[5/5] Streamlit is healthy."
      open "http://localhost:8501" >/dev/null 2>&1 || true
      show_info "App is running at http://localhost:8501"
      return
    fi
    sleep 1
  done

  show_error "Streamlit health check timed out.\nRun: docker compose logs -f" "Startup Timeout"
}

stop_flow() {
  command -v docker >/dev/null 2>&1 || { show_error "Docker CLI not found in PATH." "Missing Tool"; return; }
  echo "Stopping containers..."
  if ! docker compose down >/dev/null 2>&1; then
    show_error "docker compose down failed." "Docker Error"
    return
  fi
  show_info "Algo Trading app stopped successfully."
}

menu_loop
