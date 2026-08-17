from __future__ import annotations

import time

from .models import (
    QualificationResult,
)


class QualificationSuite:
    def __init__(
        self,
    ) -> None:
        self._checks = []

    def add(
        self,
        name,
        check,
    ) -> None:
        self._checks.append(
            (
                name,
                check,
            )
        )

    def run(
        self,
    ) -> tuple[
        QualificationResult,
        ...,
    ]:
        results = []

        for name, check in (
            self._checks
        ):
            started = (
                time.perf_counter_ns()
            )

            try:
                details = check()

                passed = True

                details = (
                    "pass"
                    if details is None
                    else str(
                        details
                    )
                )

            except Exception as exc:
                passed = False

                details = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

            duration_ms = (
                time.perf_counter_ns()
                - started
            ) / 1_000_000.0

            results.append(
                QualificationResult(
                    name=name,
                    passed=passed,
                    details=details,
                    duration_ms=(
                        duration_ms
                    ),
                )
            )

        return tuple(
            results
        )

    @staticmethod
    def require_all(
        results,
    ) -> None:
        failures = [
            result
            for result
            in results
            if not result.passed
        ]

        if failures:
            joined = "; ".join(
                f"{result.name}: "
                f"{result.details}"
                for result
                in failures
            )

            raise RuntimeError(
                f"qualification failure: "
                f"{joined}"
            )
