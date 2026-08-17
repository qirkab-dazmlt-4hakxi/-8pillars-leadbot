from __future__ import annotations

from dataclasses import (
    dataclass,
)

from typing import Callable

from .models import (
    Critique,
    RiskLevel,
    clamp01,
)


@dataclass(frozen=True)
class CriticSpec:
    critic_id: str

    handler: Callable


class CriticNetwork:
    def __init__(
        self,
    ) -> None:
        self._critics: dict[
            str,
            CriticSpec,
        ] = {}

        self.register(
            "uncertainty",
            self._uncertainty_critic,
        )

        self.register(
            "evidence",
            self._evidence_critic,
        )

        self.register(
            "disagreement",
            self._disagreement_critic,
        )

    def register(
        self,
        critic_id: str,
        handler: Callable,
    ) -> None:
        if (
            critic_id
            in self._critics
        ):
            raise ValueError(
                f"duplicate critic: "
                f"{critic_id}"
            )

        self._critics[
            critic_id
        ] = CriticSpec(
            critic_id=(
                critic_id
            ),
            handler=handler,
        )

    def run(
        self,
        context,
    ) -> tuple[
        Critique,
        ...,
    ]:
        result = []

        for spec in (
            self._critics.values()
        ):
            critique = spec.handler(
                context
            )

            if critique is None:
                continue

            if isinstance(
                critique,
                Critique,
            ):
                result.append(
                    critique
                )

                continue

            if isinstance(
                critique,
                (
                    list,
                    tuple,
                ),
            ):
                result.extend(
                    critique
                )

                continue

            raise TypeError(
                "critic must return Critique, "
                "iterable, or None"
            )

        severity_order = {
            RiskLevel.CRITICAL:
                4,

            RiskLevel.HIGH:
                3,

            RiskLevel.MODERATE:
                2,

            RiskLevel.LOW:
                1,
        }

        result.sort(
            key=lambda critique: (
                severity_order[
                    critique.severity
                ],
                critique.confidence,
                critique.critic_id,
            ),
            reverse=True,
        )

        return tuple(
            result
        )

    @staticmethod
    def _uncertainty_critic(
        context,
    ):
        confidence = clamp01(
            float(
                context.get(
                    "confidence",
                    0.0,
                )
            )
        )

        if confidence >= 0.70:
            return None

        severity = (
            RiskLevel.HIGH
            if confidence < 0.45
            else RiskLevel.MODERATE
        )

        return Critique(
            critic_id="uncertainty",
            severity=severity,
            issue=(
                f"decision confidence is only "
                f"{confidence:.3f}"
            ),
            recommendation=(
                "collect additional evidence "
                "or require human review"
            ),
            confidence=1.0,
        )

    @staticmethod
    def _evidence_critic(
        context,
    ):
        evidence_count = int(
            context.get(
                "evidence_count",
                0,
            )
        )

        if evidence_count >= 2:
            return None

        return Critique(
            critic_id="evidence",
            severity=(
                RiskLevel.HIGH
            ),
            issue=(
                "decision is weakly evidenced"
            ),
            recommendation=(
                "obtain independent corroborating evidence"
            ),
            confidence=0.95,
        )

    @staticmethod
    def _disagreement_critic(
        context,
    ):
        opinions = tuple(
            context.get(
                "opinions",
                (),
            )
        )

        distinct = {
            canonical_answer(
                opinion.answer
            )
            for opinion
            in opinions
        }

        if len(
            distinct
        ) <= 1:
            return None

        return Critique(
            critic_id="disagreement",
            severity=(
                RiskLevel.MODERATE
            ),
            issue=(
                f"{len(distinct)} materially "
                f"different expert answers remain"
            ),
            recommendation=(
                "inspect conflicting assumptions "
                "before execution"
            ),
            confidence=0.90,
        )


def canonical_answer(
    value,
) -> str:
    return repr(
        value
    )
