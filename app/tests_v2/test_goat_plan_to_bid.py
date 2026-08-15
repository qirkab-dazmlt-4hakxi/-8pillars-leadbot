import unittest

from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import SimpleNamespace

from leadbot_v2.goat.preconstruction.bid_engine.session import (
    BidSession,
    BidSessionError,
    BidSessionStatus,
    BidWorkRecord,
    WorkStatus,
)

from leadbot_v2.goat.preconstruction.documents.intelligence import (
    RawPage,
)

from leadbot_v2.goat.preconstruction.execution.plan_to_bid import (
    IntegratedBidSessionService,
    PlanToBidEngine,
    PlanToBidError,
    ReviewSeverity,
)

from leadbot_v2.goat.preconstruction.integration.vector_takeoff import (
    TradeKind,
)

from leadbot_v2.goat.preconstruction.orchestrator.whole_plan import (
    PlanTrade,
)

from leadbot_v2.goat.preconstruction.pricing.engine import (
    MarkupPolicy,
)

from leadbot_v2.goat.preconstruction.semantic.geometry import (
    SemanticKind,
    SemanticTakeoff,
)

from leadbot_v2.goat.preconstruction.semantic.pricing_bridge import (
    PricingDisposition,
    ResolvedSemanticPrice,
    ScopeProvenance,
    SemanticPricingResult,
)


@dataclass(frozen=True)
class FakeSemanticCandidate:
    candidate_id: str

    page_number: int

    trade: TradeKind


@dataclass(frozen=True)
class FakeDocument:
    document_id: str = "doc-1"

    file_name: str = "plans.pdf"

    raw_pages: tuple = (
        RawPage(
            page_number=1,
            text=(
                "SHEET S2.1\n"
                "FOUNDATION PLAN"
            ),
            source_ref=(
                "plans.pdf#page=1"
            ),
        ),
    )

    blockers: tuple = ()


class FakeSemanticResolver:
    def __init__(
        self,
        takeoff,
    ):
        self.takeoff = takeoff
        self.calls = []

    def resolve(
        self,
        document,
    ):
        self.calls.append(
            document
        )

        return self.takeoff


class FakePricingService:
    def __init__(
        self,
        result,
    ):
        self.result = result

        self.calls = []

    def price_takeoff(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.result


class FakePdfIngest:
    def __init__(
        self,
        document,
    ):
        self.document = document

        self.calls = []

    def ingest(
        self,
        path,
        *,
        password=None,
    ):
        self.calls.append(
            (
                str(path),
                password,
            )
        )

        return self.document


@dataclass
class FakeWork:
    work_id: str

    trade: PlanTrade

    page_number: int | None

    status: WorkStatus = (
        WorkStatus.OPEN
    )


@dataclass
class FakeSession:
    session_id: str

    estimate_id: str

    work_records: tuple


class FakeWorkflow:
    def __init__(
        self,
    ):
        self.handoffs = []

        self.snapshots = []

    def proposal_snapshot(
        self,
        estimate_id,
    ):
        self.snapshots.append(
            estimate_id
        )

        return {
            "estimate_id":
                estimate_id,
        }

    def handoff_to_project_budget(
        self,
        **kwargs,
    ):
        self.handoffs.append(
            kwargs
        )

        return kwargs


class FakeBidService:
    def __init__(
        self,
        *,
        work_records,
        ready=True,
        reasons=(),
    ):
        self.workflow = (
            FakeWorkflow()
        )

        self.session = (
            FakeSession(
                session_id="bid-1",
                estimate_id="estimate-1",
                work_records=tuple(
                    work_records
                ),
            )
        )

        self.ready = ready

        self.reasons = tuple(
            reasons
        )

        self.starts = []

        self.bundles = []

    def start(
        self,
        *,
        request,
        actor_id,
    ):
        self.starts.append(
            (
                request,
                actor_id,
            )
        )

        return self.session

    def get(
        self,
        session_id,
    ):
        return self.session

    def record_priced_bundle(
        self,
        *,
        session_id,
        work_id,
        actor_id,
        priced_scopes,
    ):
        self.bundles.append(
            {
                "session_id":
                    session_id,

                "work_id":
                    work_id,

                "actor_id":
                    actor_id,

                "priced_scopes":
                    tuple(
                        priced_scopes
                    ),
            }
        )

        lines = tuple(
            SimpleNamespace(
                line_id=(
                    f"line-{index}"
                )
            )
            for index, _
            in enumerate(
                priced_scopes,
                1,
            )
        )

        return (
            self.session,
            lines,
        )

    def readiness(
        self,
        session_id,
    ):
        return SimpleNamespace(
            ready=self.ready,

            reasons=self.reasons,

            status=SimpleNamespace(
                value=(
                    "ready_for_approval"
                    if self.ready
                    else "blocked"
                )
            ),
        )


def priced_scope(
    candidate_id,
    *,
    trade="concrete",
    disposition=(
        PricingDisposition.PRICED
    ),
    review=False,
    direct=10_000,
    bid=13_000,
    cost_code="03-3000",
):
    has_price = (
        disposition
        in {
            PricingDisposition
            .PRICED,

            PricingDisposition
            .REVIEW_REQUIRED,
        }
    )

    return ResolvedSemanticPrice(
        semantic_candidate_id=(
            candidate_id
        ),

        semantic_kind=(
            SemanticKind.SLAB
            if trade
            == "concrete"
            else (
                SemanticKind
                .CONDUIT_RUN
                if trade
                == "electrical"
                else (
                    SemanticKind
                    .PIPE_RUN
                    if trade
                    == "plumbing"
                    else SemanticKind
                    .TRENCH
                )
            )
        ),

        description=(
            "Test scope"
        ),

        trade=trade,

        cost_code=(
            cost_code
        ),

        quantity=10.0,

        unit="LF",

        unit_direct_cost_cents=(
            1000
            if has_price
            else None
        ),

        direct_cost_cents=(
            direct
            if has_price
            else None
        ),

        bid_price_cents=(
            bid
            if has_price
            else None
        ),

        disposition=(
            disposition
        ),

        unresolved_reason=(
            None
            if has_price
            else "PRICE_UNRESOLVED"
        ),

        rate_evidence=None,

        provenance=(
            ScopeProvenance(
                source_ref=(
                    "plans.pdf#page=1"
                ),
                geometry_ids=(
                    candidate_id,
                ),
                text_refs=(
                    "plans#span=1",
                ),
                rate_refs=(
                    "rate:test",
                ),
            )
        ),

        confidence=0.96,

        requires_review=(
            review
        ),
    )


def semantic_takeoff(
    candidates,
):
    return SemanticTakeoff(
        document_id="doc-1",

        candidates=tuple(
            candidates
        ),

        findings=(),
    )


def pricing_result(
    scopes,
):
    return SemanticPricingResult(
        city="Dallas",

        market=(
            "dallas_fort_worth"
        ),

        as_of=date(
            2026,
            8,
            15,
        ),

        scopes=tuple(
            scopes
        ),
    )


def engine(
    *,
    candidates,
    scopes,
    works,
    ready=True,
    reasons=(),
    document=None,
):
    semantic = semantic_takeoff(
        candidates
    )

    pricing = pricing_result(
        scopes
    )

    bid = FakeBidService(
        work_records=works,
        ready=ready,
        reasons=reasons,
    )

    workflow = bid.workflow

    return (
        PlanToBidEngine(
            spine=SimpleNamespace(),
            pdf_ingest=(
                FakePdfIngest(
                    document
                    or FakeDocument()
                )
            ),
            semantic_resolver=(
                FakeSemanticResolver(
                    semantic
                )
            ),
            pricing_service=(
                FakePricingService(
                    pricing
                )
            ),
            workflow=workflow,
            bid_service=bid,
        ),
        bid,
    )


def markup():
    return MarkupPolicy(
        overhead_bps=1000,
        contingency_bps=500,
        profit_bps=1500,
    )


class UnifiedExecutionTests(
    unittest.TestCase
):

    def test_priced_scope_links_to_matching_work(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        service, bid = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        self.assertEqual(
            len(
                bid.bundles
            ),
            1,
        )

        self.assertEqual(
            result
            .work_links[0]
            .semantic_candidate_ids,
            (
                "candidate-1",
            ),
        )

    def test_multiple_scopes_bundle_into_one_work(self):
        candidates = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            ),
            FakeSemanticCandidate(
                "candidate-2",
                1,
                TradeKind.CONCRETE,
            ),
        )

        scopes = (
            priced_scope(
                "candidate-1",
                cost_code="03-A",
            ),
            priced_scope(
                "candidate-2",
                cost_code="03-B",
            ),
        )

        service, bid = engine(
            candidates=candidates,
            scopes=scopes,
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        self.assertEqual(
            len(
                bid.bundles[0]
                ["priced_scopes"]
            ),
            2,
        )

        self.assertEqual(
            len(
                result
                .work_links[0]
                .estimate_line_ids
            ),
            2,
        )

    def test_unresolved_price_blocks_proposal(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1",
            disposition=(
                PricingDisposition
                .PRICE_UNRESOLVED
            ),
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
            ready=False,
            reasons=(
                "concrete pricing "
                "is incomplete.",
            ),
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        self.assertFalse(
            result
            .proposal_ready
        )

        self.assertTrue(
            result.blockers
        )

    def test_review_price_blocks_proposal(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1",
            disposition=(
                PricingDisposition
                .REVIEW_REQUIRED
            ),
            review=True,
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
            ready=False,
            reasons=(
                "Estimate contains "
                "priced lines "
                "requiring review.",
            ),
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        self.assertFalse(
            result
            .proposal_ready
        )

        self.assertTrue(
            result
            .review_items
        )

    def test_unlinked_priced_scope_is_blocker(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                2,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        codes = {
            item.code
            for item
            in result.blockers
        }

        self.assertIn(
            "PRICED_SCOPE_UNLINKED",
            codes,
        )

    def test_ready_pricing_and_bid_are_proposal_ready(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
            ready=True,
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        self.assertTrue(
            result
            .proposal_ready
        )

    def test_requested_trade_derived_from_price(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-e",
                1,
                TradeKind.ELECTRICAL,
            )
        )

        scope = priced_scope(
            "candidate-e",
            trade="electrical",
        )

        service, bid = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-e",
                    PlanTrade.ELECTRICAL,
                    1,
                ),
            ),
        )

        service.run_document(
            document=FakeDocument(),
            tenant_id="tenant",
            business_unit_id="bu",
            project_name="Project",
            city="Dallas",
            actor_id="estimator",
            as_of=date(
                2026,
                8,
                15,
            ),
            markup=markup(),
        )

        request = (
            bid.starts[0][0]
        )

        self.assertEqual(
            request
            .requested_trades,
            (
                PlanTrade.ELECTRICAL,
            ),
        )

    def test_run_pdf_uses_native_ingester(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
        )

        result = (
            service.run_pdf(
                path="plans.pdf",
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
                password="secret",
            )
        )

        self.assertEqual(
            result.document_id,
            "doc-1",
        )

        self.assertEqual(
            service
            .pdf_ingest
            .calls[0],
            (
                "plans.pdf",
                "secret",
            ),
        )

    def test_document_blocker_blocks_proposal(self):
        blocker = SimpleNamespace(
            code="RASTER_ONLY_PAGE",
            message=(
                "Raster review required"
            ),
            page_number=1,
            source_ref="plans#1",
        )

        document = FakeDocument(
            blockers=(
                blocker,
            )
        )

        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
            document=document,
        )

        result = (
            service.run_document(
                document=document,
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        self.assertFalse(
            result
            .proposal_ready
        )

        self.assertIn(
            "RASTER_ONLY_PAGE",
            {
                item.code
                for item
                in result.blockers
            },
        )

    def test_proposal_snapshot_requires_readiness(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
            ready=False,
            reasons=(
                "review required",
            ),
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        with self.assertRaises(
            PlanToBidError
        ):
            service.proposal_snapshot(
                result
            )

    def test_budget_handoff_delegates_existing_finance_path(self):
        candidate = (
            FakeSemanticCandidate(
                "candidate-1",
                1,
                TradeKind.CONCRETE,
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        service, _ = engine(
            candidates=(
                candidate,
            ),
            scopes=(
                scope,
            ),
            works=(
                FakeWork(
                    "work-1",
                    PlanTrade.CONCRETE,
                    1,
                ),
            ),
        )

        result = (
            service.run_document(
                document=FakeDocument(),
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                actor_id="estimator",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
            )
        )

        handoff = (
            service
            .handoff_awarded_project(
                result=result,
                project_id="project-1",
                principal="president",
                finance="finance-service",
            )
        )

        self.assertEqual(
            handoff[
                "project_id"
            ],
            "project-1",
        )


class DetailedBundleTests(
    unittest.TestCase
):

    def _service(
        self,
        *,
        blocking=False,
    ):
        workflow = SimpleNamespace(
            calls=[]
        )

        def add_manual_line(
            **kwargs,
        ):
            workflow.calls.append(
                kwargs
            )

            return SimpleNamespace(
                line_id=(
                    f"line-"
                    f"{len(workflow.calls)}"
                )
            )

        workflow.add_manual_line = (
            add_manual_line
        )

        service = (
            IntegratedBidSessionService
            .__new__(
                IntegratedBidSessionService
            )
        )

        service.workflow = (
            workflow
        )

        work = BidWorkRecord(
            work_id="work-1",
            trade=(
                PlanTrade.CONCRETE
            ),
            task="takeoff",
            status=(
                WorkStatus.OPEN
            ),
            sheet_number="S2.1",
            page_number=1,
            source_ref="plans#1",
            reason="test",
            blocking=blocking,
            confidence=0.99,
            updated_at=(
                datetime.now(
                    timezone.utc
                )
            ),
        )

        session = BidSession(
            session_id="bid-1",
            tenant_id="tenant",
            business_unit_id="bu",
            project_name="Project",
            estimate_id="estimate-1",
            created_by="estimator",
            created_at=(
                datetime.now(
                    timezone.utc
                )
            ),
            status=(
                BidSessionStatus
                .TAKEOFF_IN_PROGRESS
            ),
            analysis=(
                SimpleNamespace()
            ),
            work_records=(
                work,
            ),
        )

        service._sessions = {
            "bid-1":
                session
        }

        service._event = (
            lambda **kwargs:
                None
        )

        service._refresh = (
            lambda value:
                value
        )

        return (
            service,
            workflow,
        )

    def test_bundle_creates_one_line_per_scope(self):
        service, workflow = (
            self._service()
        )

        first = priced_scope(
            "candidate-1",
            cost_code="03-A",
            direct=10_000,
            bid=13_000,
        )

        second = priced_scope(
            "candidate-2",
            cost_code="03-B",
            direct=20_000,
            bid=26_000,
        )

        (
            session,
            lines,
        ) = (
            service
            .record_priced_bundle(
                session_id="bid-1",
                work_id="work-1",
                actor_id="estimator",
                priced_scopes=(
                    first,
                    second,
                ),
            )
        )

        self.assertEqual(
            len(
                workflow.calls
            ),
            2,
        )

        self.assertEqual(
            len(lines),
            2,
        )

        self.assertEqual(
            {
                call[
                    "cost_code"
                ]
                for call
                in workflow.calls
            },
            {
                "03-A",
                "03-B",
            },
        )

    def test_bundle_aggregates_work_totals(self):
        service, _ = (
            self._service()
        )

        first = priced_scope(
            "candidate-1",
            direct=10_000,
            bid=13_000,
        )

        second = priced_scope(
            "candidate-2",
            direct=20_000,
            bid=26_000,
        )

        (
            session,
            _,
        ) = (
            service
            .record_priced_bundle(
                session_id="bid-1",
                work_id="work-1",
                actor_id="estimator",
                priced_scopes=(
                    first,
                    second,
                ),
            )
        )

        work = (
            session
            .work_records[0]
        )

        self.assertEqual(
            work
            .direct_cost_cents,
            30_000,
        )

        self.assertEqual(
            work
            .bid_price_cents,
            39_000,
        )

    def test_bundle_preserves_rate_provenance(self):
        service, workflow = (
            self._service()
        )

        scope = priced_scope(
            "candidate-1"
        )

        service.record_priced_bundle(
            session_id="bid-1",
            work_id="work-1",
            actor_id="estimator",
            priced_scopes=(
                scope,
            ),
        )

        refs = (
            workflow.calls[0]
            ["source_refs"]
        )

        self.assertIn(
            "rate:test",
            refs,
        )

    def test_blocking_work_remains_blocked(self):
        service, _ = (
            self._service(
                blocking=True
            )
        )

        scope = priced_scope(
            "candidate-1"
        )

        (
            session,
            _,
        ) = (
            service
            .record_priced_bundle(
                session_id="bid-1",
                work_id="work-1",
                actor_id="estimator",
                priced_scopes=(
                    scope,
                ),
            )
        )

        self.assertEqual(
            session
            .work_records[0]
            .status,
            WorkStatus.BLOCKED,
        )

    def test_unresolved_scope_rejected_before_partial_insert(self):
        service, workflow = (
            self._service()
        )

        good = priced_scope(
            "candidate-1"
        )

        bad = priced_scope(
            "candidate-2",
            disposition=(
                PricingDisposition
                .PRICE_UNRESOLVED
            ),
        )

        with self.assertRaises(
            BidSessionError
        ):
            (
                service
                .record_priced_bundle(
                    session_id="bid-1",
                    work_id="work-1",
                    actor_id="estimator",
                    priced_scopes=(
                        good,
                        bad,
                    ),
                )
            )

        self.assertEqual(
            workflow.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()
