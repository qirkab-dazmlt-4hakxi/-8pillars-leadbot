from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .models import (
    Classification,
    TransactionKind,
)


class TaxTreatment(str, Enum):
    BUSINESS_EXPENSE_CANDIDATE = (
        "business_expense_candidate"
    )

    REVENUE_CANDIDATE = (
        "revenue_candidate"
    )

    TRANSFER_NON_TAXABLE = (
        "transfer_non_taxable"
    )

    OWNER_EQUITY = (
        "owner_equity"
    )

    CAPITAL_ASSET_REVIEW = (
        "capital_asset_review"
    )

    LOAN_SPLIT_REVIEW = (
        "loan_split_review"
    )

    PAYROLL_REVIEW = (
        "payroll_review"
    )

    UNKNOWN_REVIEW = (
        "unknown_review"
    )


@dataclass(frozen=True)
class TaxAssessment:
    treatment: TaxTreatment

    tax_code: str

    requires_documentation: bool

    requires_review: bool

    rule_version: str

    reason: str


@dataclass(frozen=True)
class TaxRule:
    rule_id: str

    kind: TransactionKind

    treatment: TaxTreatment

    tax_code: str

    requires_documentation: bool

    requires_review: bool

    reason: str


@dataclass(frozen=True)
class TaxRuleSet:
    version: str

    effective_from: date

    effective_to: date | None

    rules: tuple[
        TaxRule,
        ...,
    ]


class TaxRuleEngine:
    def __init__(
        self,
    ) -> None:
        self._sets: list[
            TaxRuleSet
        ] = []

    def register(
        self,
        rule_set: TaxRuleSet,
    ) -> None:
        self._sets.append(
            rule_set
        )

        self._sets.sort(
            key=lambda rules:
                rules.effective_from
        )

    def active_set(
        self,
        on_date: date,
    ) -> TaxRuleSet:
        active = [
            rules
            for rules
            in self._sets
            if (
                rules.effective_from
                <= on_date
                and (
                    rules.effective_to
                    is None
                    or on_date
                    <= rules.effective_to
                )
            )
        ]

        if not active:
            raise RuntimeError(
                "no tax rule set covers date"
            )

        return active[
            -1
        ]

    def assess(
        self,
        classification: Classification,
        *,
        on_date: date,
    ) -> TaxAssessment:
        rules = self.active_set(
            on_date
        )

        for rule in rules.rules:
            if (
                rule.kind
                is classification.kind
            ):
                return TaxAssessment(
                    treatment=(
                        rule.treatment
                    ),
                    tax_code=(
                        rule.tax_code
                    ),
                    requires_documentation=(
                        rule.requires_documentation
                    ),
                    requires_review=(
                        rule.requires_review
                    ),
                    rule_version=(
                        rules.version
                    ),
                    reason=(
                        rule.reason
                    ),
                )

        return TaxAssessment(
            treatment=(
                TaxTreatment.UNKNOWN_REVIEW
            ),
            tax_code=(
                "TAX-REVIEW"
            ),
            requires_documentation=True,
            requires_review=True,
            rule_version=(
                rules.version
            ),
            reason=(
                "no tax rule matched"
            ),
        )


def default_tax_engine(
) -> TaxRuleEngine:
    engine = (
        TaxRuleEngine()
    )

    rules = (
        TaxRule(
            rule_id="expense",
            kind=(
                TransactionKind.EXPENSE
            ),
            treatment=(
                TaxTreatment
                .BUSINESS_EXPENSE_CANDIDATE
            ),
            tax_code=(
                "BUSINESS-EXPENSE-CANDIDATE"
            ),
            requires_documentation=True,
            requires_review=False,
            reason=(
                "business expense candidate; final tax treatment "
                "remains dependent on facts and current tax rules"
            ),
        ),

        TaxRule(
            rule_id="revenue",
            kind=(
                TransactionKind.REVENUE
            ),
            treatment=(
                TaxTreatment.REVENUE_CANDIDATE
            ),
            tax_code=(
                "REVENUE-CANDIDATE"
            ),
            requires_documentation=True,
            requires_review=False,
            reason=(
                "business revenue candidate"
            ),
        ),

        TaxRule(
            rule_id="transfer",
            kind=(
                TransactionKind.TRANSFER
            ),
            treatment=(
                TaxTreatment
                .TRANSFER_NON_TAXABLE
            ),
            tax_code="TRANSFER",
            requires_documentation=False,
            requires_review=False,
            reason=(
                "internal transfer is not itself revenue or expense"
            ),
        ),

        TaxRule(
            rule_id="credit-card-payment",
            kind=(
                TransactionKind
                .CREDIT_CARD_PAYMENT
            ),
            treatment=(
                TaxTreatment
                .TRANSFER_NON_TAXABLE
            ),
            tax_code=(
                "LIABILITY-PAYMENT"
            ),
            requires_documentation=False,
            requires_review=False,
            reason=(
                "credit-card payment reduces liability and "
                "must not duplicate underlying purchases"
            ),
        ),

        TaxRule(
            rule_id="owner-draw",
            kind=(
                TransactionKind.OWNER_DRAW
            ),
            treatment=(
                TaxTreatment.OWNER_EQUITY
            ),
            tax_code=(
                "OWNER-DISTRIBUTION"
            ),
            requires_documentation=True,
            requires_review=False,
            reason=(
                "owner distribution is equity activity"
            ),
        ),

        TaxRule(
            rule_id="capital-contribution",
            kind=(
                TransactionKind
                .CAPITAL_CONTRIBUTION
            ),
            treatment=(
                TaxTreatment.OWNER_EQUITY
            ),
            tax_code=(
                "OWNER-CONTRIBUTION"
            ),
            requires_documentation=True,
            requires_review=False,
            reason=(
                "owner contribution is equity activity"
            ),
        ),

        TaxRule(
            rule_id="capital-asset",
            kind=(
                TransactionKind
                .CAPITAL_ASSET_PURCHASE
            ),
            treatment=(
                TaxTreatment
                .CAPITAL_ASSET_REVIEW
            ),
            tax_code=(
                "CAPITAL-ASSET-REVIEW"
            ),
            requires_documentation=True,
            requires_review=True,
            reason=(
                "capitalization, basis and recovery treatment "
                "must be determined before final tax posting"
            ),
        ),

        TaxRule(
            rule_id="loan-payment",
            kind=(
                TransactionKind.LOAN_PAYMENT
            ),
            treatment=(
                TaxTreatment
                .LOAN_SPLIT_REVIEW
            ),
            tax_code=(
                "LOAN-SPLIT-REVIEW"
            ),
            requires_documentation=True,
            requires_review=True,
            reason=(
                "principal and interest require separation"
            ),
        ),

        TaxRule(
            rule_id="payroll",
            kind=(
                TransactionKind.PAYROLL
            ),
            treatment=(
                TaxTreatment.PAYROLL_REVIEW
            ),
            tax_code=(
                "PAYROLL-SPLIT-REVIEW"
            ),
            requires_documentation=True,
            requires_review=True,
            reason=(
                "gross wages, withholding and employer liabilities "
                "require payroll detail"
            ),
        ),

        TaxRule(
            rule_id="unknown",
            kind=(
                TransactionKind.UNKNOWN
            ),
            treatment=(
                TaxTreatment.UNKNOWN_REVIEW
            ),
            tax_code=(
                "TAX-REVIEW"
            ),
            requires_documentation=True,
            requires_review=True,
            reason=(
                "unknown transaction requires classification"
            ),
        ),
    )

    engine.register(
        TaxRuleSet(
            version="GOAT-TAX-BASE-1",
            effective_from=(
                date(
                    2000,
                    1,
                    1,
                )
            ),
            effective_to=None,
            rules=rules,
        )
    )

    return engine
