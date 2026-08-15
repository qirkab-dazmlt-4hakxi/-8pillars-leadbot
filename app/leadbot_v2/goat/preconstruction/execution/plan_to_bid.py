from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)

from leadbot_v2.goat.preconstruction.bid_engine.session import (
    BidSessionError,
    BidSessionService,
    WorkStatus,
)

from leadbot_v2.goat.preconstruction.estimating.workflow import (
    EstimateWorkflowService,
)

from leadbot_v2.goat.preconstruction.orchestrator.whole_plan import (
    PlanTrade,
    WholePlanRequest,
)

from leadbot_v2.goat.preconstruction.pdf_ingest.engine import (
    PdfDocumentEvidence,
    PdfIngestEngine,
)

from leadbot_v2.goat.preconstruction.pricing.engine import (
    MarkupPolicy,
)

from leadbot_v2.goat.preconstruction.semantic.geometry import (
    SemanticGeometryResolver,
    SemanticTakeoff,
)

from leadbot_v2.goat.preconstruction.semantic.pricing_bridge import (
    PricingDisposition,
    ProjectBudgetHandoffBridge,
    ResolvedSemanticPrice,
    SemanticPricingResult,
    SemanticRegionalPricingService,
)


class PlanToBidError(RuntimeError):
    pass


class PlanToBidIntegrityError(
    PlanToBidError
):
    pass


class ReviewSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    BLOCKER = "blocker"


class ReviewSource(str, Enum):
    DOCUMENT = "document"
    SEMANTIC = "semantic"
    PRICING = "pricing"
    BID_SESSION = "bid_session"
    LINKAGE = "linkage"


@dataclass(frozen=True)
class ReviewQueueItem:
    code: str

    severity: ReviewSeverity

    source: ReviewSource

    message: str

    page_number: int | None = None

    sheet_number: str | None = None

    source_ref: str | None = None

    semantic_candidate_id: (
        str | None
    ) = None

    work_id: str | None = None


@dataclass(frozen=True)
class WorkScopeLink:
    work_id: str

    page_number: int | None

    trade: PlanTrade

    semantic_candidate_ids: tuple[
        str,
        ...
    ]

    estimate_line_ids: tuple[
        str,
        ...
    ]

    direct_cost_cents: int

    bid_price_cents: int

    requires_review: bool

    blocked: bool


@dataclass(frozen=True)
class PlanToBidResult:
    document_id: str

    project_name: str

    city: str

    market: str

    session_id: str

    estimate_id: str

    semantic_takeoff: SemanticTakeoff

    pricing: SemanticPricingResult

    work_links: tuple[
        WorkScopeLink,
        ...
    ]

    review_queue: tuple[
        ReviewQueueItem,
        ...
    ]

    bid_status: str

    bid_ready: bool

    proposal_ready: bool

    direct_cost_cents: int

    bid_price_cents: int

    @property
    def blockers(
        self,
    ) -> tuple[
        ReviewQueueItem,
        ...
    ]:
        return tuple(
            item
            for item
            in self.review_queue
            if (
                item.severity
                == ReviewSeverity.BLOCKER
            )
        )

    @property
    def review_items(
        self,
    ) -> tuple[
        ReviewQueueItem,
        ...
    ]:
        return tuple(
            item
            for item
            in self.review_queue
            if (
                item.severity
                == ReviewSeverity.REVIEW
            )
        )

    @property
    def unresolved_count(
        self,
    ) -> int:
        return (
            len(self.blockers)
            + len(self.review_items)
        )


@dataclass(frozen=True)
class _BundleProvenance:
    source_ref: str

    geometry_ids: tuple[
        str,
        ...
    ]

    text_refs: tuple[
        str,
        ...
    ]


@dataclass(frozen=True)
class _BundleScope:
    description: str

    direct_cost_cents: int

    bid_price_cents: int

    provenance: _BundleProvenance

    confidence: float

    requires_review: bool


TRADE_MAP = {
    "concrete":
        PlanTrade.CONCRETE,

    "earthwork":
        PlanTrade.EARTHWORK,

    "electrical":
        PlanTrade.ELECTRICAL,

    "plumbing":
        PlanTrade.PLUMBING,
}


TRADE_ORDER = (
    PlanTrade.CONCRETE,
    PlanTrade.EARTHWORK,
    PlanTrade.ELECTRICAL,
    PlanTrade.PLUMBING,
)


def _enum_text(
    value: Any,
) -> str:
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


def _line_id(
    value: Any,
) -> str:
    line_id = getattr(
        value,
        "line_id",
        None,
    )

    if line_id is None:
        raise PlanToBidIntegrityError(
            "Estimate workflow returned "
            "a line without line_id."
        )

    return str(
        line_id
    )


def _scope_refs(
    scope: ResolvedSemanticPrice,
) -> tuple[
    str,
    ...
]:
    provenance = (
        scope.provenance
    )

    return tuple(
        dict.fromkeys(
            (
                provenance.source_ref,
                *provenance.geometry_ids,
                *provenance.text_refs,
                *provenance.rate_refs,
            )
        )
    )


class IntegratedBidSessionService(
    BidSessionService
):
    """
    Extends the existing Bid Session service with
    a detailed pricing bundle operation.

    One plan work item may contain multiple approved
    semantic estimate lines with different cost codes.

    Each line is inserted separately so estimate
    provenance and cost-code granularity are retained,
    while the Bid Session work item receives the
    aggregate completion state.
    """

    def record_priced_bundle(
        self,
        *,
        session_id: str,
        work_id: str,
        actor_id: str,
        priced_scopes: tuple[
            ResolvedSemanticPrice,
            ...
        ],
    ):
        if not priced_scopes:
            raise BidSessionError(
                "priced bundle cannot be empty"
            )

        for scope in priced_scopes:
            if not scope.ready_for_estimate:
                raise BidSessionError(
                    "priced bundle contains "
                    "an unresolved scope"
                )

            if (
                scope.direct_cost_cents
                is None
                or scope.bid_price_cents
                is None
            ):
                raise BidSessionError(
                    "priced scope is missing "
                    "monetary values"
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
                f"work item not found: "
                f"{work_id}"
            )

        if target.status in {
            WorkStatus.PRICED,
            WorkStatus.RESOLVED,
        }:
            raise BidSessionError(
                "work item already completed"
            )

        lines = []

        for scope in priced_scopes:
            line = (
                self.workflow
                .add_manual_line(
                    estimate_id=(
                        session.estimate_id
                    ),
                    actor_id=actor_id,
                    description=(
                        scope.description
                    ),
                    cost_code=(
                        scope.cost_code
                    ),
                    quantity=(
                        scope.quantity
                    ),
                    unit=(
                        scope.unit
                    ),
                    direct_cost_cents=(
                        scope
                        .direct_cost_cents
                    ),
                    bid_price_cents=(
                        scope
                        .bid_price_cents
                    ),
                    source_refs=(
                        _scope_refs(
                            scope
                        )
                    ),
                    confidence=(
                        scope.confidence
                    ),
                    requires_review=(
                        scope
                        .requires_review
                    ),
                )
            )

            lines.append(
                line
            )

        direct = sum(
            int(
                scope
                .direct_cost_cents
                or 0
            )
            for scope
            in priced_scopes
        )

        bid = sum(
            int(
                scope
                .bid_price_cents
                or 0
            )
            for scope
            in priced_scopes
        )

        requires_review = any(
            scope.requires_review
            for scope
            in priced_scopes
        )

        if target.blocking:
            status = (
                WorkStatus.BLOCKED
            )

        elif requires_review:
            status = (
                WorkStatus
                .REVIEW_REQUIRED
            )

        else:
            status = (
                WorkStatus.PRICED
            )

        confidence = min(
            [
                float(
                    target.confidence
                )
            ]
            + [
                float(
                    scope.confidence
                )
                for scope
                in priced_scopes
            ]
        )

        updated_record = replace(
            target,
            status=status,
            blocking=(
                bool(
                    target.blocking
                )
                or requires_review
            ),
            confidence=confidence,
            estimate_line_id=(
                _line_id(
                    lines[0]
                )
            ),
            direct_cost_cents=(
                direct
            ),
            bid_price_cents=(
                bid
            ),
            review_note=(
                "Priced bundle requires "
                "estimator review."
                if requires_review
                else (
                    target.review_note
                    if target.blocking
                    else None
                )
            ),
        )

        session = (
            self._replace_record(
                session=session,
                work_id=work_id,
                replacement=(
                    updated_record
                ),
            )
        )

        session = (
            self._refresh(
                session
            )
        )

        self._event(
            session=session,
            event_type=(
                "bid_work.bundle_priced"
            ),
            actor_id=actor_id,
            payload={
                "work_id":
                    work_id,

                "estimate_line_ids":
                    [
                        _line_id(
                            line
                        )
                        for line
                        in lines
                    ],

                "cost_codes":
                    [
                        scope.cost_code
                        for scope
                        in priced_scopes
                    ],

                "direct_cost_cents":
                    direct,

                "bid_price_cents":
                    bid,

                "requires_review":
                    requires_review,
            },
        )

        return (
            session,
            tuple(
                lines
            ),
        )


class PlanToBidEngine:
    """
    Unified GOAT preconstruction execution path.

    Executes:
      native plan evidence
      → semantic geometry resolution
      → Texas regional pricing
      → Whole Plan / Bid Session
      → detailed estimate insertion
      → linkage verification
      → review queue
      → proposal-readiness decision

    It never creates a price for:
      unresolved semantic scope,
      unresolved quantity basis,
      missing regional rate,
      stale/expired/future rate,
      or failed provenance linkage.
    """

    def __init__(
        self,
        *,
        spine: InMemoryDataSpine,
        rate_resolver: Any | None = None,
        pdf_ingest: (
            PdfIngestEngine
            | None
        ) = None,
        semantic_resolver: (
            SemanticGeometryResolver
            | None
        ) = None,
        pricing_service: (
            SemanticRegionalPricingService
            | None
        ) = None,
        workflow: (
            EstimateWorkflowService
            | None
        ) = None,
        bid_service: Any | None = None,
    ) -> None:
        self.spine = spine

        self.pdf_ingest = (
            pdf_ingest
            or PdfIngestEngine()
        )

        self.semantic_resolver = (
            semantic_resolver
            or SemanticGeometryResolver()
        )

        if pricing_service is None:
            if rate_resolver is None:
                raise ValueError(
                    "rate_resolver or "
                    "pricing_service required"
                )

            pricing_service = (
                SemanticRegionalPricingService(
                    resolver=(
                        rate_resolver
                    )
                )
            )

        self.pricing_service = (
            pricing_service
        )

        if bid_service is not None:
            self.bid_service = (
                bid_service
            )

            self.workflow = (
                workflow
                or getattr(
                    bid_service,
                    "workflow",
                    None,
                )
            )

            if self.workflow is None:
                raise ValueError(
                    "workflow required when "
                    "custom bid_service has "
                    "no workflow attribute"
                )

        else:
            self.workflow = (
                workflow
                or EstimateWorkflowService(
                    spine=spine
                )
            )

            self.bid_service = (
                IntegratedBidSessionService(
                    spine=spine,
                    workflow=(
                        self.workflow
                    ),
                )
            )

    @staticmethod
    def _trade_for_scope(
        scope: ResolvedSemanticPrice,
    ) -> PlanTrade | None:
        return TRADE_MAP.get(
            scope.trade
            .strip()
            .lower()
        )

    @staticmethod
    def _candidate_map(
        semantic: SemanticTakeoff,
    ) -> dict[
        str,
        Any,
    ]:
        return {
            str(
                candidate
                .candidate_id
            ):
                candidate

            for candidate
            in semantic.candidates
        }

    @classmethod
    def _requested_trades(
        cls,
        pricing: SemanticPricingResult,
    ) -> tuple[
        PlanTrade,
        ...
    ]:
        detected = set()

        for scope in (
            pricing.scopes
        ):
            trade = (
                cls._trade_for_scope(
                    scope
                )
            )

            if trade is not None:
                detected.add(
                    trade
                )

        return tuple(
            trade
            for trade
            in TRADE_ORDER
            if trade
            in detected
        )

    @staticmethod
    def _raw_pages(
        document: Any,
    ) -> tuple:
        pages = tuple(
            getattr(
                document,
                "raw_pages",
                (),
            )
        )

        if not pages:
            raise PlanToBidIntegrityError(
                "Document has no RawPage "
                "bridge evidence."
            )

        return pages

    def _request(
        self,
        *,
        document: Any,
        tenant_id: str,
        business_unit_id: str,
        project_name: str,
        city: str,
        requested_trades: tuple[
            PlanTrade,
            ...
        ],
    ) -> WholePlanRequest:
        if not requested_trades:
            raise PlanToBidIntegrityError(
                "No supported bid trades "
                "were detected."
            )

        return WholePlanRequest(
            tenant_id=tenant_id,
            business_unit_id=(
                business_unit_id
            ),
            project_name=(
                project_name
            ),
            source_name=str(
                getattr(
                    document,
                    "file_name",
                    "plans.pdf",
                )
            ),
            pages=(
                self._raw_pages(
                    document
                )
            ),
            city=city,
            requested_trades=(
                requested_trades
            ),
            document_id=str(
                getattr(
                    document,
                    "document_id",
                    "unknown-document",
                )
            ),
        )

    @staticmethod
    def _pricing_groups(
        *,
        semantic: SemanticTakeoff,
        pricing: SemanticPricingResult,
    ) -> dict[
        tuple[
            int,
            PlanTrade,
        ],
        list[
            ResolvedSemanticPrice
        ],
    ]:
        candidate_map = (
            PlanToBidEngine
            ._candidate_map(
                semantic
            )
        )

        groups: dict[
            tuple[
                int,
                PlanTrade,
            ],
            list[
                ResolvedSemanticPrice
            ],
        ] = {}

        for scope in (
            pricing.scopes
        ):
            if not scope.ready_for_estimate:
                continue

            candidate = (
                candidate_map.get(
                    scope
                    .semantic_candidate_id
                )
            )

            if candidate is None:
                continue

            trade = (
                PlanToBidEngine
                ._trade_for_scope(
                    scope
                )
            )

            if trade is None:
                continue

            key = (
                int(
                    candidate
                    .page_number
                ),
                trade,
            )

            groups.setdefault(
                key,
                [],
            ).append(
                scope
            )

        return groups

    def _link_work(
        self,
        *,
        session: Any,
        semantic: SemanticTakeoff,
        pricing: SemanticPricingResult,
        actor_id: str,
    ) -> tuple[
        tuple[
            WorkScopeLink,
            ...
        ],
        tuple[
            str,
            ...
        ],
    ]:
        groups = (
            self._pricing_groups(
                semantic=semantic,
                pricing=pricing,
            )
        )

        consumed: set[
            tuple[
                int,
                PlanTrade,
            ]
        ] = set()

        linked_scope_ids: set[
            str
        ] = set()

        links = []

        for work in (
            session.work_records
        ):
            page_number = (
                int(
                    work.page_number
                )
                if work.page_number
                is not None
                else None
            )

            if page_number is None:
                continue

            key = (
                page_number,
                work.trade,
            )

            scopes = groups.get(
                key
            )

            if (
                not scopes
                or key
                in consumed
            ):
                continue

            (
                updated_session,
                lines,
            ) = (
                self.bid_service
                .record_priced_bundle(
                    session_id=(
                        session
                        .session_id
                    ),
                    work_id=(
                        work.work_id
                    ),
                    actor_id=(
                        actor_id
                    ),
                    priced_scopes=tuple(
                        scopes
                    ),
                )
            )

            consumed.add(
                key
            )

            for scope in scopes:
                linked_scope_ids.add(
                    scope
                    .semantic_candidate_id
                )

            updated_work = next(
                item
                for item
                in updated_session
                .work_records
                if item.work_id
                == work.work_id
            )

            scope_direct_cost = sum(
                int(
                    scope.direct_cost_cents
                    or 0
                )
                for scope
                in scopes
            )

            scope_bid_price = sum(
                int(
                    scope.bid_price_cents
                    or 0
                )
                for scope
                in scopes
            )

            direct_cost_cents = int(
                getattr(
                    updated_work,
                    "direct_cost_cents",
                    scope_direct_cost,
                )
                or scope_direct_cost
            )

            bid_price_cents = int(
                getattr(
                    updated_work,
                    "bid_price_cents",
                    scope_bid_price,
                )
                or scope_bid_price
            )

            updated_status = getattr(
                updated_work,
                "status",
                None,
            )

            requires_review = (
                updated_status
                == WorkStatus.REVIEW_REQUIRED
                or any(
                    scope.requires_review
                    for scope
                    in scopes
                )
            )

            blocked = (
                updated_status
                == WorkStatus.BLOCKED
                or bool(
                    getattr(
                        updated_work,
                        "blocking",
                        False,
                    )
                )
            )

            links.append(
                WorkScopeLink(
                    work_id=(
                        work.work_id
                    ),
                    page_number=(
                        page_number
                    ),
                    trade=(
                        work.trade
                    ),
                    semantic_candidate_ids=tuple(
                        scope.semantic_candidate_id
                        for scope
                        in scopes
                    ),
                    estimate_line_ids=tuple(
                        _line_id(line)
                        for line
                        in lines
                    ),
                    direct_cost_cents=(
                        direct_cost_cents
                    ),
                    bid_price_cents=(
                        bid_price_cents
                    ),
                    requires_review=(
                        requires_review
                    ),
                    blocked=(
                        blocked
                    ),
                )
            )

        unlinked = tuple(
            scope
            .semantic_candidate_id

            for scope
            in pricing.scopes

            if (
                scope.ready_for_estimate
                and scope
                .semantic_candidate_id
                not in linked_scope_ids
            )
        )

        return (
            tuple(
                links
            ),
            unlinked,
        )

    @staticmethod
    def _review_queue(
        *,
        document: Any,
        semantic: SemanticTakeoff,
        pricing: SemanticPricingResult,
        unlinked_scope_ids: tuple[
            str,
            ...
        ],
        bid_readiness: Any,
    ) -> tuple[
        ReviewQueueItem,
        ...
    ]:
        queue: list[
            ReviewQueueItem
        ] = []

        for finding in getattr(
            document,
            "blockers",
            (),
        ):
            queue.append(
                ReviewQueueItem(
                    code=str(
                        getattr(
                            finding,
                            "code",
                            "DOCUMENT_BLOCKER",
                        )
                    ),
                    severity=(
                        ReviewSeverity.BLOCKER
                    ),
                    source=(
                        ReviewSource.DOCUMENT
                    ),
                    message=str(
                        getattr(
                            finding,
                            "message",
                            "Document review "
                            "required.",
                        )
                    ),
                    page_number=(
                        getattr(
                            finding,
                            "page_number",
                            None,
                        )
                    ),
                    source_ref=(
                        getattr(
                            finding,
                            "source_ref",
                            None,
                        )
                    ),
                )
            )

        for finding in (
            semantic.findings
        ):
            severity_value = (
                _enum_text(
                    finding.severity
                ).lower()
            )

            if (
                severity_value
                == "blocker"
            ):
                severity = (
                    ReviewSeverity
                    .BLOCKER
                )

            else:
                severity = (
                    ReviewSeverity
                    .REVIEW
                )

            queue.append(
                ReviewQueueItem(
                    code=(
                        finding.code
                    ),
                    severity=severity,
                    source=(
                        ReviewSource.SEMANTIC
                    ),
                    message=(
                        finding.message
                    ),
                    page_number=(
                        finding.page_number
                    ),
                    source_ref=(
                        finding.source_ref
                    ),
                    semantic_candidate_id=(
                        finding.candidate_id
                    ),
                )
            )

        for scope in (
            pricing.scopes
        ):
            if (
                scope.disposition
                == PricingDisposition
                .PRICED
            ):
                continue

            if (
                scope.disposition
                in {
                    PricingDisposition
                    .PRICE_UNRESOLVED,

                    PricingDisposition
                    .BLOCKED,
                }
            ):
                severity = (
                    ReviewSeverity
                    .BLOCKER
                )

            else:
                severity = (
                    ReviewSeverity
                    .REVIEW
                )

            queue.append(
                ReviewQueueItem(
                    code=(
                        scope.disposition
                        .value
                        .upper()
                    ),
                    severity=severity,
                    source=(
                        ReviewSource.PRICING
                    ),
                    message=(
                        scope.unresolved_reason
                        or (
                            "Pricing review "
                            "required."
                        )
                    ),
                    source_ref=(
                        scope.provenance
                        .source_ref
                    ),
                    semantic_candidate_id=(
                        scope
                        .semantic_candidate_id
                    ),
                )
            )

        for scope_id in (
            unlinked_scope_ids
        ):
            queue.append(
                ReviewQueueItem(
                    code=(
                        "PRICED_SCOPE_UNLINKED"
                    ),
                    severity=(
                        ReviewSeverity.BLOCKER
                    ),
                    source=(
                        ReviewSource.LINKAGE
                    ),
                    message=(
                        "Priced scope could not "
                        "be linked to a Bid "
                        "Session work item."
                    ),
                    semantic_candidate_id=(
                        scope_id
                    ),
                )
            )

        if not bool(
            getattr(
                bid_readiness,
                "ready",
                False,
            )
        ):
            reasons = tuple(
                getattr(
                    bid_readiness,
                    "reasons",
                    (),
                )
            )

            if not reasons:
                reasons = (
                    "Bid Session is not ready.",
                )

            for reason in reasons:
                text = str(
                    reason
                )

                lower = (
                    text.lower()
                )

                severity = (
                    ReviewSeverity.BLOCKER
                    if any(
                        token in lower
                        for token
                        in (
                            "unresolved",
                            "rfi",
                            "incomplete",
                            "no priced",
                            "no ",
                        )
                    )
                    else ReviewSeverity
                    .REVIEW
                )

                queue.append(
                    ReviewQueueItem(
                        code=(
                            "BID_SESSION_NOT_READY"
                        ),
                        severity=severity,
                        source=(
                            ReviewSource
                            .BID_SESSION
                        ),
                        message=text,
                    )
                )

        deduped = {}

        for item in queue:
            key = (
                item.code,
                item.source.value,
                item.message,
                item.page_number,
                item.semantic_candidate_id,
                item.work_id,
            )

            deduped[
                key
            ] = item

        return tuple(
            deduped.values()
        )

    def run_document(
        self,
        *,
        document: Any,
        tenant_id: str,
        business_unit_id: str,
        project_name: str,
        city: str,
        actor_id: str,
        as_of: date,
        markup: MarkupPolicy,
        project_id: str | None = None,
        requested_trades: (
            tuple[
                PlanTrade,
                ...
            ]
            | None
        ) = None,
        prevailing_wage_required: (
            bool
        ) = False,
        requested_labor_basis: (
            Any | None
        ) = None,
        allow_statewide_fallback: (
            bool
        ) = True,
    ) -> PlanToBidResult:
        semantic = (
            self.semantic_resolver
            .resolve(
                document
            )
        )

        pricing = (
            self.pricing_service
            .price_takeoff(
                takeoff=semantic,
                city=city,
                as_of=as_of,
                markup=markup,
                project_id=project_id,
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

        resolved_trades = (
            requested_trades
            or self._requested_trades(
                pricing
            )
        )

        request = self._request(
            document=document,
            tenant_id=tenant_id,
            business_unit_id=(
                business_unit_id
            ),
            project_name=(
                project_name
            ),
            city=city,
            requested_trades=(
                resolved_trades
            ),
        )

        session = (
            self.bid_service
            .start(
                request=request,
                actor_id=actor_id,
            )
        )

        (
            links,
            unlinked,
        ) = self._link_work(
            session=session,
            semantic=semantic,
            pricing=pricing,
            actor_id=actor_id,
        )

        session = (
            self.bid_service
            .get(
                session.session_id
            )
        )

        readiness = (
            self.bid_service
            .readiness(
                session.session_id
            )
        )

        review_queue = (
            self._review_queue(
                document=document,
                semantic=semantic,
                pricing=pricing,
                unlinked_scope_ids=(
                    unlinked
                ),
                bid_readiness=(
                    readiness
                ),
            )
        )

        has_actionable_review = any(
            item.severity
            in {
                ReviewSeverity.REVIEW,
                ReviewSeverity.BLOCKER,
            }
            for item
            in review_queue
        )

        bid_ready = bool(
            getattr(
                readiness,
                "ready",
                False,
            )
        )

        proposal_ready = (
            pricing
            .ready_for_submission
            and bid_ready
            and not has_actionable_review
        )

        status = getattr(
            readiness,
            "status",
            "unknown",
        )

        return PlanToBidResult(
            document_id=str(
                getattr(
                    document,
                    "document_id",
                    "unknown-document",
                )
            ),
            project_name=(
                project_name
            ),
            city=city,
            market=(
                pricing.market
            ),
            session_id=(
                session.session_id
            ),
            estimate_id=(
                session.estimate_id
            ),
            semantic_takeoff=(
                semantic
            ),
            pricing=pricing,
            work_links=links,
            review_queue=(
                review_queue
            ),
            bid_status=(
                _enum_text(
                    status
                )
            ),
            bid_ready=(
                bid_ready
            ),
            proposal_ready=(
                proposal_ready
            ),
            direct_cost_cents=(
                pricing
                .direct_cost_cents
            ),
            bid_price_cents=(
                pricing
                .bid_price_cents
            ),
        )

    def run_pdf(
        self,
        *,
        path: str | Path,
        tenant_id: str,
        business_unit_id: str,
        project_name: str,
        city: str,
        actor_id: str,
        as_of: date,
        markup: MarkupPolicy,
        password: str | None = None,
        project_id: str | None = None,
        requested_trades: (
            tuple[
                PlanTrade,
                ...
            ]
            | None
        ) = None,
        prevailing_wage_required: (
            bool
        ) = False,
        requested_labor_basis: (
            Any | None
        ) = None,
        allow_statewide_fallback: (
            bool
        ) = True,
    ) -> PlanToBidResult:
        document = (
            self.pdf_ingest
            .ingest(
                path,
                password=password,
            )
        )

        return self.run_document(
            document=document,
            tenant_id=tenant_id,
            business_unit_id=(
                business_unit_id
            ),
            project_name=(
                project_name
            ),
            city=city,
            actor_id=actor_id,
            as_of=as_of,
            markup=markup,
            project_id=project_id,
            requested_trades=(
                requested_trades
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

    def proposal_snapshot(
        self,
        result: PlanToBidResult,
    ) -> Any:
        if not result.proposal_ready:
            raise PlanToBidError(
                "Proposal snapshot blocked: "
                "review queue is not clear."
            )

        return (
            self.workflow
            .proposal_snapshot(
                result.estimate_id
            )
        )

    def handoff_awarded_project(
        self,
        *,
        result: PlanToBidResult,
        project_id: str,
        principal: Any,
        finance: Any,
    ) -> Any:
        if not result.proposal_ready:
            raise PlanToBidError(
                "Project budget handoff blocked "
                "until proposal readiness "
                "requirements are satisfied."
            )

        return (
            ProjectBudgetHandoffBridge
            .handoff(
                workflow=(
                    self.workflow
                ),
                estimate_id=(
                    result.estimate_id
                ),
                project_id=(
                    project_id
                ),
                principal=(
                    principal
                ),
                finance=finance,
            )
        )
