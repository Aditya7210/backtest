#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------
# macOS one-click launcher
# 1) Resolve project directory (name-agnostic, scans common paths)
# 2) Custom GUI: Start/Update  |  Stop  |  Exit
# 3) Pull latest from GitHub (auto-stash only prompted if dirty)
# 4) Ensure Docker is running
# 5) Start/Stop docker compose
# 6) Open Streamlit once healthy (start path)
# ---------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_CONFIG="$HOME/.algo_trading_launcher_path"
PROJECT_DIR=""
AUTO_STASH="no"
STASH_CREATED="no"

# ================================================================
#  PROJECT DIRECTORY VALIDATION
# ================================================================
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

# Scan one level of subdirectories under a given parent
scan_subdirs() {
  local parent="$1"
  [[ -d "$parent" ]] || return 0
  while IFS= read -r -d '' sub; do
    try_project_dir "$sub" && return 0
  done < <(find "$parent" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)
  return 1
}

# ================================================================
#  PROJECT RESOLUTION  (name-agnostic)
#  1. Env var override
#  2. Script's own directory
#  3. Saved path from last run
#  4. Scan subdirs of common parent locations
#  5. Folder-chooser dialog
# ================================================================

# 1. Env var override
if [[ -n "${ALGO_TRADING_PROJECT_DIR:-}" ]]; then
  try_project_dir "${ALGO_TRADING_PROJECT_DIR}" || true
fi

# 2. Script's own directory (launcher placed inside the project)
if [[ -z "$PROJECT_DIR" ]]; then
  try_project_dir "$SCRIPT_DIR" || true
fi

# 3. Saved path from last run
if [[ -z "$PROJECT_DIR" && -f "$LAUNCHER_CONFIG" ]]; then
  SAVED_DIR="$(cat "$LAUNCHER_CONFIG" 2>/dev/null || true)"
  [[ -n "$SAVED_DIR" ]] && { try_project_dir "$SAVED_DIR" || true; }
fi

# 4. Scan common parent locations (any folder name accepted)
if [[ -z "$PROJECT_DIR" ]]; then
  for search_root in \
      "$SCRIPT_DIR/.." \
      "$HOME/PROJECTS" \
      "$HOME/Desktop" \
      "$HOME/Documents" \
      "$HOME/Developer" \
      "$HOME/dev" \
      "$HOME/src" \
      "$HOME"
  do
    [[ -z "$PROJECT_DIR" ]] && { scan_subdirs "$search_root" || true; }
  done
fi

# 5. Folder-chooser dialog as last resort
if [[ -z "$PROJECT_DIR" ]]; then
  echo "Could not auto-detect project folder. Showing folder chooser..."
  CHOSEN="$(osascript <<'OSA' 2>/dev/null || true
    set chosen to choose folder with prompt "Select your Algo Trading project folder (must contain docker-compose.yml):"
    return POSIX path of chosen
OSA
  )"
  # Strip trailing slash
  CHOSEN="${CHOSEN%/}"
  [[ -n "$CHOSEN" ]] && { try_project_dir "$CHOSEN" || true; }
fi

if [[ -z "$PROJECT_DIR" ]]; then
  osascript -e 'display dialog "Could not find a valid project folder.\n\nRequired files:\n  • docker-compose.yml\n  • Dashboard/dashboard.py\n\nTip: set ALGO_TRADING_PROJECT_DIR env var or place the launcher inside the project." buttons {"OK"} default button "OK" with title "Project Not Found" with icon stop' >/dev/null 2>&1 || true
  echo "ERROR: Valid project folder not found."
  exit 1
fi

# Save resolved path for next run
echo "$PROJECT_DIR" > "$LAUNCHER_CONFIG"
echo "Project directory: $PROJECT_DIR"
cd "$PROJECT_DIR"

# ================================================================
#  TOOL CHECKS
# ================================================================
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker CLI not found in PATH."; exit 1; }
command -v curl   >/dev/null 2>&1 || { echo "ERROR: curl not found in PATH.";       exit 1; }

# ================================================================
#  MAIN GUI  –  single dialog, three clearly-labelled buttons
#  osascript button order: left-to-right maps to buttons list 1→N
#  We put "Exit" first so it is not the default/return key button.
# ================================================================
ACTION="$(osascript <<OSA
tell application "System Events"
    set result to button returned of (display dialog ¬
        "Project:  $PROJECT_DIR\n\nWhat would you like to do?" ¬
        buttons {"Exit", "Stop App", "Start / Update"} ¬
        default button "Start / Update" ¬
        cancel button "Exit" ¬
        with title "Algo Trading Launcher" ¬
        with icon note)
    return result
end tell
OSA
2>/dev/null || echo "EXIT")"

case "$ACTION" in
  "Start / Update") : ;;          # fall through to start path
  "Stop App")       goto_stop=1 ;;
  *)                exit 0 ;;     # Exit / cancelled
esac

# ================================================================
#  STOP PATH
# ================================================================
if [[ "${goto_stop:-0}" == "1" ]]; then
  echo
  echo "Stopping containers..."
  docker compose down
  osascript -e 'display dialog "Algo Trading app stopped successfully." buttons {"OK"} default button "OK" with title "Algo Trading Launcher" with icon note' >/dev/null 2>&1 || true
  exit 0
fi

# ================================================================
#  START / UPDATE PATH
# ================================================================
command -v git >/dev/null 2>&1 || { echo "ERROR: git not found in PATH."; exit 1; }

echo
echo "[1/5] Checking repository status..."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ERROR: Not a git repository."; exit 1; }

# ---- Dirty-tree check BEFORE asking about stash ----
WORKTREE_DIRTY=""
[[ -n "$(git status --porcelain 2>/dev/null)" ]] && WORKTREE_DIRTY="yes"

if [[ "$WORKTREE_DIRTY" == "yes" ]]; then
  # Only now prompt about stash (tree is actually dirty)
  STASH_REPLY="$(osascript <<'OSA' 2>/dev/null || echo "No"
tell application "System Events"
    set result to button returned of (display dialog ¬
        "⚠  Uncommitted local changes detected.\n\nAuto-stash will save your changes before pulling and restore them afterward." ¬
        buttons {"Abort Update", "Auto-Stash & Continue"} ¬
        default button "Auto-Stash & Continue" ¬
        cancel button "Abort Update" ¬
        with title "Local Changes Detected" ¬
        with icon caution)
    return result
end tell
OSA
  )"

  if [[ "$STASH_REPLY" == "Auto-Stash & Continue" ]]; then
    AUTO_STASH="yes"
  else
    echo "Update aborted. Resolve local changes manually and re-run."
    exit 0
  fi
fi

# ---- Fetch ----
echo
echo "[1/5] Fetching latest updates from GitHub..."
git fetch --all --prune

# ---- Stash if needed ----
if [[ "$WORKTREE_DIRTY" == "yes" && "$AUTO_STASH" == "yes" ]]; then
  STASH_BEFORE="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
  git stash push -u -m "launcher-auto-stash $(date '+%Y-%m-%d %H:%M:%S')" >/dev/null 2>&1 || true
  STASH_AFTER="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${STASH_AFTER:-0}" -gt "${STASH_BEFORE:-0}" ]]; then
    STASH_CREATED="yes"
    echo "Auto-stashed local changes."
  fi
fi

# ---- Pull ----
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
if ! git pull --ff-only origin "$CURRENT_BRANCH"; then
  echo
  echo "ERROR: git pull failed (possible merge conflict or non-fast-forward)."
  [[ "$STASH_CREATED" == "yes" ]] && echo "Your stash is intact. Run: git stash list"
  exit 1
fi

# ---- Restore stash ----
if [[ "$STASH_CREATED" == "yes" ]]; then
  echo "Restoring auto-stashed changes..."
  if ! git stash pop >/dev/null 2>&1; then
    echo "WARNING: Stash pop had conflicts. Resolve manually (git stash list)."
  fi
fi

# ================================================================
#  DOCKER
# ================================================================
echo
echo "[2/5] Verifying Docker..."
if ! docker info >/dev/null 2>&1; then
  echo "Docker not ready — attempting to start Docker Desktop..."
  open -a Docker 2>/dev/null || true

  for _ in $(seq 1 180); do
    docker info >/dev/null 2>&1 && break
    sleep 1
  done
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker did not become ready within 3 minutes."
  exit 1
fi
echo "Docker is ready."

# ================================================================
#  CONTAINERS
# ================================================================
echo
echo "[3/5] Starting containers..."
if ! docker compose up -d 2>&1; then
  echo "Retrying with --build..."
  docker compose up -d --build
fi

# ================================================================
#  HEALTH CHECK
# ================================================================
echo
echo "[4/5] Waiting for Streamlit to become healthy..."
HEALTH_URL="http://localhost:8501/_stcore/health"

for _ in $(seq 1 180); do
  if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[5/5] Streamlit is healthy. Opening browser..."
    open "http://localhost:8501"
    echo
    echo "All done. App is running at http://localhost:8501"
    exit 0
  fi
  sleep 1
done

echo "ERROR: Streamlit health check timed out."
echo "Run: docker compose logs -f"
exit 1