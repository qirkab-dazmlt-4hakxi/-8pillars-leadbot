#!/usr/bin/env bash

set -Eeo pipefail

ROOT="$(
    git rev-parse --show-toplevel
)"

cd "$ROOT"

echo "===== GOAT VERIFY BUILD ====="

python3 -m compileall \
    -q \
    app/leadbot_v2/goat

cd app

python3 -m unittest discover \
    -s tests_v2 \
    -q \
    >/tmp/goat-verify-build.log 2>&1

tail -16 \
    /tmp/goat-verify-build.log

cd "$ROOT"

python3 \
    app/leadbot_v2/goat/security/secret_sentinel.py

echo "GOAT VERIFY BUILD: PASS"
