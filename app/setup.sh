#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
python -m unittest discover -s tests -v
python -m leadbot.main selftest
echo "Setup complete. Run: . .venv/bin/activate && python configure.py"
