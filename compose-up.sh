#!/usr/bin/env bash
set -euo pipefail

docker compose up -d "$@"

for _ in $(seq 1 45); do
  if curl -fsS "http://localhost:8000/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if command -v open >/dev/null 2>&1; then
  open "http://localhost:3000"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:3000"
fi
