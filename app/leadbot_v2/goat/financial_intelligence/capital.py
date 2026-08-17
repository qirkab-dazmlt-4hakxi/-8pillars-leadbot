from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .canonical import money


@dataclass(frozen=True)
class CapitalOption:
    option_id: str

    name: str

    required_capital: Decimal

    expected_return_rate: float

    downside_loss_rate: float

    liquidity_days: int

    strategic_value: float

    tax_efficiency: float

    risk_score: float


@dataclass(frozen=True)
class CapitalRecommendation:
    option_id: str

    name: str

    score: float

    deployable: bool

    reason: str


@dataclass(frozen=True)
class CapitalAllocationPlan:
    available_cash: Decimal

    required_operating_reserve: Decimal

    deployable_cash: Decimal

    recommendations: tuple[
        CapitalRecommendation,
        ...,
    ]


class CapitalAllocator:
    def rank(
        self,
        *,
        available_cash,
        required_operating_reserve,
        options,
    ) -> CapitalAllocationPlan:
        available = money(
            available_cash
        )

        reserve = money(
            required_operating_reserve
        )

        deployable = money(
            max(
                Decimal(
                    "0.00"
                ),
                available
                - reserve,
            )
        )

        recommendations = []

        for option in options:
            required = money(
                option.required_capital
            )

            liquidity_score = (
                1.0
                / (
                    1.0
                    + max(
                        0,
                        option.liquidity_days,
                    )
                    / 90.0
                )
            )

            score = (
                option.expected_return_rate
                * 0.35
                + option.strategic_value
                * 0.25
                + liquidity_score
                * 0.15
                + option.tax_efficiency
                * 0.10
                + (
                    1.0
                    - option.risk_score
                )
                * 0.15
                - option.downside_loss_rate
                * 0.20
            )

            can_deploy = (
                required
                <= deployable
            )

            reason = (
                "within deployable capital envelope"
                if can_deploy
                else (
                    "blocked: required capital would "
                    "violate operating reserve"
                )
            )

            recommendations.append(
                CapitalRecommendation(
                    option_id=(
                        option.option_id
                    ),
                    name=(
                        option.name
                    ),
                    score=(
                        score
                    ),
                    deployable=(
                        can_deploy
                    ),
                    reason=reason,
                )
            )

        recommendations.sort(
            key=lambda row: (
                row.deployable,
                row.score,
                row.option_id,
            ),
            reverse=True,
        )

        return CapitalAllocationPlan(
            available_cash=available,
            required_operating_reserve=(
                reserve
            ),
            deployable_cash=(
                deployable
            ),
            recommendations=tuple(
                recommendations
            ),
        )
