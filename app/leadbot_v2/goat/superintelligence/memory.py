from __future__ import annotations

import math

from dataclasses import dataclass

from datetime import datetime

from typing import Any

from .canonical import (
    stable_hash,
)

from .models import (
    ensure_utc,
)


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str

    kind: str
    key: str

    value: Any

    created_at: datetime
    last_accessed_at: datetime

    importance: float
    confidence: float

    access_count: int = 0


class AdaptiveMemory:
    def __init__(
        self,
        *,
        half_life_days: float = 180.0,
    ) -> None:
        if half_life_days <= 0:
            raise ValueError(
                "half_life_days must be positive"
            )

        self.half_life_days = float(
            half_life_days
        )

        self._items: dict[
            str,
            MemoryItem,
        ] = {}

    def remember(
        self,
        *,
        kind: str,
        key: str,
        value,
        importance: float,
        confidence: float,
        now=None,
    ) -> MemoryItem:
        now = ensure_utc(
            now
        )

        memory_id = stable_hash(
            {
                "kind":
                    kind,
                "key":
                    key,
            }
        )[:32]

        previous = self._items.get(
            memory_id
        )

        item = MemoryItem(
            memory_id=(
                memory_id
            ),
            kind=kind,
            key=key,
            value=value,
            created_at=(
                previous.created_at
                if previous
                else now
            ),
            last_accessed_at=(
                now
            ),
            importance=max(
                0.0,
                min(
                    1.0,
                    importance,
                ),
            ),
            confidence=max(
                0.0,
                min(
                    1.0,
                    confidence,
                ),
            ),
            access_count=(
                previous.access_count
                if previous
                else 0
            ),
        )

        self._items[
            memory_id
        ] = item

        return item

    def recall(
        self,
        *,
        kind: str | None = None,
        key_contains: str | None = None,
        now=None,
        limit: int = 20,
    ):
        now = ensure_utc(
            now
        )

        ranked = []

        for item in (
            self._items.values()
        ):
            if (
                kind is not None
                and item.kind != kind
            ):
                continue

            if (
                key_contains is not None
                and key_contains.lower()
                not in item.key.lower()
            ):
                continue

            age_days = max(
                0.0,
                (
                    now
                    - item
                    .last_accessed_at
                ).total_seconds()
                / 86400.0,
            )

            decay = math.pow(
                0.5,
                age_days
                / self.half_life_days,
            )

            usage_bonus = min(
                0.15,
                math.log1p(
                    item.access_count
                )
                / 20.0,
            )

            score = min(
                1.0,
                item.importance
                * 0.45
                + item.confidence
                * 0.35
                + decay
                * 0.20
                + usage_bonus,
            )

            ranked.append(
                (
                    score,
                    item,
                )
            )

        ranked.sort(
            key=lambda row: (
                row[0],
                row[1].memory_id,
            ),
            reverse=True,
        )

        result = []

        for score, item in (
            ranked[:limit]
        ):
            touched = MemoryItem(
                memory_id=(
                    item.memory_id
                ),
                kind=item.kind,
                key=item.key,
                value=item.value,
                created_at=(
                    item.created_at
                ),
                last_accessed_at=(
                    now
                ),
                importance=(
                    item.importance
                ),
                confidence=(
                    item.confidence
                ),
                access_count=(
                    item.access_count
                    + 1
                ),
            )

            self._items[
                item.memory_id
            ] = touched

            result.append(
                (
                    score,
                    touched,
                )
            )

        return tuple(
            result
        )

    def count(
        self,
    ) -> int:
        return len(
            self._items
        )
