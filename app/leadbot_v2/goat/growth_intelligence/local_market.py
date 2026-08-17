from __future__ import annotations

from decimal import Decimal

from .models import (
    LocalMarket,
)


class LocalMarketScorer:
    def score(
        self,
        *,
        market_id: str,
        name: str,
        demand: float,
        competition: float,
        serviceability: float,
        average_project_value,
        strategic_value: float,
    ) -> LocalMarket:
        demand = clamp(
            demand
        )

        competition = clamp(
            competition
        )

        serviceability = clamp(
            serviceability
        )

        strategic = clamp(
            strategic_value
        )

        project_value = Decimal(
            str(
                average_project_value
            )
        )

        value_score = min(
            1.0,
            max(
                0.0,
                float(
                    project_value
                    / Decimal(
                        "250000"
                    )
                ),
            ),
        )

        score = (
            demand
            * 0.25
            + (
                1.0
                - competition
            )
            * 0.20
            + serviceability
            * 0.25
            + value_score
            * 0.15
            + strategic
            * 0.15
        )

        return LocalMarket(
            market_id=(
                market_id
            ),
            name=name,
            demand=demand,
            competition=competition,
            serviceability=(
                serviceability
            ),
            average_project_value=(
                project_value
            ),
            strategic_value=(
                strategic
            ),
            score=clamp(
                score
            ),
        )

    def rank(
        self,
        markets,
    ):
        return tuple(
            sorted(
                markets,
                key=lambda market: (
                    market.score,
                    market.market_id,
                ),
                reverse=True,
            )
        )


def clamp(
    value,
):
    return max(
        0.0,
        min(
            1.0,
            float(
                value
            ),
        ),
    )
