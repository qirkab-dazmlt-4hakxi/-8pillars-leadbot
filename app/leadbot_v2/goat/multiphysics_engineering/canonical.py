from __future__ import annotations

import hashlib
import json

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


def _default(value):
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, (set, frozenset)):
        return sorted(value)

    if callable(value):
        return getattr(
            value,
            "__qualname__",
            repr(value),
        )

    raise TypeError(
        f"unsupported canonical type: "
        f"{type(value).__name__}"
    )


def canonical_json(value) -> str:
    return json.dumps(
        value,
        default=_default,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def to_primitive(value):
    return json.loads(
        canonical_json(value)
    )


def stable_hash(value) -> str:
    return hashlib.sha256(
        canonical_json(value).encode(
            "utf-8"
        )
    ).hexdigest()
