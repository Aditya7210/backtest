#!/usr/bin/env bash
set -euo pipefail

docker compose up -d "$@"

http_ok() {
  local url="$1"
  local code
  code="$(curl -L -sS -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null || echo "000")"
  [[ "$code" =~ ^[0-9]{3}$ ]] || return 1
  [[ "$code" -ge 200 && "$code" -lt 500 ]]
}

wait_any() {
  local seconds="$1"
  shift
  local _i url
  for _i in $(seq 1 "$seconds"); do
    for url in "$@"; do
      if http_ok "$url"; then
        return 0
      fi
    done
    sleep 1
  done
  return 1
}

wait_any 120 "http://localhost:3000/" "http://127.0.0.1:3000/" || true
wait_any 120 "http://localhost:8000/api/health" "http://127.0.0.1:8000/api/health" "http://localhost:8000/docs" "http://127.0.0.1:8000/docs" || true

if command -v open >/dev/null 2>&1; then
  open "http://localhost:3000"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:3000"
fi
