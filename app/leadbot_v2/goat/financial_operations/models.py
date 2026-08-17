from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


class FinanceOperationsError(RuntimeError):
    pass


class ProviderPolicyError(FinanceOperationsError):
    pass


class SecretResolutionError(FinanceOperationsError):
    pass


class SynchronizationError(FinanceOperationsError):
    pass


class DocumentMatchError(FinanceOperationsError):
    pass


class CloseBlockedError(FinanceOperationsError):
    pass


class ProviderCapability(str, Enum):
    ACCOUNTS_READ = "accounts.read"
    TRANSACTIONS_READ = "transactions.read"


class ProviderHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class InvoiceStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"


class OpenItemStatus(str, Enum):
    OPEN = "open"
    PARTIAL = "partial"
    SETTLED = "settled"
    DISPUTED = "disputed"
    VOID = "void"


class CloseSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class SurveillanceSeverity(str, Enum):
    INFO = "info"
    WATCH = "watch"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SecretRef:
    name: str


@dataclass(frozen=True)
class ProviderRegistration:
    provider_name: str

    capabilities: frozenset[
        ProviderCapability,
    ]

    secret_refs: tuple[
        SecretRef,
        ...,
    ] = ()

    enabled: bool = True


@dataclass(frozen=True)
class ProviderHealth:
    provider_name: str

    state: ProviderHealthState

    message: str = ""


@dataclass(frozen=True)
class ExternalAccount:
    provider_name: str

    entity_id: str
    external_account_id: str

    display_name: str
    account_type: str

    current_balance: Decimal | None = None
    available_balance: Decimal | None = None


@dataclass(frozen=True)
class ExternalTransaction:
    provider_name: str

    entity_id: str
    external_account_id: str

    external_transaction_id: str

    posted_date: date

    signed_amount: Decimal

    description: str

    merchant_name: str | None = None

    pending: bool = False

    revision_token: str | None = None

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ProviderTransactionPage:
    transactions: tuple[
        ExternalTransaction,
        ...,
    ]

    next_cursor: str | None

    has_more: bool


@dataclass(frozen=True)
class AccountRoute:
    entity_id: str

    provider_name: str
    external_account_id: str

    ledger_account_code: str


@dataclass(frozen=True)
class SyncCursor:
    provider_name: str

    entity_id: str
    external_account_id: str

    cursor: str | None

    updated_at: datetime


@dataclass(frozen=True)
class SyncCorrection:
    provider_name: str

    entity_id: str
    external_account_id: str

    external_transaction_id: str

    previous_fingerprint: str
    new_fingerprint: str

    reason: str


@dataclass(frozen=True)
class SyncResult:
    provider_name: str

    entity_id: str

    accounts_seen: int

    transactions_seen: int

    accepted_posted: int

    staged_pending: int

    duplicates: int

    corrections: tuple[
        SyncCorrection,
        ...,
    ]

    next_cursors: tuple[
        SyncCursor,
        ...,
    ]


@dataclass(frozen=True)
class InvoiceLine:
    line_id: str

    description: str

    quantity: Decimal
    unit_price: Decimal

    amount: Decimal

    cost_code: str | None = None


@dataclass(frozen=True)
class Invoice:
    invoice_id: str

    entity_id: str

    vendor_id: str

    invoice_number: str

    invoice_date: date
    due_date: date

    amount: Decimal

    project_id: str | None = None

    lines: tuple[
        InvoiceLine,
        ...,
    ] = ()

    status: InvoiceStatus = (
        InvoiceStatus.OPEN
    )

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class Receipt:
    receipt_id: str

    entity_id: str

    merchant_name: str

    receipt_date: date

    amount: Decimal

    project_id: str | None = None

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class DocumentMatch:
    document_id: str

    transaction_id: str

    confidence: float

    amount_score: float
    date_score: float
    counterparty_score: float
    project_score: float

    reason: str


@dataclass(frozen=True)
class Receivable:
    receivable_id: str

    entity_id: str

    customer_id: str

    invoice_number: str

    invoice_date: date
    due_date: date

    original_amount: Decimal
    outstanding_amount: Decimal

    project_id: str | None = None

    collection_probability: float = 1.0

    status: OpenItemStatus = (
        OpenItemStatus.OPEN
    )


@dataclass(frozen=True)
class Payable:
    payable_id: str

    entity_id: str

    vendor_id: str

    invoice_number: str

    invoice_date: date
    due_date: date

    original_amount: Decimal
    outstanding_amount: Decimal

    project_id: str | None = None

    status: OpenItemStatus = (
        OpenItemStatus.OPEN
    )


@dataclass(frozen=True)
class AgingSummary:
    current: Decimal

    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_90_plus: Decimal

    total: Decimal


@dataclass(frozen=True)
class CostCodePrediction:
    label: str | None

    confidence: float

    examples_seen: int

    evidence_tokens: tuple[
        str,
        ...,
    ]

    review_required: bool


@dataclass(frozen=True)
class CollectionCandidate:
    receivable_id: str

    customer_id: str

    outstanding_amount: Decimal

    days_past_due: int

    collection_probability: float

    priority_score: float


@dataclass(frozen=True)
class CloseFinding:
    finding_id: str

    severity: CloseSeverity

    message: str


@dataclass(frozen=True)
class CloseReport:
    entity_id: str

    period_end: date

    closable: bool

    findings: tuple[
        CloseFinding,
        ...,
    ]


@dataclass(frozen=True)
class ProfitabilityAlert:
    project_id: str

    severity: SurveillanceSeverity

    projected_margin: float

    margin_erosion: float

    cash_exposure: Decimal

    message: str


def utcnow(
) -> datetime:
    return datetime.now(
        timezone.utc
    )
