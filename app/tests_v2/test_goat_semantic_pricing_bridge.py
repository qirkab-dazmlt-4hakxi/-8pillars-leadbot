import unittest

from dataclasses import dataclass
from datetime import date

from leadbot_v2.goat.preconstruction.pricing.engine import (
    MarkupPolicy,
)

from leadbot_v2.goat.preconstruction.regional_costs.engine import (
    TexasMarket,
)

from leadbot_v2.goat.preconstruction.semantic.geometry import (
    DimensionalEvidence,
    GeometryKind,
    SemanticCandidate,
    SemanticEvidence,
    SemanticKind,
    SemanticTakeoff,
)

from leadbot_v2.goat.preconstruction.semantic.pricing_bridge import (
    PricingDisposition,
    PricingIntegrityError,
    ProjectBudgetHandoffBridge,
    SemanticBidSessionBridge,
    SemanticEstimateBridge,
    SemanticRegionalPricingService,
)


class Freshness:
    def __init__(
        self,
        value,
    ):
        self.value = value


@dataclass
class FakeRecord:
    record_id: str = "rate-1"

    source_kind: str = (
        "project_quote"
    )

    source_name: str = (
        "GOAT Supplier Quote"
    )

    market: object = (
        TexasMarket.DFW
    )

    city: str = "Dallas"

    county: str = (
        "Dallas"
    )

    postal_code: str = (
        "75201"
    )

    confidence: float = 0.98

    effective_date: date = (
        date(
            2026,
            8,
            1,
        )
    )

    expires_date: date = (
        date(
            2026,
            9,
            1,
        )
    )

    verified_at: date = (
        date(
            2026,
            8,
            14,
        )
    )

    material_cents_per_unit: int = 1000
    labor_cents_per_unit: int = 900
    equipment_cents_per_unit: int = 400
    subcontract_cents_per_unit: int = 0
    other_cents_per_unit: int = 200


@dataclass
class FakeResolved:
    record: object

    freshness: object = (
        "current"
    )


class FakeResolver:
    def __init__(
        self,
        resolved=None,
        error=None,
    ):
        self.resolved = (
            resolved
            or FakeResolved(
                FakeRecord()
            )
        )

        self.error = error

        self.calls = []

    def resolve(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        if self.error:
            raise self.error

        return self.resolved


class FakeMarketRegistry:
    def resolve(
        self,
        *,
        city=None,
        explicit_market=None,
    ):
        if (
            city
            == "Unknown"
        ):
            return (
                TexasMarket
                .STATEWIDE
            )

        return TexasMarket.DFW


class FakeWorkflow:
    def __init__(self):
        self.lines = []

        self.handoffs = []

    def add_manual_line(
        self,
        **kwargs,
    ):
        self.lines.append(
            kwargs
        )

        return kwargs

    def handoff_to_project_budget(
        self,
        **kwargs,
    ):
        self.handoffs.append(
            kwargs
        )

        return kwargs


class FakeBidService:
    def __init__(self):
        self.calls = []

    def record_priced_scope(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return kwargs


def evidence(
    kind,
):
    return (
        SemanticEvidence(
            kind=kind,
            text=(
                kind.value
            ),
            lexical_score=0.55,
            proximity_score=0.18,
            trade_score=0.14,
            geometry_score=0.10,
            dimension_score=0.08,
            total_score=0.99,
            distance_points=20,
            source_ref=(
                "plans#span=1"
            ),
        ),
    )


def semantic_candidate(
    kind,
    *,
    quantity=20.0,
    unit="LF",
    volume=None,
    review=False,
    auto=True,
    confidence=0.97,
):
    trade_map = {
        SemanticKind.SLAB:
            "concrete",

        SemanticKind.FOOTING:
            "concrete",

        SemanticKind.GRADE_BEAM:
            "concrete",

        SemanticKind.CONCRETE_WALL:
            "concrete",

        SemanticKind.TRENCH:
            "earthwork",

        SemanticKind.CONDUIT_RUN:
            "electrical",

        SemanticKind.PIPE_RUN:
            "plumbing",

        SemanticKind.UNRESOLVED:
            "coordination",
    }

    from leadbot_v2.goat.preconstruction.integration.vector_takeoff import (
        TradeKind,
    )

    return SemanticCandidate(
        candidate_id=(
            f"candidate:{kind.value}"
        ),

        semantic_kind=kind,

        geometry_kind=(
            GeometryKind.AREA
            if kind
            == SemanticKind.SLAB
            else GeometryKind.LINE
        ),

        trade=TradeKind(
            trade_map[
                kind
            ]
        ),

        page_number=1,

        sheet_number=(
            "S2.1"
        ),

        quantity=quantity,

        unit=unit,

        source_ref=(
            "plans.pdf"
            "#sha256=abc"
            "&page=1"
        ),

        semantic_confidence=(
            confidence
        ),

        measurement_confidence=(
            0.99
        ),

        evidence=(
            evidence(
                kind
            )
            if kind
            != SemanticKind
            .UNRESOLVED
            else ()
        ),

        dimensions=(
            DimensionalEvidence(
                thickness_inches=(
                    6.0
                    if kind
                    == SemanticKind.SLAB
                    else None
                ),
            )
        ),

        requires_review=(
            review
        ),

        auto_classified=(
            auto
        ),

        derived_volume_cy=(
            volume
        ),
    )


def service(
    resolver=None,
    confidence=0.80,
):
    return (
        SemanticRegionalPricingService(
            resolver=(
                resolver
                or FakeResolver()
            ),

            market_registry=(
                FakeMarketRegistry()
            ),

            minimum_rate_confidence=(
                confidence
            ),
        )
    )


def markup():
    return MarkupPolicy(
        overhead_bps=1000,
        contingency_bps=500,
        profit_bps=1500,
    )


class PricingBasisTests(
    unittest.TestCase
):

    def test_slab_uses_cy(self):
        candidate = (
            semantic_candidate(
                SemanticKind.SLAB,
                quantity=540,
                unit="SF",
                volume=10.0,
            )
        )

        resolver = FakeResolver()

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=(
                    candidate
                ),
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.unit,
            "CY",
        )

        self.assertEqual(
            result.quantity,
            10.0,
        )

        self.assertEqual(
            resolver.calls[0]
            ["trade"],
            "concrete",
        )

    def test_slab_without_cy_is_unresolved(self):
        candidate = (
            semantic_candidate(
                SemanticKind.SLAB,
                quantity=540,
                unit="SF",
                volume=None,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition
            .PRICE_UNRESOLVED,
        )

        self.assertIn(
            "QUANTITY_BASIS",
            result
            .unresolved_reason,
        )

    def test_grade_beam_uses_lf(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
                quantity=100,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.unit,
            "LF",
        )

        self.assertEqual(
            result.cost_code,
            "03-3000-GB",
        )

    def test_conduit_maps_electrical(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .CONDUIT_RUN,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.trade,
            "electrical",
        )

        self.assertEqual(
            result.cost_code,
            "26-0533",
        )

    def test_pipe_maps_plumbing(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .PIPE_RUN,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.trade,
            "plumbing",
        )


class MonetaryTests(
    unittest.TestCase
):

    def test_component_sum_is_direct_unit_cost(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
                quantity=10,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result
            .unit_direct_cost_cents,
            2500,
        )

    def test_quantity_extension(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
                quantity=10,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result
            .direct_cost_cents,
            25_000,
        )

    def test_markup_is_deterministic(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
                quantity=10,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        # Direct = $250.00.
        # OH 10% + contingency 5%
        # + profit 15% = $325.00.
        self.assertEqual(
            result
            .bid_price_cents,
            32_500,
        )


class FailClosedTests(
    unittest.TestCase
):

    def test_unresolved_semantic_not_priced(self):
        candidate = (
            semantic_candidate(
                SemanticKind.UNRESOLVED,
            )
        )

        resolver = FakeResolver()

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition.BLOCKED,
        )

        self.assertEqual(
            len(
                resolver.calls
            ),
            0,
        )

    def test_semantic_review_not_silently_priced(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
                review=True,
                auto=False,
            )
        )

        resolver = FakeResolver()

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition
            .REVIEW_REQUIRED,
        )

        self.assertFalse(
            result.has_price
        )

        self.assertEqual(
            len(
                resolver.calls
            ),
            0,
        )

    def test_missing_rate_becomes_unresolved(self):
        resolver = FakeResolver(
            error=LookupError(
                "no rate"
            )
        )

        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
            )
        )

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition
            .PRICE_UNRESOLVED,
        )

        self.assertIn(
            "PRICE_UNRESOLVED",
            result
            .unresolved_reason,
        )

    def test_stale_rate_is_rejected(self):
        resolver = FakeResolver(
            FakeResolved(
                FakeRecord(),
                freshness="stale",
            )
        )

        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
            )
        )

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition
            .PRICE_UNRESOLVED,
        )

        self.assertIn(
            "RATE_NOT_CURRENT",
            result
            .unresolved_reason,
        )

    def test_zero_rate_is_rejected(self):
        record = FakeRecord(
            material_cents_per_unit=0,
            labor_cents_per_unit=0,
            equipment_cents_per_unit=0,
            subcontract_cents_per_unit=0,
            other_cents_per_unit=0,
        )

        resolver = FakeResolver(
            FakeResolved(
                record,
                freshness="current",
            )
        )

        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
            )
        )

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition
            .PRICE_UNRESOLVED,
        )


class ConfidenceTests(
    unittest.TestCase
):

    def test_low_rate_confidence_requires_review(self):
        record = FakeRecord(
            confidence=0.60,
        )

        resolver = FakeResolver(
            FakeResolved(
                record,
                freshness="current",
            )
        )

        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
            )
        )

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition
            .REVIEW_REQUIRED,
        )

        self.assertTrue(
            result.has_price
        )

        self.assertTrue(
            result
            .requires_review
        )

    def test_unknown_freshness_requires_review(self):
        resolver = FakeResolver(
            FakeResolved(
                FakeRecord(),
                freshness=None,
            )
        )

        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
            )
        )

        result = (
            service(
                resolver
            )
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertEqual(
            result.disposition,
            PricingDisposition
            .REVIEW_REQUIRED,
        )


class ProvenanceTests(
    unittest.TestCase
):

    def test_plan_and_rate_refs_preserved(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
            )
        )

        result = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        self.assertIn(
            "plans.pdf",
            result
            .provenance
            .source_ref,
        )

        self.assertTrue(
            result
            .provenance
            .rate_refs
        )

        self.assertTrue(
            result
            .provenance
            .text_refs
        )


class FullPricingServiceTests(
    unittest.TestCase
):

    def test_city_builds_regional_context(self):
        resolver = FakeResolver()

        takeoff = (
            SemanticTakeoff(
                document_id="doc",
                candidates=(
                    semantic_candidate(
                        SemanticKind
                        .GRADE_BEAM,
                    ),
                ),
                findings=(),
            )
        )

        result = (
            service(
                resolver
            )
            .price_takeoff(
                takeoff=takeoff,
                city="Dallas",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=markup(),
                project_id="project-1",
            )
        )

        self.assertEqual(
            result.market,
            TexasMarket.DFW.value,
        )

        call = (
            resolver.calls[0]
        )

        self.assertTrue(
            call["context"]
            .require_current
        )

        self.assertEqual(
            call["context"]
            .project_id,
            "project-1",
        )

    def test_ready_result(self):
        takeoff = (
            SemanticTakeoff(
                document_id="doc",
                candidates=(
                    semantic_candidate(
                        SemanticKind
                        .GRADE_BEAM,
                    ),
                ),
                findings=(),
            )
        )

        result = (
            service()
            .price_takeoff(
                takeoff=takeoff,
                city="Dallas",
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
            .ready_for_submission
        )


class EstimateBridgeTests(
    unittest.TestCase
):

    def test_priced_scope_enters_estimate(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .GRADE_BEAM,
            )
        )

        scope = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        workflow = (
            FakeWorkflow()
        )

        SemanticEstimateBridge.add_scope(
            workflow=workflow,
            estimate_id="estimate-1",
            actor_id="estimator",
            scope=scope,
        )

        self.assertEqual(
            len(
                workflow.lines
            ),
            1,
        )

        line = (
            workflow.lines[0]
        )

        self.assertEqual(
            line[
                "direct_cost_cents"
            ],
            scope
            .direct_cost_cents,
        )

        self.assertIn(
            scope
            .rate_evidence
            .source_ref,
            line[
                "source_refs"
            ],
        )

    def test_unresolved_scope_cannot_enter_estimate(self):
        candidate = (
            semantic_candidate(
                SemanticKind.UNRESOLVED,
            )
        )

        scope = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        with self.assertRaises(
            PricingIntegrityError
        ):
            (
                SemanticEstimateBridge
                .add_scope(
                    workflow=(
                        FakeWorkflow()
                    ),
                    estimate_id=(
                        "estimate"
                    ),
                    actor_id=(
                        "estimator"
                    ),
                    scope=scope,
                )
            )


class BidSessionBridgeTests(
    unittest.TestCase
):

    def test_scope_enters_bid_session(self):
        candidate = (
            semantic_candidate(
                SemanticKind
                .CONDUIT_RUN,
            )
        )

        scope = (
            service()
            .price_candidate(
                candidate=candidate,
                context=object(),
                markup=markup(),
            )
        )

        bid = FakeBidService()

        SemanticBidSessionBridge.record_scope(
            bid_service=bid,
            session_id="bid-1",
            work_id="work-1",
            actor_id="estimator",
            scope=scope,
        )

        self.assertEqual(
            len(
                bid.calls
            ),
            1,
        )

        self.assertIs(
            bid.calls[0]
            ["priced_scope"],
            scope,
        )


class BudgetHandoffTests(
    unittest.TestCase
):

    def test_existing_finance_handoff_is_used(self):
        workflow = (
            FakeWorkflow()
        )

        result = (
            ProjectBudgetHandoffBridge
            .handoff(
                workflow=workflow,
                estimate_id="estimate-1",
                project_id="project-1",
                principal="president",
                finance="finance-service",
            )
        )

        self.assertEqual(
            len(
                workflow.handoffs
            ),
            1,
        )

        self.assertEqual(
            result[
                "project_id"
            ],
            "project-1",
        )


if __name__ == "__main__":
    unittest.main()
