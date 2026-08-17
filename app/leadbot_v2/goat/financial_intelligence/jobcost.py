from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .canonical import money
from .models import CashRisk


@dataclass(frozen=True)
class JobFinancialState:
    project_id: str

    original_contract: Decimal
    approved_change_orders: Decimal

    original_estimated_cost: Decimal

    actual_cost_to_date: Decimal
    committed_remaining: Decimal
    forecast_uncommitted_cost: Decimal

    earned_value: Decimal
    planned_value: Decimal

    cash_paid: Decimal
    commitments_due_before_collections: Decimal
    cash_collected: Decimal


@dataclass(frozen=True)
class JobCostSnapshot:
    project_id: str

    revised_contract: Decimal

    estimate_at_completion: Decimal

    projected_gross_profit: Decimal

    projected_margin: float

    original_margin: float

    margin_erosion: float

    cost_performance_index: float | None
    schedule_performance_index: float | None

    cash_exposure: Decimal

    risk: CashRisk


class JobCostAnalyzer:
    def analyze(
        self,
        state: JobFinancialState,
    ) -> JobCostSnapshot:
        contract = money(
            state.original_contract
            + state.approved_change_orders
        )

        eac = money(
            state.actual_cost_to_date
            + state.committed_remaining
            + state.forecast_uncommitted_cost
        )

        profit = money(
            contract
            - eac
        )

        projected_margin = (
            float(
                profit / contract
            )
            if contract
            else 0.0
        )

        original_profit = money(
            state.original_contract
            - state.original_estimated_cost
        )

        original_margin = (
            float(
                original_profit
                / state.original_contract
            )
            if state.original_contract
            else 0.0
        )

        erosion = (
            original_margin
            - projected_margin
        )

        cpi = (
            float(
                state.earned_value
                / state.actual_cost_to_date
            )
            if (
                state.actual_cost_to_date
                > 0
            )
            else None
        )

        spi = (
            float(
                state.earned_value
                / state.planned_value
            )
            if (
                state.planned_value
                > 0
            )
            else None
        )

        cash_exposure = money(
            state.cash_paid
            + state.commitments_due_before_collections
            - state.cash_collected
        )

        risk = CashRisk.LOW

        if (
            projected_margin < 0
            or (
                cpi is not None
                and cpi < 0.80
            )
        ):
            risk = CashRisk.CRITICAL

        elif (
            erosion >= 0.10
            or (
                cpi is not None
                and cpi < 0.90
            )
        ):
            risk = CashRisk.HIGH

        elif (
            erosion >= 0.05
            or (
                cpi is not None
                and cpi < 1.0
            )
            or (
                spi is not None
                and spi < 0.90
            )
        ):
            risk = CashRisk.MODERATE

        return JobCostSnapshot(
            project_id=(
                state.project_id
            ),
            revised_contract=contract,
            estimate_at_completion=eac,
            projected_gross_profit=(
                profit
            ),
            projected_margin=(
                projected_margin
            ),
            original_margin=(
                original_margin
            ),
            margin_erosion=(
                erosion
            ),
            cost_performance_index=(
                cpi
            ),
            schedule_performance_index=(
                spi
            ),
            cash_exposure=(
                cash_exposure
            ),
            risk=risk,
        )
