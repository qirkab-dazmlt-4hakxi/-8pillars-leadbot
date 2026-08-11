#!/usr/bin/env bash
set -euo pipefail
[ -d .venv ] && . .venv/bin/activate
python -m leadbot.main scan-now
