from __future__ import annotations

from .models import (
    ProfitabilityAlert,
    SurveillanceSeverity,
)


class ProfitabilitySurveillance:
    def __init__(
        self,
        *,
        watch_margin: float = 0.15,
        high_margin: float = 0.08,
        erosion_watch: float = 0.05,
        erosion_high: float = 0.10,
    ) -> None:
        self.watch_margin = float(
            watch_margin
        )

        self.high_margin = float(
            high_margin
        )

        self.erosion_watch = float(
            erosion_watch
        )

        self.erosion_high = float(
            erosion_high
        )

    def evaluate(
        self,
        snapshot,
    ) -> ProfitabilityAlert:
        margin = float(
            snapshot.projected_margin
        )

        erosion = float(
            snapshot.margin_erosion
        )

        if (
            margin < 0
            or snapshot.risk.value
            == "critical"
        ):
            severity = (
                SurveillanceSeverity.CRITICAL
            )

            message = (
                "project is projected to lose money "
                "or has critical cost performance"
            )

        elif (
            margin < self.high_margin
            or erosion >= self.erosion_high
            or snapshot.risk.value
            == "high"
        ):
            severity = (
                SurveillanceSeverity.HIGH
            )

            message = (
                "project profitability requires immediate "
                "management intervention"
            )

        elif (
            margin < self.watch_margin
            or erosion >= self.erosion_watch
            or snapshot.risk.value
            == "moderate"
        ):
            severity = (
                SurveillanceSeverity.WATCH
            )

            message = (
                "project margin/cost trend is degrading"
            )

        else:
            severity = (
                SurveillanceSeverity.INFO
            )

            message = (
                "project profitability remains "
                "inside configured control band"
            )

        return ProfitabilityAlert(
            project_id=(
                snapshot.project_id
            ),
            severity=severity,
            projected_margin=(
                margin
            ),
            margin_erosion=(
                erosion
            ),
            cash_exposure=(
                snapshot.cash_exposure
            ),
            message=message,
        )
