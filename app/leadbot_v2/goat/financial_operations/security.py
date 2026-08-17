from __future__ import annotations

import os

from typing import Protocol

from .models import (
    SecretRef,
    SecretResolutionError,
)


class SecretResolver(
    Protocol
):
    def resolve(
        self,
        ref: SecretRef,
    ) -> str:
        ...


class EnvironmentSecretResolver:
    """
    Resolves credentials from environment variables.

    Secret values are never persisted here and this class intentionally
    provides no method that enumerates secret values.
    """

    def resolve(
        self,
        ref: SecretRef,
    ) -> str:
        name = ref.name.strip()

        if not name:
            raise SecretResolutionError(
                "empty secret reference"
            )

        value = os.environ.get(
            name
        )

        if value is None:
            raise SecretResolutionError(
                f"required secret is not configured: "
                f"{name}"
            )

        value = value.strip()

        if not value:
            raise SecretResolutionError(
                f"required secret is empty: "
                f"{name}"
            )

        return value


def redact_mapping(
    value: dict,
    *,
    sensitive_keys=(
        "token",
        "secret",
        "password",
        "api_key",
        "apikey",
        "authorization",
    ),
):
    sensitive = tuple(
        key.lower()
        for key
        in sensitive_keys
    )

    result = {}

    for key, item in value.items():
        normalized = str(
            key
        ).lower()

        if any(
            marker
            in normalized
            for marker
            in sensitive
        ):
            result[
                key
            ] = "[REDACTED]"

        else:
            result[
                key
            ] = item

    return result
