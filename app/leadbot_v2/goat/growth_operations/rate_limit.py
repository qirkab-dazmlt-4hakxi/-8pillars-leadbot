from __future__ import annotations

import time

from dataclasses import dataclass


@dataclass
class Bucket:
    capacity: float
    tokens: float
    refill_per_second: float
    updated_at: float


class TokenBucketLimiter:
    def __init__(self) -> None:
        self._buckets = {}

    def configure(
        self,
        *,
        key: str,
        capacity: float,
        refill_per_second: float,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        if refill_per_second <= 0:
            raise ValueError("refill rate must be positive")

        now = time.monotonic()

        self._buckets[key] = Bucket(
            capacity=float(capacity),
            tokens=float(capacity),
            refill_per_second=float(
                refill_per_second
            ),
            updated_at=now,
        )

    def allow(
        self,
        key: str,
        *,
        cost: float = 1.0,
    ) -> bool:
        bucket = self._buckets.get(key)

        if bucket is None:
            raise KeyError(
                f"rate-limit bucket not configured: {key}"
            )

        now = time.monotonic()

        elapsed = max(
            0.0,
            now - bucket.updated_at,
        )

        bucket.tokens = min(
            bucket.capacity,
            bucket.tokens
            + elapsed
            * bucket.refill_per_second,
        )

        bucket.updated_at = now

        if bucket.tokens < cost:
            return False

        bucket.tokens -= cost

        return True
