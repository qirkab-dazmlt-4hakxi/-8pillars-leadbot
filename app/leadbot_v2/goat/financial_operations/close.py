from __future__ import annotations

from .models import (
    CloseFinding,
    CloseReport,
    CloseSeverity,
)


class MonthEndCloseEngine:
    def evaluate(
        self,
        *,
        entity_id: str,
        period_end,
        financial_system,
        reconciliation_report,
        anomalies=(),
        receivables_aging=None,
        payables_aging=None,
    ) -> CloseReport:
        findings = []

        trial = (
            financial_system
            .ledger
            .trial_balance()
        )

        if not trial.balanced:
            findings.append(
                CloseFinding(
                    finding_id=(
                        "ledger-unbalanced"
                    ),
                    severity=(
                        CloseSeverity.BLOCKING
                    ),
                    message=(
                        "general ledger is not balanced"
                    ),
                )
            )

        balance_sheet = (
            financial_system
            .ledger
            .balance_sheet()
        )

        if not balance_sheet.balanced:
            findings.append(
                CloseFinding(
                    finding_id=(
                        "accounting-equation"
                    ),
                    severity=(
                        CloseSeverity.BLOCKING
                    ),
                    message=(
                        "accounting equation does not reconcile"
                    ),
                )
            )

        if (
            financial_system
            .review_queue
        ):
            findings.append(
                CloseFinding(
                    finding_id=(
                        "bookkeeping-review"
                    ),
                    severity=(
                        CloseSeverity.BLOCKING
                    ),
                    message=(
                        f"{len(financial_system.review_queue)} "
                        f"bookkeeping review item(s) remain"
                    ),
                )
            )

        if (
            reconciliation_report
            is not None
            and not reconciliation_report
            .reconciled
        ):
            findings.append(
                CloseFinding(
                    finding_id=(
                        "bank-reconciliation"
                    ),
                    severity=(
                        CloseSeverity.BLOCKING
                    ),
                    message=(
                        "bank reconciliation has unmatched items"
                    ),
                )
            )

        high_anomalies = [
            anomaly
            for anomaly
            in anomalies
            if anomaly.severity.value
            in {
                "high",
                "critical",
            }
        ]

        if high_anomalies:
            findings.append(
                CloseFinding(
                    finding_id=(
                        "high-anomalies"
                    ),
                    severity=(
                        CloseSeverity.BLOCKING
                    ),
                    message=(
                        f"{len(high_anomalies)} high-severity "
                        f"financial anomaly/anomalies unresolved"
                    ),
                )
            )

        if (
            receivables_aging is not None
            and receivables_aging
            .days_90_plus
            > 0
        ):
            findings.append(
                CloseFinding(
                    finding_id=(
                        "ar-90-plus"
                    ),
                    severity=(
                        CloseSeverity.WARNING
                    ),
                    message=(
                        "90+ day receivables remain outstanding"
                    ),
                )
            )

        if (
            payables_aging is not None
            and payables_aging
            .days_90_plus
            > 0
        ):
            findings.append(
                CloseFinding(
                    finding_id=(
                        "ap-90-plus"
                    ),
                    severity=(
                        CloseSeverity.WARNING
                    ),
                    message=(
                        "90+ day payables remain outstanding"
                    ),
                )
            )

        closable = not any(
            finding.severity
            is CloseSeverity.BLOCKING
            for finding
            in findings
        )

        return CloseReport(
            entity_id=entity_id,
            period_end=(
                period_end
            ),
            closable=(
                closable
            ),
            findings=tuple(
                findings
            ),
        )
