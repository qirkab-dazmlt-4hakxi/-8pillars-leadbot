from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from leadbot_v2.goat.preconstruction.pdf_ingest.engine import (
    PdfIngestEngine,
)

from leadbot_v2.goat.preconstruction.pricing.engine import (
    MarkupPolicy,
)

from leadbot_v2.goat.preconstruction.revisions.intelligence import (
    PlanRevisionEngine,
    RevisionImpactPlan,
    RevisionRerunPlanner,
)

from leadbot_v2.goat.preconstruction.revisions.lifecycle import (
    EstimateRevisionLifecycle,
    RevisionLifecycleResult,
    RevisionReviewSeverity,
)

from leadbot_v2.goat.preconstruction.semantic.geometry import (
    SemanticGeometryResolver,
    SemanticTakeoff,
)

from leadbot_v2.goat.preconstruction.semantic.pricing_bridge import (
    SemanticPricingResult,
    SemanticRegionalPricingService,
)


class RevisionExecutionError(RuntimeError):
    pass


class RevisionExecutionMode(str, Enum):
    NO_CHANGE = "no_change"
    INCREMENTAL = "incremental"
    FULL_RERUN = "full_rerun"
    BLOCKED = "blocked"


class ApprovalSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class DocumentSlice:
    document_id: str
    file_name: str
    pages: tuple
    source_document_id: str

    @property
    def page_count(
        self,
    ) -> int:
        return len(
            self.pages
        )


@dataclass(frozen=True)
class ApprovalItem:
    code: str

    severity: ApprovalSeverity

    message: str

    page_number: int | None = None

    sheet_number: str | None = None

    candidate_id: str | None = None

    line_id: str | None = None

    source_ref: str | None = None


@dataclass(frozen=True)
class RevisionFinancialDelta:
    old_direct_cost_cents: int

    old_bid_price_cents: int

    new_direct_cost_cents: int

    new_bid_price_cents: int

    direct_cost_delta_cents: int

    bid_price_delta_cents: int


@dataclass(frozen=True)
class RevisionApprovalPacket:
    estimate_id: str

    old_document_id: str

    new_document_id: str

    mode: RevisionExecutionMode

    changed_sheet_count: int

    impacted_pages: tuple[
        int,
        ...
    ]

    impacted_trades: tuple[
        str,
        ...
    ]

    invalidated_candidate_ids: tuple[
        str,
        ...
    ]

    invalidated_line_ids: tuple[
        str,
        ...
    ]

    replacement_line_ids: tuple[
        str,
        ...
    ]

    approval_items: tuple[
        ApprovalItem,
        ...
    ]

    financial_delta: RevisionFinancialDelta

    requires_estimator_approval: bool

    ready_for_revised_proposal: bool

    @property
    def blockers(
        self,
    ) -> tuple[
        ApprovalItem,
        ...
    ]:
        return tuple(
            item
            for item
            in self.approval_items
            if (
                item.severity
                == ApprovalSeverity.BLOCKER
            )
        )

    @property
    def review_items(
        self,
    ) -> tuple[
        ApprovalItem,
        ...
    ]:
        return tuple(
            item
            for item
            in self.approval_items
            if (
                item.severity
                == ApprovalSeverity.REVIEW
            )
        )


@dataclass(frozen=True)
class RevisionExecutionResult:
    impact: RevisionImpactPlan

    rerun_plan: dict

    semantic: SemanticTakeoff

    pricing: SemanticPricingResult

    lifecycle: (
        RevisionLifecycleResult
        | None
    )

    approval_packet: RevisionApprovalPacket


def _enum_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    enum_value = getattr(
        value,
        "value",
        None,
    )

    if enum_value is not None:
        return str(
            enum_value
        )

    return str(
        value
    )


def _empty_semantic(
    document_id: str,
) -> SemanticTakeoff:
    return SemanticTakeoff(
        document_id=(
            document_id
        ),
        candidates=(),
        findings=(),
    )


def _empty_pricing(
    *,
    city: str,
    market: str = "",
    as_of: date,
) -> SemanticPricingResult:
    return SemanticPricingResult(
        city=city,
        market=market,
        as_of=as_of,
        scopes=(),
    )


class RevisionExecutionCoordinator:
    """
    End-to-end GOAT addendum/revision execution boundary.

    Flow:
        old plan evidence
        -> new plan evidence
        -> deterministic revision intelligence
        -> impacted-page isolation
        -> semantic rerun
        -> regional repricing
        -> immutable estimate revision
        -> financial delta
        -> estimator approval packet

    Existing estimates are never silently overwritten.
    """

    def __init__(
        self,
        *,
        workflow: Any,
        rate_resolver: Any | None = None,
        pricing_service: (
            SemanticRegionalPricingService
            | None
        ) = None,
        pdf_ingest: (
            PdfIngestEngine
            | None
        ) = None,
        revision_engine: (
            PlanRevisionEngine
            | None
        ) = None,
        semantic_resolver: (
            SemanticGeometryResolver
            | None
        ) = None,
        lifecycle: (
            EstimateRevisionLifecycle
            | None
        ) = None,
    ) -> None:
        self.workflow = workflow

        self.pdf_ingest = (
            pdf_ingest
            or PdfIngestEngine()
        )

        self.revision_engine = (
            revision_engine
            or PlanRevisionEngine()
        )

        self.semantic_resolver = (
            semantic_resolver
            or SemanticGeometryResolver()
        )

        if pricing_service is None:
            if rate_resolver is None:
                raise ValueError(
                    "rate_resolver or pricing_service required"
                )

            pricing_service = (
                SemanticRegionalPricingService(
                    resolver=rate_resolver
                )
            )

        self.pricing_service = (
            pricing_service
        )

        self.lifecycle = (
            lifecycle
            or EstimateRevisionLifecycle(
                workflow=workflow
            )
        )

    @staticmethod
    def _document_id(
        document: Any,
    ) -> str:
        return str(
            getattr(
                document,
                "document_id",
                "unknown-document",
            )
        )

    @staticmethod
    def _file_name(
        document: Any,
    ) -> str:
        return str(
            getattr(
                document,
                "file_name",
                "plans.pdf",
            )
        )

    @classmethod
    def _slice_document(
        cls,
        *,
        document: Any,
        pages: tuple[
            int,
            ...
        ],
        full_rerun: bool,
    ) -> DocumentSlice:
        source_pages = tuple(
            getattr(
                document,
                "pages",
                (),
            )
        )

        if full_rerun:
            selected = (
                source_pages
            )

        else:
            wanted = set(
                pages
            )

            selected = tuple(
                page
                for page
                in source_pages
                if int(
                    getattr(
                        page,
                        "page_number",
                        0,
                    )
                )
                in wanted
            )

        document_id = (
            cls._document_id(
                document
            )
        )

        return DocumentSlice(
            document_id=(
                document_id
                + (
                    ":full-rerun"
                    if full_rerun
                    else ":incremental"
                )
            ),
            file_name=(
                cls._file_name(
                    document
                )
            ),
            pages=selected,
            source_document_id=(
                document_id
            ),
        )

    @staticmethod
    def _approval_from_impact(
        impact: RevisionImpactPlan,
    ) -> list[
        ApprovalItem
    ]:
        items = []

        for finding in (
            impact.findings
        ):
            severity_text = (
                _enum_text(
                    finding.severity
                )
                .strip()
                .lower()
            )

            if severity_text == "blocker":
                severity = (
                    ApprovalSeverity.BLOCKER
                )

            elif severity_text == "review":
                severity = (
                    ApprovalSeverity.REVIEW
                )

            else:
                severity = (
                    ApprovalSeverity.INFO
                )

            items.append(
                ApprovalItem(
                    code=(
                        finding.code
                    ),
                    severity=severity,
                    message=(
                        finding.message
                    ),
                    page_number=(
                        finding
                        .new_page_number
                        or finding
                        .old_page_number
                    ),
                    sheet_number=(
                        finding
                        .sheet_number
                    ),
                    source_ref=(
                        finding
                        .source_ref
                    ),
                )
            )

        return items

    @staticmethod
    def _approval_from_lifecycle(
        lifecycle: (
            RevisionLifecycleResult
            | None
        ),
    ) -> list[
        ApprovalItem
    ]:
        if lifecycle is None:
            return []

        items = []

        for item in (
            lifecycle.review_queue
        ):
            if (
                item.severity
                == RevisionReviewSeverity
                .BLOCKER
            ):
                severity = (
                    ApprovalSeverity.BLOCKER
                )
            else:
                severity = (
                    ApprovalSeverity.REVIEW
                )

            items.append(
                ApprovalItem(
                    code=item.code,
                    severity=severity,
                    message=(
                        item.message
                    ),
                    candidate_id=(
                        item.candidate_id
                    ),
                    line_id=(
                        item.line_id
                    ),
                    source_ref=(
                        item.source_ref
                    ),
                )
            )

        return items

    @staticmethod
    def _financial_delta(
        lifecycle: (
            RevisionLifecycleResult
            | None
        ),
    ) -> RevisionFinancialDelta:
        if lifecycle is None:
            return (
                RevisionFinancialDelta(
                    old_direct_cost_cents=0,
                    old_bid_price_cents=0,
                    new_direct_cost_cents=0,
                    new_bid_price_cents=0,
                    direct_cost_delta_cents=0,
                    bid_price_delta_cents=0,
                )
            )

        delta = (
            lifecycle.delta
        )

        return RevisionFinancialDelta(
            old_direct_cost_cents=(
                delta
                .old_impacted_direct_cost_cents
            ),
            old_bid_price_cents=(
                delta
                .old_impacted_bid_price_cents
            ),
            new_direct_cost_cents=(
                delta
                .replacement_direct_cost_cents
            ),
            new_bid_price_cents=(
                delta
                .replacement_bid_price_cents
            ),
            direct_cost_delta_cents=(
                delta
                .direct_cost_delta_cents
            ),
            bid_price_delta_cents=(
                delta
                .bid_price_delta_cents
            ),
        )

    @staticmethod
    def _dedupe_items(
        items: list[
            ApprovalItem
        ],
    ) -> tuple[
        ApprovalItem,
        ...
    ]:
        deduped = {}

        for item in items:
            key = (
                item.code,
                item.severity.value,
                item.message,
                item.page_number,
                item.sheet_number,
                item.candidate_id,
                item.line_id,
                item.source_ref,
            )

            deduped[
                key
            ] = item

        return tuple(
            deduped.values()
        )

    @classmethod
    def _packet(
        cls,
        *,
        estimate_id: str,
        impact: RevisionImpactPlan,
        rerun_plan: dict,
        lifecycle: (
            RevisionLifecycleResult
            | None
        ),
        extra_items: tuple[
            ApprovalItem,
            ...
        ] = (),
    ) -> RevisionApprovalPacket:
        items = (
            cls._approval_from_impact(
                impact
            )
            + cls._approval_from_lifecycle(
                lifecycle
            )
            + list(
                extra_items
            )
        )

        approval_items = (
            cls._dedupe_items(
                items
            )
        )

        blockers = tuple(
            item
            for item
            in approval_items
            if (
                item.severity
                == ApprovalSeverity.BLOCKER
            )
        )

        reviews = tuple(
            item
            for item
            in approval_items
            if (
                item.severity
                == ApprovalSeverity.REVIEW
            )
        )

        if impact.no_change:
            mode = (
                RevisionExecutionMode
                .NO_CHANGE
            )

        elif impact.blockers:
            mode = (
                RevisionExecutionMode
                .BLOCKED
            )

        elif (
            rerun_plan.get(
                "mode"
            )
            == "full_rerun"
        ):
            mode = (
                RevisionExecutionMode
                .FULL_RERUN
            )

        else:
            mode = (
                RevisionExecutionMode
                .INCREMENTAL
            )

        financial = (
            cls._financial_delta(
                lifecycle
            )
        )

        invalidated_line_ids = (
            tuple(
                item.line_id
                for item
                in lifecycle
                .invalidated_lines
            )
            if lifecycle
            is not None
            else ()
        )

        replacement_line_ids = (
            tuple(
                item.line_id
                for item
                in lifecycle
                .replacement_lines
            )
            if lifecycle
            is not None
            else ()
        )

        lifecycle_ready = (
            bool(
                lifecycle
                .proposal_ready
            )
            if lifecycle
            is not None
            else False
        )

        ready = (
            impact.no_change
            or (
                lifecycle_ready
                and not blockers
                and not reviews
            )
        )

        requires_approval = (
            not impact.no_change
        )

        return RevisionApprovalPacket(
            estimate_id=(
                estimate_id
            ),
            old_document_id=(
                impact
                .old_document_id
            ),
            new_document_id=(
                impact
                .new_document_id
            ),
            mode=mode,
            changed_sheet_count=len(
                impact
                .changed_sheets
            ),
            impacted_pages=tuple(
                impact
                .impacted_new_pages
            ),
            impacted_trades=tuple(
                trade.value
                for trade
                in impact
                .impacted_trades
            ),
            invalidated_candidate_ids=(
                impact
                .invalidated_candidate_ids
            ),
            invalidated_line_ids=(
                invalidated_line_ids
            ),
            replacement_line_ids=(
                replacement_line_ids
            ),
            approval_items=(
                approval_items
            ),
            financial_delta=(
                financial
            ),
            requires_estimator_approval=(
                requires_approval
            ),
            ready_for_revised_proposal=(
                ready
            ),
        )

    def execute_documents(
        self,
        *,
        old_document: Any,
        new_document: Any,
        previous_semantic: Any,
        estimate_id: str,
        actor_id: str,
        city: str,
        as_of: date,
        markup: MarkupPolicy,
        project_id: str | None = None,
        prevailing_wage_required: (
            bool
        ) = False,
        requested_labor_basis: (
            Any | None
        ) = None,
        allow_statewide_fallback: (
            bool
        ) = True,
    ) -> RevisionExecutionResult:
        impact = (
            self.revision_engine
            .compare(
                old_document=(
                    old_document
                ),
                new_document=(
                    new_document
                ),
                previous_semantic=(
                    previous_semantic
                ),
            )
        )

        rerun_plan = (
            RevisionRerunPlanner
            .execution_plan(
                impact
            )
        )

        if impact.blockers:
            semantic = (
                _empty_semantic(
                    self._document_id(
                        new_document
                    )
                )
            )

            pricing = (
                _empty_pricing(
                    city=city,
                    as_of=as_of,
                )
            )

            packet = (
                self._packet(
                    estimate_id=(
                        estimate_id
                    ),
                    impact=impact,
                    rerun_plan=(
                        rerun_plan
                    ),
                    lifecycle=None,
                )
            )

            return (
                RevisionExecutionResult(
                    impact=impact,
                    rerun_plan=(
                        rerun_plan
                    ),
                    semantic=semantic,
                    pricing=pricing,
                    lifecycle=None,
                    approval_packet=(
                        packet
                    ),
                )
            )

        if impact.no_change:
            semantic = (
                previous_semantic
            )

            pricing = (
                _empty_pricing(
                    city=city,
                    as_of=as_of,
                )
            )

            lifecycle = (
                self.lifecycle
                .apply(
                    estimate_id=(
                        estimate_id
                    ),
                    actor_id=(
                        actor_id
                    ),
                    impact=impact,
                    new_semantic=(
                        semantic
                    ),
                    new_pricing=(
                        pricing
                    ),
                )
            )

            packet = (
                self._packet(
                    estimate_id=(
                        estimate_id
                    ),
                    impact=impact,
                    rerun_plan=(
                        rerun_plan
                    ),
                    lifecycle=(
                        lifecycle
                    ),
                )
            )

            return (
                RevisionExecutionResult(
                    impact=impact,
                    rerun_plan=(
                        rerun_plan
                    ),
                    semantic=semantic,
                    pricing=pricing,
                    lifecycle=lifecycle,
                    approval_packet=(
                        packet
                    ),
                )
            )

        full_rerun = (
            rerun_plan.get(
                "mode"
            )
            == "full_rerun"
        )

        slice_document = (
            self._slice_document(
                document=(
                    new_document
                ),
                pages=(
                    impact
                    .impacted_new_pages
                ),
                full_rerun=(
                    full_rerun
                ),
            )
        )

        if (
            not slice_document.pages
            and impact
            .impacted_new_pages
        ):
            extra = (
                ApprovalItem(
                    code=(
                        "RERUN_PAGE_MISSING"
                    ),
                    severity=(
                        ApprovalSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Revision intelligence "
                        "identified impacted new "
                        "pages that could not be "
                        "found in the new document."
                    ),
                ),
            )

            semantic = (
                _empty_semantic(
                    self._document_id(
                        new_document
                    )
                )
            )

            pricing = (
                _empty_pricing(
                    city=city,
                    as_of=as_of,
                )
            )

            packet = (
                self._packet(
                    estimate_id=(
                        estimate_id
                    ),
                    impact=impact,
                    rerun_plan=(
                        rerun_plan
                    ),
                    lifecycle=None,
                    extra_items=(
                        extra
                    ),
                )
            )

            return (
                RevisionExecutionResult(
                    impact=impact,
                    rerun_plan=(
                        rerun_plan
                    ),
                    semantic=semantic,
                    pricing=pricing,
                    lifecycle=None,
                    approval_packet=(
                        packet
                    ),
                )
            )

        if slice_document.pages:
            semantic = (
                self.semantic_resolver
                .resolve(
                    slice_document
                )
            )

            pricing = (
                self.pricing_service
                .price_takeoff(
                    takeoff=semantic,
                    city=city,
                    as_of=as_of,
                    markup=markup,
                    project_id=(
                        project_id
                    ),
                    prevailing_wage_required=(
                        prevailing_wage_required
                    ),
                    requested_labor_basis=(
                        requested_labor_basis
                    ),
                    allow_statewide_fallback=(
                        allow_statewide_fallback
                    ),
                )
            )

        else:
            # Removed-sheet-only revision.
            semantic = (
                _empty_semantic(
                    self._document_id(
                        new_document
                    )
                )
            )

            pricing = (
                _empty_pricing(
                    city=city,
                    as_of=as_of,
                )
            )

        lifecycle = (
            self.lifecycle
            .apply(
                estimate_id=(
                    estimate_id
                ),
                actor_id=(
                    actor_id
                ),
                impact=impact,
                new_semantic=(
                    semantic
                ),
                new_pricing=(
                    pricing
                ),
            )
        )

        packet = (
            self._packet(
                estimate_id=(
                    estimate_id
                ),
                impact=impact,
                rerun_plan=(
                    rerun_plan
                ),
                lifecycle=(
                    lifecycle
                ),
            )
        )

        return (
            RevisionExecutionResult(
                impact=impact,
                rerun_plan=(
                    rerun_plan
                ),
                semantic=semantic,
                pricing=pricing,
                lifecycle=lifecycle,
                approval_packet=(
                    packet
                ),
            )
        )

    def execute_pdfs(
        self,
        *,
        old_path: str | Path,
        new_path: str | Path,
        previous_semantic: Any,
        estimate_id: str,
        actor_id: str,
        city: str,
        as_of: date,
        markup: MarkupPolicy,
        old_password: str | None = None,
        new_password: str | None = None,
        project_id: str | None = None,
        prevailing_wage_required: (
            bool
        ) = False,
        requested_labor_basis: (
            Any | None
        ) = None,
        allow_statewide_fallback: (
            bool
        ) = True,
    ) -> RevisionExecutionResult:
        old_document = (
            self.pdf_ingest
            .ingest(
                old_path,
                password=(
                    old_password
                ),
            )
        )

        new_document = (
            self.pdf_ingest
            .ingest(
                new_path,
                password=(
                    new_password
                ),
            )
        )

        return (
            self.execute_documents(
                old_document=(
                    old_document
                ),
                new_document=(
                    new_document
                ),
                previous_semantic=(
                    previous_semantic
                ),
                estimate_id=(
                    estimate_id
                ),
                actor_id=(
                    actor_id
                ),
                city=city,
                as_of=as_of,
                markup=markup,
                project_id=(
                    project_id
                ),
                prevailing_wage_required=(
                    prevailing_wage_required
                ),
                requested_labor_basis=(
                    requested_labor_basis
                ),
                allow_statewide_fallback=(
                    allow_statewide_fallback
                ),
            )
        )
