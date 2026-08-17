from __future__ import annotations

from .models import (
    AutonomyLevel,
    Critique,
    RiskLevel,
)


class AutonomyPolicy:
    def __init__(
        self,
        *,
        max_autonomy: AutonomyLevel = (
            AutonomyLevel.EXECUTE_BOUNDED
        ),
    ) -> None:
        self.max_autonomy = (
            max_autonomy
        )

    def authorize(
        self,
        *,
        requested: AutonomyLevel,
        risk: RiskLevel,
        confidence: float,
        critiques: tuple[
            Critique,
            ...,
        ],
        irreversible: bool = False,
        external_side_effect: bool = False,
    ):
        effective = min(
            requested,
            self.max_autonomy,
        )

        requires_human = False

        reasons = []

        if irreversible:
            requires_human = True

            reasons.append(
                "irreversible action"
            )

        if risk in {
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        }:
            requires_human = True

            reasons.append(
                f"{risk.value} risk"
            )

        if (
            confidence < 0.80
            and effective
            >= AutonomyLevel
            .EXECUTE_REVERSIBLE
        ):
            requires_human = True

            reasons.append(
                "insufficient confidence "
                "for autonomous execution"
            )

        if (
            external_side_effect
            and effective
            >= AutonomyLevel
            .EXECUTE_BOUNDED
        ):
            requires_human = True

            reasons.append(
                "external side effect"
            )

        if any(
            critique.severity
            in {
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            }
            for critique
            in critiques
        ):
            requires_human = True

            reasons.append(
                "high-severity critic finding"
            )

        if requires_human:
            effective = min(
                effective,
                AutonomyLevel.PREPARE,
            )

        return (
            effective,
            requires_human,
            tuple(
                reasons
            ),
        )
