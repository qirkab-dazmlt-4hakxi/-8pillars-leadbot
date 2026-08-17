from __future__ import annotations

import time

from dataclasses import dataclass

from typing import Callable

from .models import (
    ExpertOpinion,
    InvariantViolation,
    RiskLevel,
    clamp01,
)


@dataclass(frozen=True)
class ExpertSpec:
    expert_id: str

    domain: str

    weight: float

    handler: Callable


class ExpertRegistry:
    def __init__(
        self,
    ) -> None:
        self._experts: dict[
            str,
            ExpertSpec,
        ] = {}

    def register(
        self,
        *,
        expert_id: str,
        domain: str,
        handler: Callable,
        weight: float = 1.0,
    ) -> None:
        if (
            expert_id
            in self._experts
        ):
            raise InvariantViolation(
                f"duplicate expert: "
                f"{expert_id}"
            )

        if weight <= 0:
            raise InvariantViolation(
                "expert weight must be positive"
            )

        self._experts[
            expert_id
        ] = ExpertSpec(
            expert_id=(
                expert_id
            ),
            domain=domain,
            weight=float(
                weight
            ),
            handler=handler,
        )

    def specs(
        self,
        domain: str | None = None,
    ):
        values = tuple(
            self._experts.values()
        )

        if domain is None:
            return values

        return tuple(
            spec
            for spec in values
            if spec.domain
            == domain
        )

    def invoke(
        self,
        expert_id: str,
        context,
    ) -> ExpertOpinion:
        spec = self._experts[
            expert_id
        ]

        started = (
            time.perf_counter_ns()
        )

        raw = spec.handler(
            context
        )

        latency_ms = (
            time.perf_counter_ns()
            - started
        ) / 1_000_000.0

        if isinstance(
            raw,
            ExpertOpinion,
        ):
            return ExpertOpinion(
                expert_id=(
                    spec.expert_id
                ),
                answer=raw.answer,
                confidence=clamp01(
                    raw.confidence
                ),
                risk=raw.risk,
                reasoning_summary=(
                    raw.reasoning_summary
                ),
                evidence_ids=tuple(
                    raw.evidence_ids
                ),
                assumptions=tuple(
                    raw.assumptions
                ),
                latency_ms=(
                    latency_ms
                ),
            )

        if not isinstance(
            raw,
            dict,
        ):
            raise TypeError(
                "expert handler must return "
                "dict or ExpertOpinion"
            )

        risk = raw.get(
            "risk",
            RiskLevel.MODERATE,
        )

        if isinstance(
            risk,
            str,
        ):
            risk = RiskLevel(
                risk
            )

        return ExpertOpinion(
            expert_id=(
                spec.expert_id
            ),
            answer=raw.get(
                "answer"
            ),
            confidence=clamp01(
                raw.get(
                    "confidence",
                    0.5,
                )
            ),
            risk=risk,
            reasoning_summary=str(
                raw.get(
                    "reasoning_summary",
                    "",
                )
            ),
            evidence_ids=tuple(
                raw.get(
                    "evidence_ids",
                    (),
                )
            ),
            assumptions=tuple(
                raw.get(
                    "assumptions",
                    (),
                )
            ),
            latency_ms=(
                latency_ms
            ),
        )

    def invoke_domain(
        self,
        domain: str,
        context,
    ) -> tuple[
        ExpertOpinion,
        ...,
    ]:
        return tuple(
            self.invoke(
                spec.expert_id,
                context,
            )
            for spec
            in self.specs(
                domain
            )
        )
