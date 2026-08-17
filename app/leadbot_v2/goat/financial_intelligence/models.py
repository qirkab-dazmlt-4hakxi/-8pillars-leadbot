from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


ZERO = Decimal("0.00")


class FinancialError(RuntimeError):
    pass


class AccountingInvariantError(FinancialError):
    pass


class EntityIsolationError(FinancialError):
    pass


class AccountClass(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    COGS = "cogs"
    EXPENSE = "expense"
    OTHER_INCOME = "other_income"
    OTHER_EXPENSE = "other_expense"


class BankDirection(str, Enum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class TransactionKind(str, Enum):
    EXPENSE = "expense"
    REVENUE = "revenue"
    TRANSFER = "transfer"
    CREDIT_CARD_PAYMENT = "credit_card_payment"
    LOAN_PAYMENT = "loan_payment"
    OWNER_DRAW = "owner_draw"
    CAPITAL_CONTRIBUTION = "capital_contribution"
    PAYROLL = "payroll"
    CAPITAL_ASSET_PURCHASE = "capital_asset_purchase"
    UNKNOWN = "unknown"


class PostingStatus(str, Enum):
    AUTO_POSTED = "auto_posted"
    REVIEW_REQUIRED = "review_required"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class CashRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ChartAccount:
    code: str
    name: str

    account_class: AccountClass

    active: bool = True

    description: str = ""


@dataclass(frozen=True)
class JournalLine:
    account_code: str

    debit: Decimal = ZERO
    credit: Decimal = ZERO

    project_id: str | None = None
    cost_code: str | None = None
    vendor_id: str | None = None

    tax_code: str | None = None

    memo: str = ""


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str

    entity_id: str

    entry_date: date

    source_type: str
    source_id: str

    memo: str

    lines: tuple[
        JournalLine,
        ...,
    ]

    created_at: datetime


@dataclass(frozen=True)
class BankTransaction:
    transaction_id: str

    entity_id: str

    provider: str
    account_id: str

    posted_date: date

    amount: Decimal

    direction: BankDirection

    description: str
    merchant_name: str | None

    pending: bool

    external_hash: str

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    @property
    def signed_amount(
        self,
    ) -> Decimal:
        if (
            self.direction
            is BankDirection.INFLOW
        ):
            return self.amount

        return -self.amount


@dataclass(frozen=True)
class Classification:
    transaction_id: str

    kind: TransactionKind

    counter_account_code: str | None

    confidence: float

    project_id: str | None = None
    cost_code: str | None = None
    vendor_id: str | None = None

    tax_category: str | None = None

    review_required: bool = False

    reason: str = ""


@dataclass(frozen=True)
class TrialBalance:
    total_debits: Decimal
    total_credits: Decimal

    balanced: bool


@dataclass(frozen=True)
class IncomeStatement:
    revenue: Decimal
    cogs: Decimal

    gross_profit: Decimal

    operating_expense: Decimal

    other_income: Decimal
    other_expense: Decimal

    net_income: Decimal


@dataclass(frozen=True)
class BalanceSheet:
    assets: Decimal

    liabilities: Decimal
    equity: Decimal

    current_period_income: Decimal

    accounting_equation_difference: Decimal

    balanced: bool


@dataclass(frozen=True)
class FinancialHealth:
    ledger_balanced: bool

    open_review_items: int

    unreconciled_transactions: int

    cash_risk: CashRisk

    project_count: int
    at_risk_projects: int


def utcnow(
) -> datetime:
    return datetime.now(
        timezone.utc
    )
