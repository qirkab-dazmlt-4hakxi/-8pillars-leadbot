from __future__ import annotations

import json

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ApplicationServerError(RuntimeError):
    pass


class BadRequest(ApplicationServerError):
    pass


class PayloadTooLarge(BadRequest):
    pass


class UnsupportedMediaType(BadRequest):
    pass


class RouteNotFound(ApplicationServerError):
    pass


class RealtimeProtocolError(ApplicationServerError):
    pass


class Platform(str, Enum):
    IOS = "ios"
    IPADOS = "ipados"
    ANDROID = "android"
    MACOS = "macos"
    WINDOWS = "windows"
    WEB = "web"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str

    headers: dict[str, str]

    query: dict[str, str]

    body: bytes = b""

    request_id: str | None = None

    remote_address: str | None = None

    @property
    def content_type(self) -> str:
        value = self.headers.get(
            "content-type",
            "",
        )

        return (
            value.split(
                ";",
                1,
            )[0]
            .strip()
            .lower()
        )

    def json(
        self,
        *,
        maximum_bytes: int = (
            2
            * 1024
            * 1024
        ),
    ) -> dict[str, Any]:
        if len(self.body) > maximum_bytes:
            raise PayloadTooLarge(
                "JSON payload too large"
            )

        if not self.body:
            return {}

        if (
            self.content_type
            and self.content_type
            != "application/json"
        ):
            raise UnsupportedMediaType(
                self.content_type
            )

        try:
            value = json.loads(
                self.body.decode(
                    "utf-8"
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise BadRequest(
                "invalid JSON"
            ) from exc

        if not isinstance(
            value,
            dict,
        ):
            raise BadRequest(
                "JSON root must be object"
            )

        return value


@dataclass(frozen=True)
class HttpResponse:
    status: int

    body: bytes = b""

    headers: tuple[
        tuple[str, str],
        ...
    ] = ()

    @staticmethod
    def json(
        status: int,
        payload: Mapping[
            str,
            Any,
        ],
        *,
        headers: tuple[
            tuple[str, str],
            ...
        ] = (),
    ) -> "HttpResponse":
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=True,
            default=str,
        ).encode(
            "utf-8"
        )

        base_headers = (
            (
                "content-type",
                "application/json",
            ),
            (
                "content-length",
                str(
                    len(
                        encoded
                    )
                ),
            ),
            (
                "cache-control",
                "no-store",
            ),
        )

        return HttpResponse(
            status=status,
            body=encoded,
            headers=(
                base_headers
                + headers
            ),
        )


def normalize_headers(
    raw_headers: list[
        tuple[
            bytes,
            bytes,
        ]
    ],
) -> dict[
    str,
    str,
]:
    result = {}

    for key, value in raw_headers:
        name = (
            key.decode(
                "latin-1"
            )
            .strip()
            .lower()
        )

        decoded = (
            value.decode(
                "latin-1"
            )
            .strip()
        )

        if name in result:
            result[name] = (
                result[name]
                + ","
                + decoded
            )

        else:
            result[name] = (
                decoded
            )

    return result


def parse_query_string(
    raw: bytes,
) -> dict[
    str,
    str,
]:
    if not raw:
        return {}

    from urllib.parse import (
        parse_qsl,
    )

    return dict(
        parse_qsl(
            raw.decode(
                "utf-8",
                errors="strict",
            ),
            keep_blank_values=True,
        )
    )


def bearer_token(
    headers: Mapping[
        str,
        str,
    ],
) -> str:
    value = headers.get(
        "authorization",
        "",
    ).strip()

    prefix = "Bearer "

    if not value.startswith(
        prefix
    ):
        raise BadRequest(
            "missing bearer authorization"
        )

    token = value[
        len(prefix):
    ].strip()

    if not token:
        raise BadRequest(
            "empty bearer token"
        )

    return token
