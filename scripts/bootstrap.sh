#!/usr/bin/env bash
set -euo pipefail

missing=()
for command_name in python3 go cmake cc c++ node npm docker; do
  command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
done
docker compose version >/dev/null 2>&1 || missing+=("docker compose")

if ((${#missing[@]})); then
  echo "Missing prerequisites: ${missing[*]}" >&2
  echo "Install them using your operating system's supported method, then rerun." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "No .env found. Copy .env.example to .env and replace CHANGE_ME before make up."
else
  echo "Existing .env preserved."
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix apps/web install

echo "Setup complete. Run 'make check', then 'make up' and 'make health'."
