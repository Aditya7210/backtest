#!/usr/bin/env sh
set -eu

# Always run from project root regardless of caller working directory.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

PYTHON_BIN="python"
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [ "${SKIP_INSTRUMENT_UPDATE:-0}" = "1" ]; then
  echo "Skipping instrument update (SKIP_INSTRUMENT_UPDATE=1)"
else
  echo "Starting instrument update..."
  if ! "$PYTHON_BIN" "Dashboard/Backtesting_page/Features/instrument_mapper_updater.py"; then
    echo "Instrument update failed; continuing startup." >&2
  fi
fi

echo "Starting Streamlit..."
exec streamlit run "Dashboard/dashboard.py" --server.port=8501 --server.address=0.0.0.0
