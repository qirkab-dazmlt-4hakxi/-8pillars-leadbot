#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path("/workspaces/-8pillars-leadbot").resolve()


def safe_target(raw: str) -> Path:
    target = (ROOT / raw).resolve()

    if target != ROOT and ROOT not in target.parents:
        raise SystemExit(
            "GOAT PAYLOAD REJECTED: target outside repository"
        )

    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("sha256")

    args = parser.parse_args()

    target = safe_target(args.target)

    encoded = "".join(
        line.strip()
        for line in sys.stdin
        if line.strip()
    )

    if not encoded:
        raise SystemExit(
            "GOAT PAYLOAD REJECTED: empty payload"
        )

    try:
        compressed = base64.b64decode(
            encoded,
            validate=True,
        )

        content = gzip.decompress(
            compressed
        )

    except Exception as exc:
        raise SystemExit(
            "GOAT PAYLOAD REJECTED: "
            f"corrupt or truncated payload: {exc}"
        )

    actual = hashlib.sha256(
        content
    ).hexdigest()

    expected = args.sha256.lower()

    if actual != expected:
        raise SystemExit(
            "\n".join(
                (
                    "GOAT PAYLOAD REJECTED: CHECKSUM FAILURE",
                    f"EXPECTED: {expected}",
                    f"ACTUAL  : {actual}",
                    "Original file was NOT modified.",
                )
            )
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary_name = tempfile.mkstemp(
        prefix=".goat-",
        dir=str(target.parent),
    )

    try:
        with os.fdopen(
            fd,
            "wb",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_name,
            target,
        )

    finally:
        if os.path.exists(
            temporary_name
        ):
            os.unlink(
                temporary_name
            )

    print(
        f"GOAT PAYLOAD OK: "
        f"{target.relative_to(ROOT)}"
    )

    print(
        f"BYTES: {len(content)}"
    )

    print(
        f"SHA256: {actual}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
