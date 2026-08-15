#!/usr/bin/env bash
set -Eeo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BRANCH="$(git branch --show-current)"

if test "$BRANCH" != "v2-intelligence-platform"; then
    echo "SAFE STOP: wrong branch: $BRANCH"
    exit 1
fi

if ! git diff --quiet; then
    echo "SAFE STOP: TRACKED UNCOMMITTED WORK EXISTS"
    git status --short
    exit 1
fi

if ! git diff --cached --quiet; then
    echo "SAFE STOP: STAGED UNCOMMITTED WORK EXISTS"
    git status --short
    exit 1
fi

git fetch origin

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/v2-intelligence-platform)"

if test "$LOCAL" != "$REMOTE"; then
    echo "SAFE STOP: LOCAL/REMOTE DIFFER"
    echo "LOCAL : $LOCAL"
    echo "REMOTE: $REMOTE"
    exit 1
fi

CHECKPOINT_FILE="$ROOT/.git/goat_last_safe_checkpoint"

{
    echo "GOAT LAST SAFE CHECKPOINT"
    echo "branch=$BRANCH"
    echo "sha=$LOCAL"
    echo "remote_sha=$REMOTE"
    echo "saved_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$CHECKPOINT_FILE"

echo "========================================"
echo "GOAT HARD SAVE COMPLETE"
echo "BRANCH: $BRANCH"
echo "SHA   : $LOCAL"
echo "FILE  : $CHECKPOINT_FILE"
echo "REMOTE BACKUP VERIFIED"
echo "========================================"
