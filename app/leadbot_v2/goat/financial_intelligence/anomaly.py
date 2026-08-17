from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import median

from .canonical import money


class AnomalySeverity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class FinancialAnomaly:
    anomaly_type: str

    severity: AnomalySeverity

    transaction_ids: tuple[
        str,
        ...,
    ]

    message: str


class FinancialAnomalyDetector:
    def __init__(
        self,
        *,
        large_transaction_threshold=10000,
    ) -> None:
        self.large_transaction_threshold = (
            money(
                large_transaction_threshold
            )
        )

    def detect(
        self,
        transactions,
    ) -> tuple[
        FinancialAnomaly,
        ...,
    ]:
        transactions = tuple(
            transactions
        )

        anomalies = []

        anomalies.extend(
            self._duplicates(
                transactions
            )
        )

        anomalies.extend(
            self._large_transactions(
                transactions
            )
        )

        anomalies.extend(
            self._merchant_outliers(
                transactions
            )
        )

        return tuple(
            anomalies
        )

    def _duplicates(
        self,
        transactions,
    ):
        anomalies = []

        for index, left in enumerate(
            transactions
        ):
            for right in transactions[
                index + 1:
            ]:
                if (
                    left.entity_id
                    != right.entity_id
                ):
                    continue

                if (
                    left.account_id
                    != right.account_id
                ):
                    continue

                if (
                    left.transaction_id
                    == right.transaction_id
                ):
                    continue

                if (
                    left.direction
                    is not right.direction
                ):
                    continue

                if (
                    money(
                        left.amount
                    )
                    != money(
                        right.amount
                    )
                ):
                    continue

                left_name = (
                    left.merchant_name
                    or left.description
                ).strip().lower()

                right_name = (
                    right.merchant_name
                    or right.description
                ).strip().lower()

                if left_name != right_name:
                    continue

                if abs(
                    (
                        left.posted_date
                        - right.posted_date
                    ).days
                ) > 1:
                    continue

                anomalies.append(
                    FinancialAnomaly(
                        anomaly_type=(
                            "possible_duplicate"
                        ),
                        severity=(
                            AnomalySeverity.HIGH
                        ),
                        transaction_ids=(
                            left.transaction_id,
                            right.transaction_id,
                        ),
                        message=(
                            "same entity, account, merchant, amount "
                            "and near-identical posting date"
                        ),
                    )
                )

        return anomalies

    def _large_transactions(
        self,
        transactions,
    ):
        return [
            FinancialAnomaly(
                anomaly_type=(
                    "large_transaction"
                ),
                severity=(
                    AnomalySeverity.MODERATE
                ),
                transaction_ids=(
                    transaction.transaction_id,
                ),
                message=(
                    f"transaction exceeds configured "
                    f"review threshold: "
                    f"{transaction.amount}"
                ),
            )
            for transaction
            in transactions
            if (
                transaction.amount
                >= self.large_transaction_threshold
            )
        ]

    def _merchant_outliers(
        self,
        transactions,
    ):
        by_merchant = {}

        for transaction in transactions:
            merchant = (
                transaction.merchant_name
                or transaction.description
            ).strip().lower()

            key = (
                transaction.entity_id,
                merchant,
            )

            by_merchant.setdefault(
                key,
                [],
            ).append(
                transaction
            )

        result = []

        for (
            entity_id,
            merchant,
        ), rows in (
            by_merchant.items()
        ):
            if len(rows) < 4:
                continue

            amounts = sorted(
                float(
                    row.amount
                )
                for row
                in rows
            )

            baseline = median(
                amounts
            )

            if baseline <= 0:
                continue

            for row in rows:
                if (
                    float(
                        row.amount
                    )
                    >= baseline * 3.0
                ):
                    result.append(
                        FinancialAnomaly(
                            anomaly_type=(
                                "merchant_amount_outlier"
                            ),
                            severity=(
                                AnomalySeverity.MODERATE
                            ),
                            transaction_ids=(
                                row.transaction_id,
                            ),
                            message=(
                                f"{entity_id}:{merchant} amount "
                                f"is at least 3x merchant median"
                            ),
                        )
                    )

        return result
