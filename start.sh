#!/usr/bin/env bash
# One-click start for macOS / Linux
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python) || { echo "Install Python 3.10+ first"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
[ -f .env ] || cp .env.example .env
if [ ! -f .venv/.deps_v4 ]; then
  .venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1
  .venv/bin/python -m pip install -r requirements.txt && touch .venv/.deps_v4
fi
.venv/bin/python run.py
