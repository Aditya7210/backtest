#!/bin/bash
set -euo pipefail

# ---------------------------
# macOS one-click launcher:
# 1) Resolve project directory
# 2) GUI action: Start/Update or Stop
# 3) Pull latest from GitHub (auto-stash supported)
# 4) Ensure Docker is running
# 5) Start/Stop docker compose
# 6) Open Streamlit once healthy (start path)
# ---------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_CONFIG="$HOME/.algo_trading_launcher_path"
PROJECT_DIR=""
ACTION=""
AUTO_STASH="no"
STASH_CREATED="no"

is_project_dir() {
  local d="$1"
  [[ -n "$d" ]] || return 1
  [[ -f "$d/docker-compose.yml" && -f "$d/Dashboard/dashboard.py" ]]
}

try_project_dir() {
  local d="$1"
  if is_project_dir "$d"; then
    PROJECT_DIR="$d"
    return 0
  fi
  return 1
}

if [[ -n "${ALGO_TRADING_PROJECT_DIR:-}" ]]; then
  try_project_dir "${ALGO_TRADING_PROJECT_DIR}" || true
fi

if [[ -z "$PROJECT_DIR" ]]; then
  try_project_dir "$SCRIPT_DIR" || true
fi
if [[ -z "$PROJECT_DIR" ]]; then
  try_project_dir "$SCRIPT_DIR/Algo_Trading_System" || true
fi
if [[ -z "$PROJECT_DIR" ]]; then
  try_project_dir "$HOME/PROJECTS/Algo_Trading_System" || true
fi
if [[ -z "$PROJECT_DIR" ]]; then
  try_project_dir "$HOME/Desktop/Algo_Trading_System" || true
fi
if [[ -z "$PROJECT_DIR" && -f "$LAUNCHER_CONFIG" ]]; then
  SAVED_DIR="$(cat "$LAUNCHER_CONFIG" 2>/dev/null || true)"
  try_project_dir "$SAVED_DIR" || true
fi

if [[ -z "$PROJECT_DIR" ]]; then
  echo "Could not auto-detect project folder."
  read -r -p "Enter full path to Algo_Trading_System: " USER_DIR
  try_project_dir "$USER_DIR" || true
fi

if [[ -z "$PROJECT_DIR" ]]; then
  echo
  echo "ERROR: Invalid project path."
  echo "Required files not found: docker-compose.yml and Dashboard/dashboard.py"
  exit 1
fi

echo "$PROJECT_DIR" > "$LAUNCHER_CONFIG"
echo "Project directory: $PROJECT_DIR"
cd "$PROJECT_DIR"

command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker CLI is not installed."; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is not installed."; exit 1; }

# ---- GUI action picker ----
ACTION="$(osascript <<'OSA'
set choices to {"Start / Update App", "Stop App", "Exit"}
set selectedItem to choose from list choices with title "Algo Trading Launcher" with prompt "Choose an action:" default items {"Start / Update App"} OK button name "Continue" cancel button name "Exit"
if selectedItem is false then
    return "EXIT"
else
    return item 1 of selectedItem
end if
OSA
)"

if [[ "$ACTION" == "Exit" || "$ACTION" == "EXIT" ]]; then
  exit 0
fi

if [[ "$ACTION" == "Stop App" ]]; then
  echo
  echo "Stopping Algo Trading app containers..."
  docker compose down
  osascript -e 'display dialog "Algo Trading app stopped." buttons {"OK"} default button "OK" with title "Algo Trading Launcher"' >/dev/null
  exit 0
fi

# START/UPDATE path
command -v git >/dev/null 2>&1 || { echo "ERROR: git is not installed."; exit 1; }

AUTO_STASH_REPLY="$(osascript <<'OSA'
display dialog "If local changes exist, should launcher auto-stash before update and auto-pop after update?" buttons {"No", "Yes"} default button "Yes" with title "Auto Stash Option"
return button returned of result
OSA
)"
if [[ "$AUTO_STASH_REPLY" == "Yes" ]]; then
  AUTO_STASH="yes"
fi

echo
echo "[1/5] Fetching latest updates from GitHub..."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ERROR: Not a git repository."; exit 1; }

if [[ -n "$(git status --porcelain)" ]]; then
  if [[ "$AUTO_STASH" == "yes" ]]; then
    STASH_BEFORE="$(git stash list | wc -l | tr -d ' ')"
    git stash push -u -m "launcher-auto-stash $(date '+%Y-%m-%d %H:%M:%S')" >/dev/null 2>&1 || true
    STASH_AFTER="$(git stash list | wc -l | tr -d ' ')"
    if [[ "${STASH_AFTER:-0}" -gt "${STASH_BEFORE:-0}" ]]; then
      STASH_CREATED="yes"
      echo "Auto-stashed local changes before update."
    fi
  else
    echo
    echo "ERROR: Local changes detected. Enable auto-stash or stash manually before update."
    exit 1
  fi
fi

git fetch --all --prune
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD || echo main)"
if ! git pull --ff-only origin "$CURRENT_BRANCH"; then
  echo
  echo "ERROR: git pull failed."
  if [[ "$STASH_CREATED" == "yes" ]]; then
    echo "Auto-stash was created and kept. Inspect with: git stash list"
  fi
  exit 1
fi

if [[ "$STASH_CREATED" == "yes" ]]; then
  echo "Restoring auto-stashed local changes..."
  if ! git stash pop >/dev/null 2>&1; then
    echo "WARNING: Could not auto-apply stashed changes cleanly."
    echo "Resolve conflicts manually. Stash may still exist in: git stash list"
  fi
fi

echo
echo "[2/5] Verifying Docker..."
if ! docker info >/dev/null 2>&1; then
  echo "Docker is not ready. Attempting to start Docker Desktop..."
  open -a Docker || true

  for _ in $(seq 1 180); do
    if docker info >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker did not become ready within timeout."
  exit 1
fi
echo "Docker is ready."

echo
echo "[3/5] Starting containers..."
if ! docker compose up -d; then
  echo "docker compose up failed. Retrying with --build..."
  docker compose up -d --build
fi

echo
echo "[4/5] Waiting for Streamlit health endpoint..."
HEALTH_URL="http://localhost:8501/_stcore/health"
for _ in $(seq 1 180); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Streamlit is healthy. Opening browser..."
    open "http://localhost:8501"
    echo "Done."
    exit 0
  fi
  sleep 1
done

echo "ERROR: Streamlit health check did not pass in time."
echo "Check logs using: docker compose logs -f"
exit 1
