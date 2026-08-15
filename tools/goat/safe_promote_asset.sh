#!/usr/bin/env bash
set -Eeo pipefail

if test "$#" -ne 2; then
    echo "usage: safe_promote_asset.sh SOURCE DESTINATION"
    exit 2
fi

SOURCE="$1"
DEST="$2"

if test ! -f "$SOURCE"; then
    echo "SAFE PROMOTE ASSET FAILED: source missing: $SOURCE"
    exit 1
fi

DEST_DIR="$(dirname "$DEST")"
mkdir -p "$DEST_DIR"

TMP="$DEST_DIR/.goat-promote.$(basename "$DEST").$$"

cleanup() {
    rm -f "$TMP"
}

trap cleanup EXIT

cp "$SOURCE" "$TMP"

test -s "$TMP" || {
    echo "SAFE PROMOTE ASSET FAILED: temporary file empty"
    exit 1
}

if [[ "$DEST" == *.sh ]]; then
    bash -n "$TMP"

    chmod 755 "$TMP"
fi

mv -f "$TMP" "$DEST"

trap - EXIT

echo "GOAT SAFE ASSET PROMOTE: PASS"
echo "$DEST"
