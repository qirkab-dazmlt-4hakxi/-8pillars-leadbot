from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit, urlunsplit


_WS = re.compile(r"\s+")
_DIGITS = re.compile(r"\D+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    return _WS.sub(
        " ",
        value,
    ).strip()


def canonical_key(
    value: str | None,
) -> str:
    return _NON_ALNUM.sub(
        "",
        normalize_text(value).lower(),
    )


def normalize_email(
    value: str | None,
) -> str | None:
    value = normalize_text(
        value
    ).lower()

    if not value:
        return None

    if value.count("@") != 1:
        return None

    local, domain = value.split(
        "@",
        1,
    )

    if not local or "." not in domain:
        return None

    return f"{local}@{domain}"


def normalize_phone(
    value: str | None,
) -> str | None:
    if not value:
        return None

    digits = _DIGITS.sub(
        "",
        value,
    )

    if (
        len(digits) == 11
        and digits.startswith("1")
    ):
        digits = digits[1:]

    if len(digits) != 10:
        return None

    return digits


def normalize_postal(
    value: str | None,
) -> str | None:
    if not value:
        return None

    digits = _DIGITS.sub(
        "",
        value,
    )

    if len(digits) < 5:
        return None

    return digits[:5]


def normalize_state(
    value: str | None,
) -> str | None:
    value = normalize_text(
        value
    ).upper()

    if not value:
        return None

    mapping = {
        "TEXAS": "TX",
        "OKLAHOMA": "OK",
        "LOUISIANA": "LA",
        "ARKANSAS": "AR",
    }

    if value in mapping:
        return mapping[value]

    if len(value) == 2:
        return value

    return value


def normalize_uri(
    value: str | None,
) -> str:
    value = normalize_text(
        value
    )

    if not value:
        return ""

    try:
        parts = urlsplit(
            value
        )

        if not parts.scheme:
            return value

        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                parts.path.rstrip("/"),
                parts.query,
                "",
            )
        )

    except Exception:
        return value


def _json_default(
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
        f"not JSON serializable: "
        f"{type(value).__name__}"
    )


def canonical_json(
    payload,
) -> str:
    return json.dumps(
        payload,
        default=_json_default,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )


def stable_hash(
    payload,
) -> str:
    return hashlib.sha256(
        canonical_json(
            payload
        ).encode(
            "utf-8"
        )
    ).hexdigest()


def token_set(
    value: str | None,
) -> set[str]:
    return {
        token
        for token
        in re.findall(
            r"[a-z0-9]+",
            normalize_text(
                value
            ).lower(),
        )
        if token
    }


def jaccard_similarity(
    left: str | None,
    right: str | None,
) -> float:
    a = token_set(
        left
    )

    b = token_set(
        right
    )

    if not a or not b:
        return 0.0

    return len(
        a & b
    ) / len(
        a | b
    )
