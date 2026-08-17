from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .canonical import money
from .models import CashRisk


@dataclass(frozen=True)
class CashEvent:
    event_date: date

    amount: Decimal

    label: str

    confidence: float = 1.0

    project_id: str | None = None


@dataclass(frozen=True)
class CashForecastPoint:
    horizon_days: int

    projected_cash: Decimal

    conservative_cash: Decimal


@dataclass(frozen=True)
class CashForecast:
    starting_cash: Decimal

    points: tuple[
        CashForecastPoint,
        ...,
    ]

    runway_days: float | None

    risk: CashRisk


class CashFlowForecaster:
    def forecast(
        self,
        *,
        starting_cash,
        as_of: date,
        events,
        horizons=(
            7,
            30,
            60,
            90,
        ),
        average_daily_net_burn=0,
    ) -> CashForecast:
        starting_cash = money(
            starting_cash
        )

        events = tuple(
            events
        )

        points = []

        risk = CashRisk.LOW

        for horizon in horizons:
            cutoff = (
                as_of
                + timedelta(
                    days=int(
                        horizon
                    )
                )
            )

            projected = (
                starting_cash
            )

            conservative = (
                starting_cash
            )

            for event in events:
                if not (
                    as_of
                    < event.event_date
                    <= cutoff
                ):
                    continue

                amount = money(
                    event.amount
                )

                projected += amount

                if amount >= 0:
                    confidence = max(
                        0.0,
                        min(
                            1.0,
                            float(
                                event.confidence
                            ),
                        ),
                    )

                    conservative += money(
                        amount
                        * Decimal(
                            str(
                                confidence
                            )
                        )
                    )

                else:
                    conservative += amount

            projected = money(
                projected
            )

            conservative = money(
                conservative
            )

            points.append(
                CashForecastPoint(
                    horizon_days=(
                        int(
                            horizon
                        )
                    ),
                    projected_cash=(
                        projected
                    ),
                    conservative_cash=(
                        conservative
                    ),
                )
            )

            if conservative < 0:
                risk = max_risk(
                    risk,
                    CashRisk.HIGH,
                )

        daily_burn = money(
            average_daily_net_burn
        )

        runway = None

        if daily_burn > 0:
            runway = float(
                starting_cash
                / daily_burn
            )

            if runway < 14:
                risk = CashRisk.CRITICAL

            elif runway < 30:
                risk = max_risk(
                    risk,
                    CashRisk.HIGH,
                )

            elif runway < 60:
                risk = max_risk(
                    risk,
                    CashRisk.MODERATE,
                )

        return CashForecast(
            starting_cash=(
                starting_cash
            ),
            points=tuple(
                points
            ),
            runway_days=runway,
            risk=risk,
        )


def max_risk(
    a,
    b,
):
    rank = {
        CashRisk.LOW:
            1,
        CashRisk.MODERATE:
            2,
        CashRisk.HIGH:
            3,
        CashRisk.CRITICAL:
            4,
    }

    return (
        a
        if rank[a] >= rank[b]
        else b
    )
