from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.access_control import (
    AuthorizationEngine,
    Permission,
    Principal,
    ResourceContext,
)
from leadbot_v2.goat.data_spine.models import Project
from leadbot_v2.goat.data_spine.store import InMemoryDataSpine


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class FinancialAuthorizationError(PermissionError):
    pass


class FinancialValidationError(ValueError):
    pass


class FinancialStateError(RuntimeError):
    pass


class CostCategory(str, Enum):
    LABOR = "labor"
    MATERIAL = "material"
    EQUIPMENT = "equipment"
    SUBCONTRACT = "subcontract"
    GENERAL_CONDITIONS = "general_conditions"
    PERMIT = "permit"
    INSURANCE = "insurance"
    OVERHEAD = "overhead"
    OTHER = "other"


class CommitmentStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ChangeOrderStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"


class BillStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"


@dataclass(frozen=True)
class CostCode:
    code: str
    name: str
    category: CostCategory
    tenant_id: str
    business_unit_id: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise FinancialValidationError("cost code required")

        if not self.name.strip():
            raise FinancialValidationError("cost code name required")


@dataclass(frozen=True)
class BudgetLine:
    project_id: str
    cost_code: str
    original_budget_cents: int
    revised_budget_cents: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.original_budget_cents < 0:
            raise FinancialValidationError(
                "original budget cannot be negative"
            )

        if self.revised_budget_cents < 0:
            raise FinancialValidationError(
                "revised budget cannot be negative"
            )


@dataclass(frozen=True)
class Commitment:
    commitment_id: str
    tenant_id: str
    project_id: str
    cost_code: str
    vendor_id: str
    description: str
    original_amount_cents: int
    approved_changes_cents: int
    invoiced_cents: int
    status: CommitmentStatus
    created_at: datetime

    @property
    def total_committed_cents(self) -> int:
        return (
            self.original_amount_cents
            + self.approved_changes_cents
        )

    @property
    def remaining_cents(self) -> int:
        return max(
            0,
            self.total_committed_cents
            - self.invoiced_cents,
        )


@dataclass(frozen=True)
class ActualCost:
    cost_id: str
    tenant_id: str
    project_id: str
    cost_code: str
    amount_cents: int
    source_type: str
    source_ref: str
    occurred_at: datetime
    commitment_id: str | None = None


@dataclass(frozen=True)
class ChangeOrder:
    change_order_id: str
    tenant_id: str
    project_id: str
    description: str
    revenue_change_cents: int
    cost_change_cents: int
    status: ChangeOrderStatus
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None


@dataclass(frozen=True)
class ARInvoice:
    invoice_id: str
    tenant_id: str
    project_id: str
    gross_amount_cents: int
    retainage_cents: int
    paid_cents: int
    status: InvoiceStatus
    issued_at: datetime

    @property
    def net_due_cents(self) -> int:
        return (
            self.gross_amount_cents
            - self.retainage_cents
        )

    @property
    def outstanding_cents(self) -> int:
        return max(
            0,
            self.net_due_cents
            - self.paid_cents,
        )


@dataclass(frozen=True)
class APBill:
    bill_id: str
    tenant_id: str
    project_id: str
    vendor_id: str
    cost_code: str
    gross_amount_cents: int
    retainage_cents: int
    paid_cents: int
    status: BillStatus
    created_at: datetime

    @property
    def net_due_cents(self) -> int:
        return (
            self.gross_amount_cents
            - self.retainage_cents
        )

    @property
    def outstanding_cents(self) -> int:
        return max(
            0,
            self.net_due_cents
            - self.paid_cents,
        )


@dataclass(frozen=True)
class CostForecast:
    project_id: str
    cost_code: str
    forecast_to_complete_cents: int
    updated_at: datetime
    updated_by: str

    def __post_init__(self) -> None:
        if self.forecast_to_complete_cents < 0:
            raise FinancialValidationError(
                "forecast to complete cannot be negative"
            )


@dataclass(frozen=True)
class JournalLine:
    account: str
    debit_cents: int = 0
    credit_cents: int = 0

    def __post_init__(self) -> None:
        if not self.account.strip():
            raise FinancialValidationError(
                "journal account required"
            )

        if self.debit_cents < 0 or self.credit_cents < 0:
            raise FinancialValidationError(
                "journal amounts cannot be negative"
            )

        if bool(self.debit_cents) == bool(self.credit_cents):
            raise FinancialValidationError(
                "journal line must contain exactly one "
                "debit or credit amount"
            )


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    tenant_id: str
    project_id: str | None
    description: str
    lines: tuple[JournalLine, ...]
    posted_at: datetime
    posted_by: str

    @property
    def debits_cents(self) -> int:
        return sum(
            line.debit_cents
            for line in self.lines
        )

    @property
    def credits_cents(self) -> int:
        return sum(
            line.credit_cents
            for line in self.lines
        )


@dataclass(frozen=True)
class FinancialRiskFinding:
    severity: str
    code: str
    message: str
    amount_cents: int | None = None


@dataclass(frozen=True)
class ProjectFinancialSnapshot:
    project_id: str

    original_contract_value_cents: int
    approved_change_revenue_cents: int
    revised_contract_value_cents: int

    original_budget_cents: int
    approved_change_cost_cents: int
    revised_budget_cents: int

    committed_cents: int
    outstanding_commitments_cents: int

    actual_cost_cents: int
    forecast_to_complete_cents: int
    estimate_at_completion_cents: int

    projected_gross_profit_cents: int
    projected_margin_bps: int

    billed_cents: int
    collected_cents: int
    ar_outstanding_cents: int
    retainage_receivable_cents: int

    ap_billed_cents: int
    ap_paid_cents: int
    ap_outstanding_cents: int
    retainage_payable_cents: int

    findings: tuple[FinancialRiskFinding, ...]


class ProjectFinanceService:
    """
    GOAT project financial control plane.

    Prototype storage is in memory.

    Production persistence later moves to PostgreSQL with:
      - row-level tenant security
      - immutable financial audit records
      - transactional outbox
      - period controls
      - external accounting integration
    """

    def __init__(
        self,
        *,
        spine: InMemoryDataSpine,
        authorization: AuthorizationEngine | None = None,
    ) -> None:
        self.spine = spine
        self.authorization = (
            authorization
            or AuthorizationEngine()
        )

        self._cost_codes: dict[
            tuple[str, str],
            CostCode,
        ] = {}

        self._budgets: dict[
            tuple[str, str],
            BudgetLine,
        ] = {}

        self._commitments: dict[
            str,
            Commitment,
        ] = {}

        self._costs: dict[
            str,
            ActualCost,
        ] = {}

        self._change_orders: dict[
            str,
            ChangeOrder,
        ] = {}

        self._ar: dict[
            str,
            ARInvoice,
        ] = {}

        self._ap: dict[
            str,
            APBill,
        ] = {}

        self._forecasts: dict[
            tuple[str, str],
            CostForecast,
        ] = {}

        self._journal: dict[
            str,
            JournalEntry,
        ] = {}

    def _require(
        self,
        *,
        principal: Principal,
        permission: Permission,
        tenant_id: str,
        project_id: str | None = None,
    ) -> None:
        decision = self.authorization.authorize(
            principal,
            permission,
            ResourceContext(
                tenant_id=tenant_id,
                project_id=project_id,
            ),
        )

        if not decision.allowed:
            raise FinancialAuthorizationError(
                decision.reason
            )

    def _project(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> Project:
        return self.spine.get(
            entity_id=project_id,
            tenant_id=tenant_id,
            expected_type=Project,
        )

    def _cost_code(
        self,
        *,
        tenant_id: str,
        code: str,
    ) -> CostCode:
        try:
            return self._cost_codes[
                (tenant_id, code)
            ]
        except KeyError as exc:
            raise FinancialValidationError(
                f"unknown cost code: {code}"
            ) from exc

    def register_cost_code(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        business_unit_id: str,
        code: str,
        name: str,
        category: CostCategory,
    ) -> CostCode:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
        )

        key = (
            tenant_id,
            code.strip(),
        )

        if key in self._cost_codes:
            raise FinancialValidationError(
                "cost code already exists"
            )

        item = CostCode(
            code=code.strip(),
            name=name.strip(),
            category=category,
            tenant_id=tenant_id,
            business_unit_id=business_unit_id,
        )

        self._cost_codes[key] = item

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Finance",
            aggregate_id=code,
            event_type="finance.cost_code.created",
            actor_id=principal.user_id,
            payload={
                "name": name,
                "category": category.value,
            },
        )

        return item

    def set_budget(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        amount_cents: int,
    ) -> BudgetLine:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._cost_code(
            tenant_id=tenant_id,
            code=cost_code,
        )

        if amount_cents < 0:
            raise FinancialValidationError(
                "budget cannot be negative"
            )

        key = (
            project_id,
            cost_code,
        )

        existing = self._budgets.get(key)

        if existing is None:
            line = BudgetLine(
                project_id=project_id,
                cost_code=cost_code,
                original_budget_cents=amount_cents,
                revised_budget_cents=amount_cents,
                updated_at=utc_now(),
            )
        else:
            line = replace(
                existing,
                revised_budget_cents=amount_cents,
                updated_at=utc_now(),
            )

        self._budgets[key] = line

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Project",
            aggregate_id=project_id,
            event_type="finance.budget.updated",
            actor_id=principal.user_id,
            payload={
                "cost_code": cost_code,
                "amount_cents": amount_cents,
            },
        )

        return line

    def create_commitment(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        vendor_id: str,
        description: str,
        amount_cents: int,
    ) -> Commitment:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._cost_code(
            tenant_id=tenant_id,
            code=cost_code,
        )

        if amount_cents < 0:
            raise FinancialValidationError(
                "commitment cannot be negative"
            )

        commitment = Commitment(
            commitment_id=new_id("commitment"),
            tenant_id=tenant_id,
            project_id=project_id,
            cost_code=cost_code,
            vendor_id=vendor_id,
            description=description.strip(),
            original_amount_cents=amount_cents,
            approved_changes_cents=0,
            invoiced_cents=0,
            status=CommitmentStatus.OPEN,
            created_at=utc_now(),
        )

        self._commitments[
            commitment.commitment_id
        ] = commitment

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Project",
            aggregate_id=project_id,
            event_type="finance.commitment.created",
            actor_id=principal.user_id,
            payload={
                "commitment_id":
                    commitment.commitment_id,
                "vendor_id": vendor_id,
                "cost_code": cost_code,
                "amount_cents": amount_cents,
            },
        )

        return commitment

    def adjust_commitment(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        commitment_id: str,
        approved_change_cents: int,
    ) -> Commitment:
        commitment = self._commitments[
            commitment_id
        ]

        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=commitment.project_id,
        )

        if commitment.tenant_id != tenant_id:
            raise FinancialAuthorizationError(
                "cross-tenant commitment denied"
            )

        updated = replace(
            commitment,
            approved_changes_cents=(
                commitment.approved_changes_cents
                + approved_change_cents
            ),
        )

        if updated.total_committed_cents < 0:
            raise FinancialValidationError(
                "commitment total cannot be negative"
            )

        self._commitments[
            commitment_id
        ] = updated

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Project",
            aggregate_id=commitment.project_id,
            event_type="finance.commitment.changed",
            actor_id=principal.user_id,
            payload={
                "commitment_id": commitment_id,
                "approved_change_cents":
                    approved_change_cents,
            },
        )

        return updated

    def record_actual_cost(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        amount_cents: int,
        source_type: str,
        source_ref: str,
        commitment_id: str | None = None,
    ) -> ActualCost:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._cost_code(
            tenant_id=tenant_id,
            code=cost_code,
        )

        if amount_cents <= 0:
            raise FinancialValidationError(
                "actual cost must be positive"
            )

        if not source_ref.strip():
            raise FinancialValidationError(
                "actual cost source reference required"
            )

        if commitment_id is not None:
            commitment = self._commitments[
                commitment_id
            ]

            if (
                commitment.tenant_id != tenant_id
                or commitment.project_id
                != project_id
                or commitment.cost_code
                != cost_code
            ):
                raise FinancialValidationError(
                    "commitment scope mismatch"
                )

            self._commitments[
                commitment_id
            ] = replace(
                commitment,
                invoiced_cents=(
                    commitment.invoiced_cents
                    + amount_cents
                ),
            )

        cost = ActualCost(
            cost_id=new_id("cost"),
            tenant_id=tenant_id,
            project_id=project_id,
            cost_code=cost_code,
            amount_cents=amount_cents,
            source_type=source_type,
            source_ref=source_ref.strip(),
            occurred_at=utc_now(),
            commitment_id=commitment_id,
        )

        self._costs[cost.cost_id] = cost

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Project",
            aggregate_id=project_id,
            event_type="finance.actual_cost.recorded",
            actor_id=principal.user_id,
            payload={
                "cost_id": cost.cost_id,
                "cost_code": cost_code,
                "amount_cents": amount_cents,
                "source_type": source_type,
                "source_ref": source_ref,
                "commitment_id": commitment_id,
            },
        )

        return cost

    def create_change_order(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        description: str,
        revenue_change_cents: int,
        cost_change_cents: int,
    ) -> ChangeOrder:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        change = ChangeOrder(
            change_order_id=new_id("co"),
            tenant_id=tenant_id,
            project_id=project_id,
            description=description.strip(),
            revenue_change_cents=revenue_change_cents,
            cost_change_cents=cost_change_cents,
            status=ChangeOrderStatus.DRAFT,
            created_at=utc_now(),
        )

        self._change_orders[
            change.change_order_id
        ] = change

        return change

    def submit_change_order(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        change_order_id: str,
    ) -> ChangeOrder:
        change = self._change_orders[
            change_order_id
        ]

        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=change.project_id,
        )

        if change.status != ChangeOrderStatus.DRAFT:
            raise FinancialStateError(
                "only draft change orders may be submitted"
            )

        updated = replace(
            change,
            status=ChangeOrderStatus.SUBMITTED,
        )

        self._change_orders[
            change_order_id
        ] = updated

        return updated

    def approve_change_order(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        change_order_id: str,
    ) -> ChangeOrder:
        change = self._change_orders[
            change_order_id
        ]

        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=change.project_id,
        )

        if (
            change.status
            != ChangeOrderStatus.SUBMITTED
        ):
            raise FinancialStateError(
                "only submitted change orders "
                "may be approved"
            )

        updated = replace(
            change,
            status=ChangeOrderStatus.APPROVED,
            approved_at=utc_now(),
            approved_by=principal.user_id,
        )

        self._change_orders[
            change_order_id
        ] = updated

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Project",
            aggregate_id=change.project_id,
            event_type="finance.change_order.approved",
            actor_id=principal.user_id,
            payload={
                "change_order_id":
                    change_order_id,
                "revenue_change_cents":
                    change.revenue_change_cents,
                "cost_change_cents":
                    change.cost_change_cents,
            },
        )

        return updated

    def create_ar_invoice(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        gross_amount_cents: int,
        retainage_cents: int = 0,
    ) -> ARInvoice:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        if gross_amount_cents <= 0:
            raise FinancialValidationError(
                "invoice must be positive"
            )

        if not 0 <= retainage_cents <= gross_amount_cents:
            raise FinancialValidationError(
                "invalid invoice retainage"
            )

        invoice = ARInvoice(
            invoice_id=new_id("invoice"),
            tenant_id=tenant_id,
            project_id=project_id,
            gross_amount_cents=gross_amount_cents,
            retainage_cents=retainage_cents,
            paid_cents=0,
            status=InvoiceStatus.ISSUED,
            issued_at=utc_now(),
        )

        self._ar[invoice.invoice_id] = invoice

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Project",
            aggregate_id=project_id,
            event_type="finance.ar.invoice_issued",
            actor_id=principal.user_id,
            payload={
                "invoice_id": invoice.invoice_id,
                "gross_amount_cents":
                    gross_amount_cents,
                "retainage_cents":
                    retainage_cents,
            },
        )

        return invoice

    def record_ar_payment(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        invoice_id: str,
        amount_cents: int,
    ) -> ARInvoice:
        invoice = self._ar[invoice_id]

        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=invoice.project_id,
        )

        if invoice.tenant_id != tenant_id:
            raise FinancialAuthorizationError(
                "cross-tenant invoice denied"
            )

        if amount_cents <= 0:
            raise FinancialValidationError(
                "payment must be positive"
            )

        new_paid = (
            invoice.paid_cents
            + amount_cents
        )

        if new_paid > invoice.net_due_cents:
            raise FinancialValidationError(
                "payment exceeds invoice net due"
            )

        status = (
            InvoiceStatus.PAID
            if new_paid == invoice.net_due_cents
            else InvoiceStatus.PARTIALLY_PAID
        )

        updated = replace(
            invoice,
            paid_cents=new_paid,
            status=status,
        )

        self._ar[invoice_id] = updated

        return updated

    def create_ap_bill(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        vendor_id: str,
        cost_code: str,
        gross_amount_cents: int,
        retainage_cents: int = 0,
    ) -> APBill:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._cost_code(
            tenant_id=tenant_id,
            code=cost_code,
        )

        if gross_amount_cents <= 0:
            raise FinancialValidationError(
                "bill must be positive"
            )

        if not 0 <= retainage_cents <= gross_amount_cents:
            raise FinancialValidationError(
                "invalid bill retainage"
            )

        bill = APBill(
            bill_id=new_id("bill"),
            tenant_id=tenant_id,
            project_id=project_id,
            vendor_id=vendor_id,
            cost_code=cost_code,
            gross_amount_cents=gross_amount_cents,
            retainage_cents=retainage_cents,
            paid_cents=0,
            status=BillStatus.OPEN,
            created_at=utc_now(),
        )

        self._ap[bill.bill_id] = bill

        return bill

    def record_ap_payment(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        bill_id: str,
        amount_cents: int,
    ) -> APBill:
        bill = self._ap[bill_id]

        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=bill.project_id,
        )

        if bill.tenant_id != tenant_id:
            raise FinancialAuthorizationError(
                "cross-tenant AP bill denied"
            )

        if amount_cents <= 0:
            raise FinancialValidationError(
                "payment must be positive"
            )

        new_paid = (
            bill.paid_cents
            + amount_cents
        )

        if new_paid > bill.net_due_cents:
            raise FinancialValidationError(
                "payment exceeds bill net due"
            )

        status = (
            BillStatus.PAID
            if new_paid == bill.net_due_cents
            else BillStatus.PARTIALLY_PAID
        )

        updated = replace(
            bill,
            paid_cents=new_paid,
            status=status,
        )

        self._ap[bill_id] = updated

        return updated

    def set_forecast_to_complete(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        forecast_to_complete_cents: int,
    ) -> CostForecast:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._cost_code(
            tenant_id=tenant_id,
            code=cost_code,
        )

        forecast = CostForecast(
            project_id=project_id,
            cost_code=cost_code,
            forecast_to_complete_cents=(
                forecast_to_complete_cents
            ),
            updated_at=utc_now(),
            updated_by=principal.user_id,
        )

        self._forecasts[
            (project_id, cost_code)
        ] = forecast

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Project",
            aggregate_id=project_id,
            event_type="finance.forecast.updated",
            actor_id=principal.user_id,
            payload={
                "cost_code": cost_code,
                "forecast_to_complete_cents":
                    forecast_to_complete_cents,
            },
        )

        return forecast

    def post_journal_entry(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        description: str,
        lines: tuple[JournalLine, ...],
        project_id: str | None = None,
    ) -> JournalEntry:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_WRITE,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        if project_id is not None:
            self._project(
                tenant_id=tenant_id,
                project_id=project_id,
            )

        if len(lines) < 2:
            raise FinancialValidationError(
                "journal entry requires at least two lines"
            )

        debits = sum(
            line.debit_cents
            for line in lines
        )

        credits = sum(
            line.credit_cents
            for line in lines
        )

        if debits != credits:
            raise FinancialValidationError(
                "journal entry is not balanced"
            )

        if debits <= 0:
            raise FinancialValidationError(
                "journal entry must contain value"
            )

        entry = JournalEntry(
            entry_id=new_id("journal"),
            tenant_id=tenant_id,
            project_id=project_id,
            description=description.strip(),
            lines=lines,
            posted_at=utc_now(),
            posted_by=principal.user_id,
        )

        self._journal[
            entry.entry_id
        ] = entry

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Finance",
            aggregate_id=entry.entry_id,
            event_type="finance.journal.posted",
            actor_id=principal.user_id,
            payload={
                "project_id": project_id,
                "debits_cents": debits,
                "credits_cents": credits,
            },
        )

        return entry

    def snapshot(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
    ) -> ProjectFinancialSnapshot:
        self._require(
            principal=principal,
            permission=Permission.FINANCIAL_READ,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        project = self._project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        budget_lines = [
            line
            for (pid, _), line
            in self._budgets.items()
            if pid == project_id
        ]

        original_budget = sum(
            line.original_budget_cents
            for line in budget_lines
        )

        approved_changes = [
            item
            for item
            in self._change_orders.values()
            if (
                item.tenant_id == tenant_id
                and item.project_id == project_id
                and item.status
                == ChangeOrderStatus.APPROVED
            )
        ]

        change_revenue = sum(
            item.revenue_change_cents
            for item in approved_changes
        )

        change_cost = sum(
            item.cost_change_cents
            for item in approved_changes
        )

        revised_budget = (
            sum(
                line.revised_budget_cents
                for line in budget_lines
            )
            + change_cost
        )

        commitments = [
            item
            for item
            in self._commitments.values()
            if (
                item.tenant_id == tenant_id
                and item.project_id == project_id
                and item.status
                != CommitmentStatus.CANCELLED
            )
        ]

        committed = sum(
            item.total_committed_cents
            for item in commitments
        )

        outstanding_commitments = sum(
            item.remaining_cents
            for item in commitments
        )

        project_costs = [
            item
            for item
            in self._costs.values()
            if (
                item.tenant_id == tenant_id
                and item.project_id == project_id
            )
        ]

        actual_cost = sum(
            item.amount_cents
            for item in project_costs
        )

        actual_by_code: dict[str, int] = {}

        for item in project_costs:
            actual_by_code[item.cost_code] = (
                actual_by_code.get(
                    item.cost_code,
                    0,
                )
                + item.amount_cents
            )

        commitment_remaining_by_code: dict[
            str,
            int,
        ] = {}

        for item in commitments:
            commitment_remaining_by_code[
                item.cost_code
            ] = (
                commitment_remaining_by_code.get(
                    item.cost_code,
                    0,
                )
                + item.remaining_cents
            )

        forecast_to_complete = 0

        for line in budget_lines:
            override = self._forecasts.get(
                (
                    project_id,
                    line.cost_code,
                )
            )

            if override is not None:
                forecast_to_complete += (
                    override
                    .forecast_to_complete_cents
                )
                continue

            actual_for_code = (
                actual_by_code.get(
                    line.cost_code,
                    0,
                )
            )

            remaining_budget = max(
                0,
                line.revised_budget_cents
                - actual_for_code,
            )

            outstanding_commitment = (
                commitment_remaining_by_code.get(
                    line.cost_code,
                    0,
                )
            )

            forecast_to_complete += max(
                remaining_budget,
                outstanding_commitment,
            )

        # Cost codes with actual/commitment activity
        # but no budget line must not disappear.
        budgeted_codes = {
            line.cost_code
            for line in budget_lines
        }

        for code, remaining in (
            commitment_remaining_by_code.items()
        ):
            if code not in budgeted_codes:
                forecast_to_complete += remaining

        estimate_at_completion = (
            actual_cost
            + forecast_to_complete
        )

        original_contract = (
            project.contract_value_cents
            or 0
        )

        revised_contract = (
            original_contract
            + change_revenue
        )

        projected_gp = (
            revised_contract
            - estimate_at_completion
        )

        projected_margin_bps = (
            projected_gp * 10_000
            // revised_contract
            if revised_contract > 0
            else 0
        )

        project_ar = [
            invoice
            for invoice in self._ar.values()
            if (
                invoice.tenant_id == tenant_id
                and invoice.project_id == project_id
                and invoice.status
                != InvoiceStatus.VOID
            )
        ]

        billed = sum(
            invoice.gross_amount_cents
            for invoice in project_ar
        )

        collected = sum(
            invoice.paid_cents
            for invoice in project_ar
        )

        ar_outstanding = sum(
            invoice.outstanding_cents
            for invoice in project_ar
        )

        retainage_receivable = sum(
            invoice.retainage_cents
            for invoice in project_ar
        )

        project_ap = [
            bill
            for bill in self._ap.values()
            if (
                bill.tenant_id == tenant_id
                and bill.project_id == project_id
                and bill.status
                != BillStatus.VOID
            )
        ]

        ap_billed = sum(
            bill.gross_amount_cents
            for bill in project_ap
        )

        ap_paid = sum(
            bill.paid_cents
            for bill in project_ap
        )

        ap_outstanding = sum(
            bill.outstanding_cents
            for bill in project_ap
        )

        retainage_payable = sum(
            bill.retainage_cents
            for bill in project_ap
        )

        findings: list[
            FinancialRiskFinding
        ] = []

        if revised_budget > 0:
            budget_gp = (
                revised_contract
                - revised_budget
            )

            budget_margin_bps = (
                budget_gp * 10_000
                // revised_contract
                if revised_contract > 0
                else 0
            )

            erosion_bps = (
                budget_margin_bps
                - projected_margin_bps
            )

            if erosion_bps >= 500:
                findings.append(
                    FinancialRiskFinding(
                        severity="critical",
                        code="margin_erosion",
                        message=(
                            "Projected gross margin has "
                            "eroded by at least 5 percentage "
                            "points versus revised budget."
                        ),
                        amount_cents=(
                            estimate_at_completion
                            - revised_budget
                        ),
                    )
                )

            elif erosion_bps >= 200:
                findings.append(
                    FinancialRiskFinding(
                        severity="high",
                        code="margin_erosion",
                        message=(
                            "Projected gross margin has "
                            "eroded by at least 2 percentage "
                            "points versus revised budget."
                        ),
                        amount_cents=(
                            estimate_at_completion
                            - revised_budget
                        ),
                    )
                )

        if actual_cost > revised_budget:
            findings.append(
                FinancialRiskFinding(
                    severity="critical",
                    code="actual_cost_over_budget",
                    message=(
                        "Actual project cost exceeds "
                        "revised budget."
                    ),
                    amount_cents=(
                        actual_cost
                        - revised_budget
                    ),
                )
            )

        for commitment in commitments:
            if (
                commitment.invoiced_cents
                > commitment.total_committed_cents
            ):
                findings.append(
                    FinancialRiskFinding(
                        severity="high",
                        code="commitment_overrun",
                        message=(
                            f"Commitment "
                            f"{commitment.commitment_id} "
                            "has invoiced cost exceeding "
                            "approved commitment."
                        ),
                        amount_cents=(
                            commitment.invoiced_cents
                            - commitment.total_committed_cents
                        ),
                    )
                )

        if (
            revised_contract > 0
            and billed > revised_contract
        ):
            findings.append(
                FinancialRiskFinding(
                    severity="critical",
                    code="overbilling",
                    message=(
                        "Gross billing exceeds revised "
                        "contract value."
                    ),
                    amount_cents=(
                        billed
                        - revised_contract
                    ),
                )
            )

        return ProjectFinancialSnapshot(
            project_id=project_id,

            original_contract_value_cents=(
                original_contract
            ),

            approved_change_revenue_cents=(
                change_revenue
            ),

            revised_contract_value_cents=(
                revised_contract
            ),

            original_budget_cents=(
                original_budget
            ),

            approved_change_cost_cents=(
                change_cost
            ),

            revised_budget_cents=(
                revised_budget
            ),

            committed_cents=committed,

            outstanding_commitments_cents=(
                outstanding_commitments
            ),

            actual_cost_cents=actual_cost,

            forecast_to_complete_cents=(
                forecast_to_complete
            ),

            estimate_at_completion_cents=(
                estimate_at_completion
            ),

            projected_gross_profit_cents=(
                projected_gp
            ),

            projected_margin_bps=(
                projected_margin_bps
            ),

            billed_cents=billed,

            collected_cents=collected,

            ar_outstanding_cents=(
                ar_outstanding
            ),

            retainage_receivable_cents=(
                retainage_receivable
            ),

            ap_billed_cents=ap_billed,

            ap_paid_cents=ap_paid,

            ap_outstanding_cents=(
                ap_outstanding
            ),

            retainage_payable_cents=(
                retainage_payable
            ),

            findings=tuple(findings),
        )
