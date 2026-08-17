from __future__ import annotations

import hashlib
import json

from dataclasses import (
    asdict,
    is_dataclass,
)

from datetime import datetime

from enum import Enum


def _default(
    value,
):
    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if is_dataclass(
        value
    ):
        return asdict(
            value
        )

    if isinstance(
        value,
        set,
    ):
        return sorted(
            value
        )

    raise TypeError(
        f"cannot serialize "
        f"{type(value).__name__}"
    )


def canonical_json(
    value,
) -> str:
    return json.dumps(
        value,
        default=_default,
        sort_keys=True,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )


def stable_hash(
    value,
) -> str:
    return hashlib.sha256(
        canonical_json(
            value
        ).encode(
            "utf-8"
        )
    ).hexdigest()
