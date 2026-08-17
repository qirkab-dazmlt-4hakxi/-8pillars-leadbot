from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BankDirection,
    BankTransaction,
    Classification,
    TransactionKind,
)


@dataclass(frozen=True)
class ClassificationRule:
    rule_id: str

    contains_any: tuple[
        str,
        ...,
    ]

    kind: TransactionKind

    counter_account_code: str | None

    confidence: float

    direction: BankDirection | None = None

    project_required: bool = False

    default_project_id: str | None = None
    default_cost_code: str | None = None
    default_vendor_id: str | None = None

    tax_category: str | None = None

    review_required: bool = False


class TransactionClassifier:
    def __init__(
        self,
    ) -> None:
        self._rules: dict[
            str,
            ClassificationRule,
        ] = {}

    def add_rule(
        self,
        rule: ClassificationRule,
    ) -> None:
        if (
            rule.rule_id
            in self._rules
        ):
            raise ValueError(
                f"duplicate classification rule: "
                f"{rule.rule_id}"
            )

        if not (
            0.0
            <= rule.confidence
            <= 1.0
        ):
            raise ValueError(
                "confidence must be in [0,1]"
            )

        self._rules[
            rule.rule_id
        ] = rule

    def classify(
        self,
        transaction: BankTransaction,
        *,
        project_id: str | None = None,
        cost_code: str | None = None,
        vendor_id: str | None = None,
    ) -> Classification:
        haystack = " ".join(
            filter(
                None,
                (
                    transaction.description,
                    transaction.merchant_name,
                ),
            )
        ).upper()

        candidates = []

        for rule in (
            self._rules.values()
        ):
            if (
                rule.direction
                is not None
                and rule.direction
                is not transaction.direction
            ):
                continue

            matches = [
                token
                for token
                in rule.contains_any
                if token.upper()
                in haystack
            ]

            if not matches:
                continue

            specificity = max(
                len(
                    token
                )
                for token
                in matches
            )

            candidates.append(
                (
                    rule.confidence,
                    specificity,
                    rule.rule_id,
                    rule,
                )
            )

        if not candidates:
            return Classification(
                transaction_id=(
                    transaction.transaction_id
                ),
                kind=(
                    TransactionKind.UNKNOWN
                ),
                counter_account_code=None,
                confidence=0.0,
                review_required=True,
                reason=(
                    "no deterministic classification rule matched"
                ),
            )

        candidates.sort(
            key=lambda row: (
                row[0],
                row[1],
                row[2],
            ),
            reverse=True,
        )

        rule = candidates[
            0
        ][
            3
        ]

        resolved_project = (
            project_id
            or rule.default_project_id
        )

        resolved_cost = (
            cost_code
            or rule.default_cost_code
        )

        resolved_vendor = (
            vendor_id
            or rule.default_vendor_id
        )

        review = bool(
            rule.review_required
        )

        reason = (
            f"matched rule "
            f"{rule.rule_id}"
        )

        if (
            rule.project_required
            and not resolved_project
        ):
            review = True

            reason += (
                "; project assignment required"
            )

        return Classification(
            transaction_id=(
                transaction.transaction_id
            ),
            kind=rule.kind,
            counter_account_code=(
                rule.counter_account_code
            ),
            confidence=(
                rule.confidence
            ),
            project_id=(
                resolved_project
            ),
            cost_code=(
                resolved_cost
            ),
            vendor_id=(
                resolved_vendor
            ),
            tax_category=(
                rule.tax_category
            ),
            review_required=(
                review
            ),
            reason=reason,
        )
