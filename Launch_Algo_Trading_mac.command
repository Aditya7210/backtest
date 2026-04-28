#!/bin/bash
set -euo pipefail

# ---------------------------
# macOS one-click launcher:
# 1) Resolve project directory
# 2) Pull latest from GitHub
# 3) Ensure Docker is running
# 4) Start docker compose
# 5) Open Streamlit once healthy
# ---------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_CONFIG="$HOME/.algo_trading_launcher_path"
PROJECT_DIR=""

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

command -v git >/dev/null 2>&1 || { echo "ERROR: git is not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker CLI is not installed."; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is not installed."; exit 1; }

echo
echo "[1/4] Fetching latest updates from GitHub..."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ERROR: Not a git repository."; exit 1; }
git fetch --all --prune
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD || echo main)"
if ! git pull --ff-only origin "$CURRENT_BRANCH"; then
  echo
  echo "ERROR: git pull failed."
  echo "This usually means local changes must be committed or stashed first."
  exit 1
fi

echo
echo "[2/4] Verifying Docker..."
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
echo "[3/4] Starting containers..."
if ! docker compose up -d; then
  echo "docker compose up failed. Retrying with --build..."
  docker compose up -d --build
fi

echo
echo "[4/4] Waiting for Streamlit health endpoint..."
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

