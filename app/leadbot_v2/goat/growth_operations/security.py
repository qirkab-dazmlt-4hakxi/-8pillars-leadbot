from __future__ import annotations

import os

from .models import SecretRef


class SecretResolver:
    def resolve(self, ref: SecretRef) -> str:
        raise NotImplementedError


class EnvironmentSecretResolver(SecretResolver):
    def resolve(self, ref: SecretRef) -> str:
        name = ref.name.strip()

        if not name:
            raise ValueError("secret reference name required")

        value = os.environ.get(name)

        if value is None:
            raise RuntimeError(
                f"secret not configured: {name}"
            )

        value = value.strip()

        if not value:
            raise RuntimeError(
                f"secret empty: {name}"
            )

        return value


def redact(mapping):
    sensitive_markers = (
        "secret",
        "token",
        "password",
        "authorization",
        "api_key",
        "apikey",
        "private_key",
    )

    result = {}

    for key, value in mapping.items():
        normalized = str(key).lower()

        if any(
            marker in normalized
            for marker in sensitive_markers
        ):
            result[key] = "[REDACTED]"
        else:
            result[key] = value

    return result
