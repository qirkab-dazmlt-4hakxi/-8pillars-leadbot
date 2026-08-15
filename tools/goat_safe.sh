#!/usr/bin/env bash

# GOAT high-assurance build runner.
# A failing build terminates only its protected subshell,
# never the interactive Codespaces terminal.

goat_build() {
    local name="${1:-GOAT BUILD}"
    shift || true

    echo
    echo "============================================"
    echo "$name"
    echo "============================================"

    (
        set -Eeuo pipefail

        trap '
            rc=$?
            echo
            echo "--------------------------------------------"
            echo "GOAT BUILDER FAILURE"
            echo "EXIT CODE : $rc"
            echo "COMMAND   : $BASH_COMMAND"
            echo "LINE      : $LINENO"
            echo "--------------------------------------------"
            exit "$rc"
        ' ERR

        "$@"
    )

    local rc=$?

    echo
    if [ "$rc" -eq 0 ]; then
        echo "============================================"
        echo "$name: PASS"
        echo "TERMINAL REMAINS ACTIVE"
        echo "============================================"
    else
        echo "============================================"
        echo "$name: FAILED SAFELY"
        echo "MAIN TERMINAL IS STILL ACTIVE"
        echo "============================================"
    fi

    return "$rc"
}


goat_python() {
    (
        set -Eeuo pipefail

        cd /workspaces/-8pillars-leadbot/app

        python3 "$@"
    )

    local rc=$?

    if [ "$rc" -ne 0 ]; then
        echo "PYTHON COMMAND FAILED SAFELY: $rc"
    fi

    return "$rc"
}


goat_targeted_test() {
    local module="$1"
    local log="/tmp/goat-targeted.log"

    (
        set -Eeuo pipefail

        cd /workspaces/-8pillars-leadbot/app

        python3 -m unittest \
            "$module" -q \
            >"$log" 2>&1
    )

    local rc=$?

    if [ "$rc" -eq 0 ]; then
        echo "TARGETED TEST: PASS"
        tail -8 "$log"
    else
        echo "TARGETED TEST: FAILED"
        tail -80 "$log"
    fi

    return "$rc"
}


goat_full_test() {
    local log="/tmp/goat-full.log"

    (
        set -Eeuo pipefail

        cd /workspaces/-8pillars-leadbot/app

        python3 -m unittest discover \
            -s tests_v2 \
            -q \
            >"$log" 2>&1
    )

    local rc=$?

    if [ "$rc" -eq 0 ]; then
        echo "FULL GOAT REGRESSION: PASS"
        tail -8 "$log"
    else
        echo "FULL GOAT REGRESSION: FAILED"
        tail -100 "$log"
    fi

    return "$rc"
}


goat_security() {
    local log="/tmp/goat-security.log"

    (
        set -Eeuo pipefail

        cd /workspaces/-8pillars-leadbot

        python3 \
          app/leadbot_v2/goat/security/secret_sentinel.py \
          >"$log" 2>&1
    )

    local rc=$?

    if [ "$rc" -eq 0 ]; then
        echo "GOAT SECRET SENTINEL: PASS"
        tail -8 "$log"
    else
        echo "GOAT SECRET SENTINEL: FAILED"
        tail -80 "$log"
    fi

    return "$rc"
}


goat_remote_verify() {
    (
        set -Eeuo pipefail

        cd /workspaces/-8pillars-leadbot

        git fetch origin

        local_sha="$(git rev-parse HEAD)"
        remote_sha="$(
            git rev-parse \
            origin/v2-intelligence-platform
        )"

        echo "LOCAL : $local_sha"
        echo "REMOTE: $remote_sha"

        test "$local_sha" = "$remote_sha"
    )

    local rc=$?

    if [ "$rc" -eq 0 ]; then
        echo "REMOTE BACKUP VERIFIED"
    else
        echo "REMOTE BACKUP NOT VERIFIED"
    fi

    return "$rc"
}
