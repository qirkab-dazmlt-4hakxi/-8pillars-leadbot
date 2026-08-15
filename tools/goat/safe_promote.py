from __future__ import annotations

import argparse
import os
import py_compile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compile and atomically promote "
            "a GOAT staged Python source file."
        )
    )

    parser.add_argument(
        "staged",
    )

    parser.add_argument(
        "destination",
    )

    args = parser.parse_args()

    staged = Path(
        args.staged
    )

    destination = Path(
        args.destination
    )

    if not staged.exists():
        raise SystemExit(
            f"staged file missing: {staged}"
        )

    if staged.resolve() == destination.resolve():
        raise SystemExit(
            "staged and destination "
            "must be different paths"
        )

    py_compile.compile(
        str(staged),
        doraise=True,
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.replace(
        staged,
        destination,
    )

    py_compile.compile(
        str(destination),
        doraise=True,
    )

    print(
        "GOAT SAFE PROMOTE: PASS"
    )

    print(
        f"{destination}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
