from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.preconstruction.details.resolver import (
    DetailResolution,
    DetailResolutionError,
    DrawingDetailResolver,
)
from leadbot_v2.goat.preconstruction.documents.intelligence import (
    ConstructionDocumentIntelligence,
    RawPage,
)
from leadbot_v2.goat.preconstruction.documents.models import (
    Discipline,
    DocumentSet,
)
from leadbot_v2.goat.preconstruction.estimating.workflow import (
    EstimateVersion,
    EstimateWorkflowService,
)
from leadbot_v2.goat.preconstruction.regional_costs.engine import (
    TexasMarket,
    TexasMarketRegistry,
    UnresolvedRateError,
)
from leadbot_v2.goat.preconstruction.rfi.engine import (
    PreconstructionRFIEngine,
    RFICandidate,
    RFISeverity,
)


class PlanTrade(str, Enum):
    CONCRETE = "concrete"
    EARTHWORK = "earthwork"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    ARCHITECTURAL = "architectural"
    COORDINATION = "coordination"


class PlanTask(str, Enum):
    CONCRETE_TAKEOFF = "concrete_takeoff"
    EARTHWORK_TAKEOFF = "earthwork_takeoff"
    ELECTRICAL_TAKEOFF = "electrical_takeoff"
    PLUMBING_TAKEOFF = "plumbing_takeoff"

    ARCHITECTURAL_REVIEW = "architectural_review"
    GENERAL_COORDINATION = "general_coordination"

    DETAIL_REVIEW = "detail_review"
    RFI_REVIEW = "rfi_review"

    MISSING_SCOPE = "missing_scope"
    PRICING_MARKET_REVIEW = "pricing_market_review"


@dataclass(frozen=True)
class PlanWorkItem:
    work_id: str

    trade: PlanTrade
    task: PlanTask

    sheet_number: str | None
    page_number: int | None

    source_ref: str | None

    reason: str

    confidence: float

    blocking: bool = False

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(
                "work item reason required"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence must be 0-1"
            )


@dataclass(frozen=True)
class WholePlanRequest:
    tenant_id: str
    business_unit_id: str

    project_name: str

    source_name: str
    pages: tuple[
        RawPage,
        ...
    ]

    city: str | None

    requested_trades: tuple[
        PlanTrade,
        ...
    ]

    document_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError(
                "tenant_id required"
            )

        if not self.business_unit_id.strip():
            raise ValueError(
                "business_unit_id required"
            )

        if not self.project_name.strip():
            raise ValueError(
                "project_name required"
            )

        if not self.source_name.strip():
            raise ValueError(
                "source_name required"
            )

        if not self.pages:
            raise ValueError(
                "whole-plan analysis requires pages"
            )

        if not self.requested_trades:
            raise ValueError(
                "at least one requested trade required"
            )


@dataclass(frozen=True)
class WholePlanAnalysis:
    document: DocumentSet

    market: TexasMarket | None

    discipline_counts: tuple[
        tuple[str, int],
        ...
    ]

    work_items: tuple[
        PlanWorkItem,
        ...
    ]

    rfis: tuple[
        RFICandidate,
        ...
    ]

    detail_resolutions: tuple[
        DetailResolution,
        ...
    ]

    blocking_reasons: tuple[
        str,
        ...
    ]

    requested_trades: tuple[
        PlanTrade,
        ...
    ]

    @property
    def ready_for_estimator(self) -> bool:
        return True

    @property
    def ready_for_final_pricing(self) -> bool:
        return (
            self.market is not None
            and not self.blocking_reasons
            and not any(
                item.blocking
                for item in self.work_items
            )
        )

    @property
    def work_item_count(self) -> int:
        return len(
            self.work_items
        )


DISCIPLINE_ROUTE = {
    Discipline.STRUCTURAL: (
        PlanTrade.CONCRETE,
        PlanTask.CONCRETE_TAKEOFF,
    ),

    Discipline.CIVIL: (
        PlanTrade.EARTHWORK,
        PlanTask.EARTHWORK_TAKEOFF,
    ),

    Discipline.ELECTRICAL: (
        PlanTrade.ELECTRICAL,
        PlanTask.ELECTRICAL_TAKEOFF,
    ),

    Discipline.PLUMBING: (
        PlanTrade.PLUMBING,
        PlanTask.PLUMBING_TAKEOFF,
    ),

    Discipline.ARCHITECTURAL: (
        PlanTrade.ARCHITECTURAL,
        PlanTask.ARCHITECTURAL_REVIEW,
    ),

    Discipline.GENERAL: (
        PlanTrade.COORDINATION,
        PlanTask.GENERAL_COORDINATION,
    ),
}


REQUIRED_DISCIPLINES = {
    PlanTrade.CONCRETE: {
        Discipline.STRUCTURAL,
    },

    PlanTrade.EARTHWORK: {
        Discipline.CIVIL,
    },

    PlanTrade.ELECTRICAL: {
        Discipline.ELECTRICAL,
    },

    PlanTrade.PLUMBING: {
        Discipline.PLUMBING,
    },

    PlanTrade.ARCHITECTURAL: {
        Discipline.ARCHITECTURAL,
    },
}


class WholePlanEstimatorOrchestrator:

    def __init__(self) -> None:
        self.documents = (
            ConstructionDocumentIntelligence()
        )

        self.rfis = (
            PreconstructionRFIEngine()
        )

    @staticmethod
    def _work_id() -> str:
        return (
            f"work_{uuid4().hex}"
        )

    @staticmethod
    def _dedupe_rfis(
        rfis: tuple[
            RFICandidate,
            ...
        ],
    ) -> tuple[
        RFICandidate,
        ...
    ]:
        seen = set()
        output = []

        for rfi in rfis:
            key = (
                rfi.title,
                tuple(
                    rfi.sheet_numbers
                ),
                rfi.conflict,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            output.append(
                rfi
            )

        return tuple(
            output
        )

    def analyze(
        self,
        request: WholePlanRequest,
    ) -> WholePlanAnalysis:
        document = (
            self.documents
            .analyze_document(
                source_name=(
                    request.source_name
                ),
                pages=request.pages,
                document_id=(
                    request.document_id
                ),
            )
        )

        blocking_reasons = []
        work_items = []

        market = None

        if request.city:
            try:
                market = (
                    TexasMarketRegistry
                    .resolve(
                        city=request.city
                    )
                )

            except UnresolvedRateError:
                blocking_reasons.append(
                    "Texas regional pricing "
                    f"market unresolved for "
                    f"{request.city}."
                )

                work_items.append(
                    PlanWorkItem(
                        work_id=(
                            self._work_id()
                        ),
                        trade=(
                            PlanTrade
                            .COORDINATION
                        ),
                        task=(
                            PlanTask
                            .PRICING_MARKET_REVIEW
                        ),
                        sheet_number=None,
                        page_number=None,
                        source_ref=None,
                        reason=(
                            "Project pricing market "
                            "must be confirmed before "
                            "final pricing."
                        ),
                        confidence=1.0,
                        blocking=True,
                    )
                )

        else:
            blocking_reasons.append(
                "Project city is missing; "
                "regional pricing market unresolved."
            )

            work_items.append(
                PlanWorkItem(
                    work_id=(
                        self._work_id()
                    ),
                    trade=(
                        PlanTrade.COORDINATION
                    ),
                    task=(
                        PlanTask
                        .PRICING_MARKET_REVIEW
                    ),
                    sheet_number=None,
                    page_number=None,
                    source_ref=None,
                    reason=(
                        "Project location required "
                        "for regional pricing."
                    ),
                    confidence=1.0,
                    blocking=True,
                )
            )

        disciplines = Counter(
            sheet.discipline
            for sheet in document.sheets
        )

        present_disciplines = set(
            disciplines
        )

        requested = set(
            request.requested_trades
        )

        for trade in request.requested_trades:
            required = (
                REQUIRED_DISCIPLINES
                .get(
                    trade,
                    set(),
                )
            )

            if not required:
                continue

            if not (
                required
                & present_disciplines
            ):
                message = (
                    f"Requested {trade.value} "
                    "scope has no governing "
                    "discipline sheets."
                )

                blocking_reasons.append(
                    message
                )

                work_items.append(
                    PlanWorkItem(
                        work_id=(
                            self._work_id()
                        ),
                        trade=trade,
                        task=(
                            PlanTask
                            .MISSING_SCOPE
                        ),
                        sheet_number=None,
                        page_number=None,
                        source_ref=None,
                        reason=message,
                        confidence=1.0,
                        blocking=True,
                    )
                )

        for sheet in document.sheets:
            route = (
                DISCIPLINE_ROUTE
                .get(
                    sheet.discipline
                )
            )

            if route is None:
                continue

            trade, task = route

            if (
                trade
                not in requested
                and trade
                not in {
                    PlanTrade.ARCHITECTURAL,
                    PlanTrade.COORDINATION,
                }
            ):
                continue

            work_items.append(
                PlanWorkItem(
                    work_id=(
                        self._work_id()
                    ),
                    trade=trade,
                    task=task,
                    sheet_number=(
                        sheet.sheet_number
                    ),
                    page_number=(
                        sheet.page_number
                    ),
                    source_ref=(
                        sheet.source_ref
                        or (
                            f"{request.source_name}"
                            f"#page="
                            f"{sheet.page_number}"
                        )
                    ),
                    reason=(
                        f"Route "
                        f"{sheet.sheet_number} "
                        f"to {trade.value} "
                        "estimating intelligence."
                    ),
                    confidence=(
                        sheet.confidence
                    ),
                    blocking=False,
                )
            )

        base_rfis = (
            self.rfis.analyze(
                document
            )
        )

        detail_resolutions = ()

        try:
            detail_resolutions = (
                DrawingDetailResolver
                .resolve_all(
                    document
                )
            )

            detail_rfis = (
                DrawingDetailResolver
                .unresolved_to_rfis(
                    detail_resolutions
                )
            )

        except DetailResolutionError as exc:
            detail_rfis = ()

            blocking_reasons.append(
                f"Drawing detail index "
                f"integrity failure: {exc}"
            )

        all_rfis = (
            self._dedupe_rfis(
                tuple(
                    base_rfis
                )
                + tuple(
                    detail_rfis
                )
            )
        )

        for rfi in all_rfis:
            blocking = (
                rfi.severity
                in {
                    RFISeverity.HIGH,
                    RFISeverity.CRITICAL,
                }
            )

            if blocking:
                blocking_reasons.append(
                    f"{rfi.title}: "
                    f"{rfi.conflict}"
                )

            work_items.append(
                PlanWorkItem(
                    work_id=(
                        self._work_id()
                    ),
                    trade=(
                        PlanTrade
                        .COORDINATION
                    ),
                    task=(
                        PlanTask.RFI_REVIEW
                    ),
                    sheet_number=(
                        rfi.sheet_numbers[0]
                        if rfi.sheet_numbers
                        else None
                    ),
                    page_number=None,
                    source_ref=(
                        rfi.evidence_refs[0]
                        if rfi.evidence_refs
                        else None
                    ),
                    reason=(
                        f"{rfi.title}: "
                        f"{rfi.request}"
                    ),
                    confidence=(
                        rfi.confidence
                    ),
                    blocking=blocking,
                )
            )

        return WholePlanAnalysis(
            document=document,
            market=market,
            discipline_counts=tuple(
                sorted(
                    (
                        discipline.value,
                        count,
                    )
                    for (
                        discipline,
                        count,
                    )
                    in disciplines.items()
                )
            ),
            work_items=tuple(
                work_items
            ),
            rfis=all_rfis,
            detail_resolutions=tuple(
                detail_resolutions
            ),
            blocking_reasons=tuple(
                dict.fromkeys(
                    blocking_reasons
                )
            ),
            requested_trades=(
                request.requested_trades
            ),
        )

    @staticmethod
    def initialize_estimate(
        *,
        request: WholePlanRequest,
        analysis: WholePlanAnalysis,
        workflow: EstimateWorkflowService,
        actor_id: str,
    ) -> EstimateVersion:
        estimate = (
            workflow.create_estimate(
                tenant_id=(
                    request.tenant_id
                ),
                business_unit_id=(
                    request
                    .business_unit_id
                ),
                project_name=(
                    request.project_name
                ),
                actor_id=actor_id,
            )
        )

        market = (
            analysis.market.value
            if analysis.market
            else "UNRESOLVED"
        )

        workflow.add_qualification(
            estimate_id=(
                estimate.estimate_id
            ),
            actor_id=actor_id,
            text=(
                "GOAT whole-plan analysis "
                f"market: {market}"
            ),
        )

        workflow.add_qualification(
            estimate_id=(
                estimate.estimate_id
            ),
            actor_id=actor_id,
            text=(
                "Requested estimating scopes: "
                + ", ".join(
                    trade.value
                    for trade
                    in analysis.requested_trades
                )
            ),
        )

        for reason in (
            analysis.blocking_reasons
        ):
            workflow.add_qualification(
                estimate_id=(
                    estimate.estimate_id
                ),
                actor_id=actor_id,
                text=(
                    f"GOAT BLOCKER: {reason}"
                ),
            )

        for rfi in analysis.rfis:
            workflow.add_rfi_effect(
                estimate_id=(
                    estimate.estimate_id
                ),
                actor_id=actor_id,
                rfi_id=rfi.rfi_id,
                description=(
                    f"{rfi.title}: "
                    f"{rfi.conflict}"
                ),
                cost_code="UNRESOLVED",
                cost_delta_cents=0,
                price_delta_cents=0,
                blocking=(
                    rfi.severity
                    in {
                        RFISeverity.HIGH,
                        RFISeverity.CRITICAL,
                    }
                ),
            )

        return (
            workflow.current_version(
                estimate.estimate_id
            )
        )
