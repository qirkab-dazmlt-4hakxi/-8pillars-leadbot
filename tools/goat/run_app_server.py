#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


def main() -> int:
    secret = os.environ.get(
        "GOAT_SESSION_SECRET",
        "",
    )

    if len(
        secret.encode("utf-8")
    ) < 32:
        print(
            "GOAT_SESSION_SECRET must contain at least 32 bytes",
            file=sys.stderr,
        )

        return 2

    try:
        import uvicorn

    except ImportError:
        print(
            "uvicorn is not installed in this environment",
            file=sys.stderr,
        )

        return 3

    from leadbot_v2.goat.app_server import (
        build_application,
    )

    app = build_application(
        session_secret=(
            secret.encode(
                "utf-8"
            )
        )
    )

    host = os.environ.get(
        "GOAT_BIND_HOST",
        "127.0.0.1",
    )

    port = int(
        os.environ.get(
            "GOAT_BIND_PORT",
            "8080",
        )
    )

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        proxy_headers=False,
        server_header=False,
        date_header=False,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
