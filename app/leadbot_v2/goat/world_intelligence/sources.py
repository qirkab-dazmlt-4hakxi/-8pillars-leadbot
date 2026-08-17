from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import (
    SourceAuthority,
    SourceHealth,
    SourceHealthState,
    SourcePolicyError,
)


AUTHORITY_WEIGHT = {
    SourceAuthority.OFFICIAL:
        1.00,

    SourceAuthority.PRIMARY:
        0.92,

    SourceAuthority.PROFESSIONAL:
        0.82,

    SourceAuthority.REPUTABLE_SECONDARY:
        0.70,

    SourceAuthority.COMMUNITY:
        0.45,

    SourceAuthority.UNVERIFIED:
        0.20,
}


class SourceRegistry:
    def __init__(
        self,
    ) -> None:
        self._sources = {}

    def register(
        self,
        source,
    ) -> None:
        if not source.source_id.strip():
            raise SourcePolicyError(
                "source_id required"
            )

        if source.source_id in self._sources:
            raise SourcePolicyError(
                "duplicate source"
            )

        if not (
            0.0
            <= source.base_confidence
            <= 1.0
        ):
            raise SourcePolicyError(
                "invalid source confidence"
            )

        self._sources[
            source.source_id
        ] = source

    def get(
        self,
        source_id,
    ):
        try:
            return self._sources[
                source_id
            ]
        except KeyError as exc:
            raise SourcePolicyError(
                f"unknown source: "
                f"{source_id}"
            ) from exc

    def require_domain(
        self,
        source_id,
        domain,
    ):
        source = self.get(
            source_id
        )

        if not source.enabled:
            raise SourcePolicyError(
                "source disabled"
            )

        if domain not in source.domains:
            raise SourcePolicyError(
                f"source is not authorized "
                f"for domain {domain.value}"
            )

        return source


class SourceHealthTracker:
    def __init__(
        self,
        *,
        failure_quarantine_threshold=5,
    ) -> None:
        self.failure_quarantine_threshold = int(
            failure_quarantine_threshold
        )

        self._stats = {}

    def _row(
        self,
        source_id,
    ):
        return self._stats.setdefault(
            source_id,
            {
                "successes":
                    0,

                "failures":
                    0,

                "consecutive_failures":
                    0,

                "last_success_at":
                    None,

                "last_failure_at":
                    None,
            },
        )

    def success(
        self,
        source_id,
        *,
        when=None,
    ):
        when = (
            when
            or datetime.now(
                timezone.utc
            )
        )

        row = self._row(
            source_id
        )

        row[
            "successes"
        ] += 1

        row[
            "consecutive_failures"
        ] = 0

        row[
            "last_success_at"
        ] = when

    def failure(
        self,
        source_id,
        *,
        when=None,
    ):
        when = (
            when
            or datetime.now(
                timezone.utc
            )
        )

        row = self._row(
            source_id
        )

        row[
            "failures"
        ] += 1

        row[
            "consecutive_failures"
        ] += 1

        row[
            "last_failure_at"
        ] = when

    def health(
        self,
        source_id,
    ):
        row = self._row(
            source_id
        )

        total = (
            row[
                "successes"
            ]
            + row[
                "failures"
            ]
        )

        success_rate = (
            1.0
            if total == 0
            else (
                row[
                    "successes"
                ]
                / total
            )
        )

        consecutive = row[
            "consecutive_failures"
        ]

        if (
            consecutive
            >= self.failure_quarantine_threshold
        ):
            state = (
                SourceHealthState.QUARANTINED
            )

        elif consecutive >= 2:
            state = (
                SourceHealthState.DEGRADED
            )

        elif (
            total >= 5
            and success_rate < 0.5
        ):
            state = (
                SourceHealthState.FAILED
            )

        else:
            state = (
                SourceHealthState.HEALTHY
            )

        return SourceHealth(
            source_id=(
                source_id
            ),
            state=state,
            success_rate=(
                success_rate
            ),
            consecutive_failures=(
                consecutive
            ),
            last_success_at=(
                row[
                    "last_success_at"
                ]
            ),
            last_failure_at=(
                row[
                    "last_failure_at"
                ]
            ),
        )
