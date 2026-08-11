#!/usr/bin/env bash
set -euo pipefail
[ -d .venv ] && . .venv/bin/activate
uvicorn leadbot.api:app --host 0.0.0.0 --port 8080
