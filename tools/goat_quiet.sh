#!/usr/bin/env bash
set -o pipefail

goat_test() {
    local log="/tmp/goat-tests.log"

    echo "GOAT TESTS RUNNING..."

    if python -m unittest discover \
        -s app/tests_v2 -q \
        >"$log" 2>&1
    then
        echo "GOAT TESTS: PASS"
        tail -5 "$log"
    else
        local rc=$?
        echo "GOAT TESTS: FAILED"
        tail -60 "$log"
        return "$rc"
    fi
}

goat_security() {
    local log="/tmp/goat-security.log"

    echo "GOAT SECURITY CHECK..."

    if python \
        app/leadbot_v2/goat/security/secret_sentinel.py \
        >"$log" 2>&1
    then
        echo "GOAT SECURITY: PASS"
        tail -5 "$log"
    else
        local rc=$?
        echo "GOAT SECURITY: FAILED"
        tail -40 "$log"
        return "$rc"
    fi
}

goat_push() {
    git push origin v2-intelligence-platform \
        >/tmp/goat-push.log 2>&1 || {
            tail -40 /tmp/goat-push.log
            return 1
        }

    git fetch origin \
        >/dev/null 2>&1 || return 1

    local local_sha
    local remote_sha

    local_sha="$(git rev-parse HEAD)"
    remote_sha="$(
        git rev-parse \
        origin/v2-intelligence-platform
    )"

    if [ "$local_sha" != "$remote_sha" ]; then
        echo "REMOTE BACKUP MISMATCH"
        return 1
    fi

    echo "REMOTE BACKUP VERIFIED"
}
