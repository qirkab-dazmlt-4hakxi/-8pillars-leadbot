from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)
from leadbot_v2.goat.preconstruction.estimating.workflow import (
    EstimateVersion,
    EstimateWorkflowService,
)
from leadbot_v2.goat.preconstruction.orchestrator.whole_plan import (
    PlanTrade,
    PlanWorkItem,
    WholePlanAnalysis,
    WholePlanEstimatorOrchestrator,
    WholePlanRequest,
)


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def new_id(prefix: str) -> str:
    return (
        f"{prefix}_{uuid4().hex}"
    )


class BidSessionError(RuntimeError):
    pass


class BidSessionIntegrityError(
    BidSessionError
):
    pass


class BidSessionStatus(str, Enum):
    CREATED = "created"

    TAKEOFF_IN_PROGRESS = (
        "takeoff_in_progress"
    )

    REVIEW_REQUIRED = (
        "review_required"
    )

    PRICING_IN_PROGRESS = (
        "pricing_in_progress"
    )

    BLOCKED = "blocked"

    READY_FOR_APPROVAL = (
        "ready_for_approval"
    )

    APPROVED = "approved"


class WorkStatus(str, Enum):
    OPEN = "open"

    IN_PROGRESS = (
        "in_progress"
    )

    PRICED = "priced"

    REVIEW_REQUIRED = (
        "review_required"
    )

    RESOLVED = "resolved"

    BLOCKED = "blocked"


@dataclass(frozen=True)
class BidWorkRecord:
    work_id: str

    trade: PlanTrade

    task: str

    status: WorkStatus

    sheet_number: str | None
    page_number: int | None

    source_ref: str | None

    reason: str

    blocking: bool

    confidence: float

    estimate_line_id: (
        str | None
    ) = None

    direct_cost_cents: int = 0
    bid_price_cents: int = 0

    review_note: (
        str | None
    ) = None

    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.work_id.strip():
            raise ValueError(
                "work_id required"
            )

        if self.direct_cost_cents < 0:
            raise ValueError(
                "direct cost cannot "
                "be negative"
            )

        if self.bid_price_cents < 0:
            raise ValueError(
                "bid price cannot "
                "be negative"
            )

        if not 0 <= self.confidence <= 1:
            raise ValueError(
                "confidence must be 0-1"
            )


@dataclass(frozen=True)
class TradeProgress:
    trade: PlanTrade

    total_work_items: int

    open_items: int
    priced_items: int
    review_items: int
    blocked_items: int
    resolved_items: int

    direct_cost_cents: int
    bid_price_cents: int

    @property
    def complete(self) -> bool:
        return (
            self.total_work_items > 0
            and self.open_items == 0
            and self.review_items == 0
            and self.blocked_items == 0
        )


@dataclass(frozen=True)
class BidReadiness:
    ready: bool

    status: BidSessionStatus

    reasons: tuple[
        str,
        ...
    ]

    required_trades: tuple[
        PlanTrade,
        ...
    ]

    completed_trades: tuple[
        PlanTrade,
        ...
    ]


@dataclass(frozen=True)
class BidSession:
    session_id: str

    tenant_id: str
    business_unit_id: str

    project_name: str

    estimate_id: str

    created_by: str
    created_at: datetime

    status: BidSessionStatus

    analysis: WholePlanAnalysis

    work_records: tuple[
        BidWorkRecord,
        ...
    ]

    @property
    def direct_cost_cents(
        self,
    ) -> int:
        return sum(
            item.direct_cost_cents
            for item
            in self.work_records
        )

    @property
    def bid_price_cents(
        self,
    ) -> int:
        return sum(
            item.bid_price_cents
            for item
            in self.work_records
        )


@dataclass(frozen=True)
class BidSessionSummary:
    session_id: str

    project_name: str

    status: BidSessionStatus

    estimate_id: str

    market: str

    direct_cost_cents: int
    bid_price_cents: int

    work_count: int

    open_count: int
    priced_count: int
    review_count: int
    blocked_count: int
    resolved_count: int

    unresolved_rfi_count: int

    ready_for_approval: bool

    readiness_reasons: tuple[
        str,
        ...
    ]


class BidSessionService:
    """
    GOAT bid coordination layer.

    Coordinates:

        whole-plan analysis
        discipline routing
        takeoff work
        pricing results
        estimator review
        RFIs
        estimate lines
        trade completeness
        executive-approval readiness

    It does not fabricate takeoff quantities or prices.

    Existing trade engines remain authoritative for
    quantity and pricing calculations.
    """

    def __init__(
        self,
        *,
        spine: InMemoryDataSpine,
        workflow: (
            EstimateWorkflowService
            | None
        ) = None,
        orchestrator: (
            WholePlanEstimatorOrchestrator
            | None
        ) = None,
    ) -> None:
        self.spine = spine

        self.workflow = (
            workflow
            or EstimateWorkflowService(
                spine=spine
            )
        )

        self.orchestrator = (
            orchestrator
            or WholePlanEstimatorOrchestrator()
        )

        self._sessions: dict[
            str,
            BidSession,
        ] = {}

    def _event(
        self,
        *,
        session: BidSession,
        event_type: str,
        actor_id: str,
        payload: (
            dict[str, Any]
            | None
        ) = None,
    ) -> None:
        self.spine.append_event(
            tenant_id=(
                session.tenant_id
            ),
            aggregate_type=(
                "BidSession"
            ),
            aggregate_id=(
                session.session_id
            ),
            event_type=event_type,
            actor_id=actor_id,
            payload=payload or {},
        )

    @staticmethod
    def _record_from_work(
        item: PlanWorkItem,
    ) -> BidWorkRecord:
        return BidWorkRecord(
            work_id=item.work_id,
            trade=item.trade,
            task=item.task.value,
            status=(
                WorkStatus.BLOCKED
                if item.blocking
                else WorkStatus.OPEN
            ),
            sheet_number=(
                item.sheet_number
            ),
            page_number=(
                item.page_number
            ),
            source_ref=(
                item.source_ref
            ),
            reason=item.reason,
            blocking=item.blocking,
            confidence=(
                item.confidence
            ),
            updated_at=utc_now(),
        )

    def start(
        self,
        *,
        request: WholePlanRequest,
        actor_id: str,
    ) -> BidSession:
        analysis = (
            self.orchestrator
            .analyze(
                request
            )
        )

        estimate = (
            self.orchestrator
            .initialize_estimate(
                request=request,
                analysis=analysis,
                workflow=self.workflow,
                actor_id=actor_id,
            )
        )

        records = tuple(
            self._record_from_work(
                item
            )
            for item
            in analysis.work_items
        )

        initial_status = (
            BidSessionStatus.BLOCKED
            if any(
                record.blocking
                for record in records
            )
            else (
                BidSessionStatus
                .TAKEOFF_IN_PROGRESS
            )
        )

        session = BidSession(
            session_id=new_id(
                "bid"
            ),
            tenant_id=(
                request.tenant_id
            ),
            business_unit_id=(
                request.business_unit_id
            ),
            project_name=(
                request.project_name
            ),
            estimate_id=(
                estimate.estimate_id
            ),
            created_by=actor_id,
            created_at=utc_now(),
            status=initial_status,
            analysis=analysis,
            work_records=records,
        )

        self._sessions[
            session.session_id
        ] = session

        self._event(
            session=session,
            event_type=(
                "bid_session.started"
            ),
            actor_id=actor_id,
            payload={
                "estimate_id":
                    session.estimate_id,

                "work_count":
                    len(
                        session.work_records
                    ),

                "market":
                    (
                        analysis.market.value
                        if analysis.market
                        else "UNRESOLVED"
                    ),
            },
        )

        return session

    def get(
        self,
        session_id: str,
    ) -> BidSession:
        try:
            return self._sessions[
                session_id
            ]

        except KeyError as exc:
            raise KeyError(
                "bid session not found: "
                f"{session_id}"
            ) from exc

    def estimate(
        self,
        session_id: str,
    ) -> EstimateVersion:
        session = self.get(
            session_id
        )

        return (
            self.workflow
            .current_version(
                session.estimate_id
            )
        )

    def _replace_record(
        self,
        *,
        session: BidSession,
        work_id: str,
        replacement: BidWorkRecord,
    ) -> BidSession:
        found = False

        records = []

        for record in (
            session.work_records
        ):
            if (
                record.work_id
                == work_id
            ):
                found = True

                records.append(
                    replacement
                )

            else:
                records.append(
                    record
                )

        if not found:
            raise KeyError(
                "bid work item "
                f"not found: {work_id}"
            )

        updated = replace(
            session,
            work_records=tuple(
                records
            ),
        )

        self._sessions[
            session.session_id
        ] = updated

        return updated

    def begin_work(
        self,
        *,
        session_id: str,
        work_id: str,
        actor_id: str,
    ) -> BidSession:
        session = self.get(
            session_id
        )

        target = next(
            (
                item
                for item
                in session.work_records
                if item.work_id
                == work_id
            ),
            None,
        )

        if target is None:
            raise KeyError(
                "work item not found"
            )

        if target.status not in {
            WorkStatus.OPEN,
            WorkStatus.REVIEW_REQUIRED,
        }:
            raise BidSessionError(
                "work item cannot "
                "enter progress"
            )

        updated_record = replace(
            target,
            status=(
                WorkStatus.IN_PROGRESS
            ),
            updated_at=utc_now(),
        )

        session = self._replace_record(
            session=session,
            work_id=work_id,
            replacement=(
                updated_record
            ),
        )

        session = self._refresh(
            session
        )

        self._event(
            session=session,
            event_type=(
                "bid_work.started"
            ),
            actor_id=actor_id,
            payload={
                "work_id": work_id,
            },
        )

        return session

    @staticmethod
    def _scope_refs(
        priced_scope,
    ) -> tuple[
        str,
        ...
    ]:
        provenance = (
            priced_scope.provenance
        )

        refs = [
            provenance.source_ref,
            *provenance.geometry_ids,
            *provenance.text_refs,
        ]

        return tuple(
            dict.fromkeys(
                ref
                for ref in refs
                if ref
            )
        )

    def record_priced_scope(
        self,
        *,
        session_id: str,
        work_id: str,
        actor_id: str,
        priced_scope,
        cost_code: str,
    ) -> BidSession:
        session = self.get(
            session_id
        )

        target = next(
            (
                item
                for item
                in session.work_records
                if item.work_id
                == work_id
            ),
            None,
        )

        if target is None:
            raise KeyError(
                "work item not found"
            )

        if target.status in {
            WorkStatus.PRICED,
            WorkStatus.RESOLVED,
        }:
            raise BidSessionError(
                "work item already completed"
            )

        direct = int(
            priced_scope
            .direct_cost_cents
        )

        bid = int(
            priced_scope
            .bid_price_cents
        )

        requires_review = bool(
            priced_scope
            .requires_review
        )

        confidence = float(
            priced_scope
            .confidence
        )

        line = (
            self.workflow
            .add_manual_line(
                estimate_id=(
                    session.estimate_id
                ),
                actor_id=actor_id,
                description=(
                    priced_scope
                    .description
                ),
                cost_code=cost_code,
                quantity=1.0,
                unit="LS",
                direct_cost_cents=direct,
                bid_price_cents=bid,
                source_refs=(
                    self._scope_refs(
                        priced_scope
                    )
                ),
                confidence=confidence,
                requires_review=(
                    requires_review
                ),
            )
        )

        status = (
            WorkStatus.REVIEW_REQUIRED
            if requires_review
            else WorkStatus.PRICED
        )

        updated_record = replace(
            target,
            status=status,
            blocking=(
                target.blocking
                or requires_review
            ),
            confidence=min(
                target.confidence,
                confidence,
            ),
            estimate_line_id=(
                line.line_id
            ),
            direct_cost_cents=direct,
            bid_price_cents=bid,
            review_note=(
                "Priced scope requires "
                "estimator review."
                if requires_review
                else None
            ),
            updated_at=utc_now(),
        )

        session = self._replace_record(
            session=session,
            work_id=work_id,
            replacement=(
                updated_record
            ),
        )

        session = self._refresh(
            session
        )

        self._event(
            session=session,
            event_type=(
                "bid_work.priced"
            ),
            actor_id=actor_id,
            payload={
                "work_id": work_id,
                "estimate_line_id":
                    line.line_id,
                "cost_code":
                    cost_code,
                "direct_cost_cents":
                    direct,
                "bid_price_cents":
                    bid,
                "requires_review":
                    requires_review,
            },
        )

        return session

    def mark_review_required(
        self,
        *,
        session_id: str,
        work_id: str,
        actor_id: str,
        reason: str,
    ) -> BidSession:
        if not reason.strip():
            raise ValueError(
                "review reason required"
            )

        session = self.get(
            session_id
        )

        target = next(
            (
                item
                for item
                in session.work_records
                if item.work_id
                == work_id
            ),
            None,
        )

        if target is None:
            raise KeyError(
                "work item not found"
            )

        updated_record = replace(
            target,
            status=(
                WorkStatus
                .REVIEW_REQUIRED
            ),
            blocking=True,
            review_note=(
                reason.strip()
            ),
            updated_at=utc_now(),
        )

        session = self._replace_record(
            session=session,
            work_id=work_id,
            replacement=(
                updated_record
            ),
        )

        session = self._refresh(
            session
        )

        self._event(
            session=session,
            event_type=(
                "bid_work.review_required"
            ),
            actor_id=actor_id,
            payload={
                "work_id": work_id,
                "reason":
                    reason.strip(),
            },
        )

        return session

    def resolve_work(
        self,
        *,
        session_id: str,
        work_id: str,
        actor_id: str,
        note: str,
    ) -> BidSession:
        if not note.strip():
            raise ValueError(
                "resolution note required"
            )

        session = self.get(
            session_id
        )

        target = next(
            (
                item
                for item
                in session.work_records
                if item.work_id
                == work_id
            ),
            None,
        )

        if target is None:
            raise KeyError(
                "work item not found"
            )

        if (
            target.estimate_line_id
            is None
            and target.trade
            in {
                PlanTrade.CONCRETE,
                PlanTrade.EARTHWORK,
                PlanTrade.ELECTRICAL,
                PlanTrade.PLUMBING,
            }
        ):
            raise BidSessionError(
                "trade takeoff cannot be "
                "resolved without pricing"
            )

        updated_record = replace(
            target,
            status=(
                WorkStatus.RESOLVED
            ),
            blocking=False,
            review_note=(
                note.strip()
            ),
            updated_at=utc_now(),
        )

        session = self._replace_record(
            session=session,
            work_id=work_id,
            replacement=(
                updated_record
            ),
        )

        session = self._refresh(
            session
        )

        self._event(
            session=session,
            event_type=(
                "bid_work.resolved"
            ),
            actor_id=actor_id,
            payload={
                "work_id": work_id,
                "note": note.strip(),
            },
        )

        return session

    def trade_progress(
        self,
        *,
        session_id: str,
        trade: PlanTrade,
    ) -> TradeProgress:
        session = self.get(
            session_id
        )

        records = tuple(
            item
            for item
            in session.work_records
            if item.trade == trade
        )

        return TradeProgress(
            trade=trade,
            total_work_items=len(
                records
            ),
            open_items=sum(
                item.status
                in {
                    WorkStatus.OPEN,
                    WorkStatus.IN_PROGRESS,
                }
                for item in records
            ),
            priced_items=sum(
                item.status
                == WorkStatus.PRICED
                for item in records
            ),
            review_items=sum(
                item.status
                == WorkStatus.REVIEW_REQUIRED
                for item in records
            ),
            blocked_items=sum(
                item.status
                == WorkStatus.BLOCKED
                for item in records
            ),
            resolved_items=sum(
                item.status
                == WorkStatus.RESOLVED
                for item in records
            ),
            direct_cost_cents=sum(
                item.direct_cost_cents
                for item in records
            ),
            bid_price_cents=sum(
                item.bid_price_cents
                for item in records
            ),
        )

    def readiness(
        self,
        session_id: str,
    ) -> BidReadiness:
        session = self.get(
            session_id
        )

        reasons = []

        if session.analysis.market is None:
            reasons.append(
                "Regional pricing market "
                "is unresolved."
            )

        estimate = self.estimate(
            session_id
        )

        if estimate.open_blocking_rfis:
            reasons.append(
                "Blocking RFIs remain open."
            )

        if estimate.review_line_ids:
            reasons.append(
                "Estimate contains priced "
                "lines requiring review."
            )

        requested = tuple(
            trade
            for trade
            in session.analysis
            .requested_trades
            if trade
            in {
                PlanTrade.CONCRETE,
                PlanTrade.EARTHWORK,
                PlanTrade.ELECTRICAL,
                PlanTrade.PLUMBING,
            }
        )

        completed = []

        for trade in requested:
            progress = (
                self.trade_progress(
                    session_id=(
                        session_id
                    ),
                    trade=trade,
                )
            )

            if (
                progress.total_work_items
                == 0
            ):
                reasons.append(
                    f"No {trade.value} "
                    "work items exist."
                )

                continue

            if (
                progress.open_items > 0
                or progress.review_items > 0
                or progress.blocked_items > 0
            ):
                reasons.append(
                    f"{trade.value} "
                    "takeoff/pricing "
                    "is incomplete."
                )

                continue

            if (
                progress.direct_cost_cents
                <= 0
            ):
                reasons.append(
                    f"{trade.value} "
                    "contains no priced "
                    "direct cost."
                )

                continue

            completed.append(
                trade
            )

        if not estimate.lines:
            reasons.append(
                "Estimate contains "
                "no priced scope."
            )

        ready = (
            len(reasons) == 0
        )

        if ready:
            status = (
                BidSessionStatus
                .READY_FOR_APPROVAL
            )

        elif any(
            "RFI" in reason
            or "unresolved"
            in reason.lower()
            for reason in reasons
        ):
            status = (
                BidSessionStatus.BLOCKED
            )

        elif any(
            "review"
            in reason.lower()
            for reason in reasons
        ):
            status = (
                BidSessionStatus
                .REVIEW_REQUIRED
            )

        else:
            status = (
                BidSessionStatus
                .TAKEOFF_IN_PROGRESS
            )

        return BidReadiness(
            ready=ready,
            status=status,
            reasons=tuple(
                dict.fromkeys(
                    reasons
                )
            ),
            required_trades=(
                requested
            ),
            completed_trades=tuple(
                completed
            ),
        )

    def _refresh(
        self,
        session: BidSession,
    ) -> BidSession:
        readiness = self.readiness(
            session.session_id
        )

        updated = replace(
            session,
            status=(
                readiness.status
            ),
        )

        self._sessions[
            session.session_id
        ] = updated

        return updated

    def summary(
        self,
        session_id: str,
    ) -> BidSessionSummary:
        session = self.get(
            session_id
        )

        readiness = self.readiness(
            session_id
        )

        records = (
            session.work_records
        )

        estimate = self.estimate(
            session_id
        )

        return BidSessionSummary(
            session_id=(
                session.session_id
            ),
            project_name=(
                session.project_name
            ),
            status=(
                readiness.status
            ),
            estimate_id=(
                session.estimate_id
            ),
            market=(
                session.analysis.market.value
                if session.analysis.market
                else "UNRESOLVED"
            ),
            direct_cost_cents=(
                estimate
                .base_direct_cost_cents
            ),
            bid_price_cents=(
                estimate
                .base_bid_price_cents
            ),
            work_count=len(
                records
            ),
            open_count=sum(
                item.status
                in {
                    WorkStatus.OPEN,
                    WorkStatus.IN_PROGRESS,
                }
                for item in records
            ),
            priced_count=sum(
                item.status
                == WorkStatus.PRICED
                for item in records
            ),
            review_count=sum(
                item.status
                == WorkStatus.REVIEW_REQUIRED
                for item in records
            ),
            blocked_count=sum(
                item.status
                == WorkStatus.BLOCKED
                for item in records
            ),
            resolved_count=sum(
                item.status
                == WorkStatus.RESOLVED
                for item in records
            ),
            unresolved_rfi_count=len(
                estimate
                .open_blocking_rfis
            ),
            ready_for_approval=(
                readiness.ready
            ),
            readiness_reasons=(
                readiness.reasons
            ),
        )
