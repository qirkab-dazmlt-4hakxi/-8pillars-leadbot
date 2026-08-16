from __future__ import annotations

import unittest

from copy import deepcopy
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from types import SimpleNamespace

from leadbot_v2.goat.revenue_intelligence import (
    ActionKind,
    ActionObservation,
    AdaptiveRevenueMemory,
    ActorType,
    DecisionTier,
    EvidenceIntegrityError,
    EvidenceLedger,
    GoatCRMAdapter,
    LeadCandidate,
    OutcomeAttributionEngine,
    OutcomeEvent,
    OutcomeType,
    PopulationDriftMonitor,
    ProbabilityCalibrationTracker,
    ProjectType,
    RelationType,
    RevenueIntelligenceEngine,
    RevenueRepository,
    ServiceArea,
    SourceType,
    StrategyEvolutionGovernor,
    normalize_email,
    normalize_phone,
)


BASE = datetime(
    2026,
    8,
    16,
    20,
    0,
    tzinfo=timezone.utc,
)


class FakeStore:
    def __init__(
        self,
    ) -> None:
        self.entities = {}

    def get_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        include_deleted=False,
    ):
        return deepcopy(
            self.entities.get(
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                )
            )
        )

    def list_entities(
        self,
        *,
        tenant_id,
        entity_type,
        include_deleted=False,
    ):
        result = []

        for (
            row_tenant,
            row_type,
            _,
        ), record in (
            self.entities.items()
        ):
            if (
                row_tenant
                == tenant_id
                and row_type
                == entity_type
            ):
                result.append(
                    deepcopy(
                        record
                    )
                )

        result.sort(
            key=lambda item:
                item.entity_id
        )

        return tuple(
            result
        )

    def put_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        payload,
        actor_id,
        expected_version=None,
    ):
        key = (
            tenant_id,
            entity_type,
            entity_id,
        )

        current = (
            self.entities.get(
                key
            )
        )

        if current is None:
            if (
                expected_version
                is not None
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = 1

        else:
            if (
                current.version
                != expected_version
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = (
                current.version + 1
            )

        record = SimpleNamespace(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            version=version,
            payload=deepcopy(
                payload
            ),
        )

        self.entities[
            key
        ] = record

        return deepcopy(
            record
        )


def homeowner(
    **overrides,
):
    payload = {
        "candidate_id":
            "candidate-1",
        "source_type":
            SourceType.NEXTDOOR,
        "raw_text":
            (
                "Looking for a concrete contractor "
                "to replace my driveway. "
                "Need an estimate this week."
            ),
        "observed_at":
            BASE,
        "source_uri":
            "https://example.test/post/1",
        "name":
            "Jane Homeowner",
        "phone":
            "(817) 555-0100",
        "email":
            "Jane@Example.com",
        "street":
            "100 Main Street",
        "city":
            "Fort Worth",
        "state":
            "TX",
        "postal_code":
            "76102",
        "metadata":
            {
                "source_confidence":
                    0.90,
            },
    }

    payload.update(
        overrides
    )

    return LeadCandidate(
        **payload
    )


def engine(
    *,
    repository=None,
):
    return RevenueIntelligenceEngine(
        service_area=ServiceArea(
            states=(
                "TX",
            ),
            cities=(
                "Fort Worth",
                "Dallas",
                "Arlington",
                "Frisco",
            ),
        ),
        repository=repository,
    )


class CanonicalTests(
    unittest.TestCase
):
    def test_phone(
        self,
    ):
        self.assertEqual(
            normalize_phone(
                "+1 (817) 555-0100"
            ),
            "8175550100",
        )

    def test_email(
        self,
    ):
        self.assertEqual(
            normalize_email(
                " Jane@Example.COM "
            ),
            "jane@example.com",
        )


class EvidenceTests(
    unittest.TestCase
):
    def test_chain_verifies(
        self,
    ):
        ledger = EvidenceLedger()

        ledger.append(
            homeowner()
        )

        ledger.append(
            homeowner(
                candidate_id="candidate-2",
                source_uri=(
                    "https://example.test/post/2"
                ),
            )
        )

        self.assertTrue(
            ledger.verify()
        )

    def test_tampering_detected(
        self,
    ):
        ledger = EvidenceLedger()

        ledger.append(
            homeowner()
        )

        ledger.tamper_for_test(
            0,
            text="tampered",
        )

        with self.assertRaises(
            EvidenceIntegrityError
        ):
            ledger.verify()


class IntelligenceTests(
    unittest.TestCase
):
    def test_homeowner_concrete_need_qualifies(
        self,
    ):
        result = engine().evaluate(
            homeowner()
        )

        self.assertIn(
            result.tier,
            {
                DecisionTier.QUALIFY,
                DecisionTier.PRIORITY,
                DecisionTier.EXECUTIVE,
            },
        )

        self.assertEqual(
            result.lead.actor_type,
            ActorType.HOMEOWNER,
        )

        self.assertEqual(
            result.lead.project_type,
            ProjectType.DRIVEWAY,
        )

        self.assertGreater(
            result.lead.features
            .concrete_intent,
            0.50,
        )

    def test_competitor_rejected(
        self,
    ):
        result = engine().evaluate(
            homeowner(
                candidate_id="competitor",
                company=(
                    "Competitor Concrete"
                ),
                raw_text=(
                    "We offer concrete driveways "
                    "and patios. Licensed contractor. "
                    "Free estimates. Call us today."
                ),
            )
        )

        self.assertEqual(
            result.tier,
            DecisionTier.REJECT,
        )

    def test_non_concrete_noise_rejected(
        self,
    ):
        result = engine().evaluate(
            homeowner(
                candidate_id="noise",
                raw_text=(
                    "Selling my old couch "
                    "this weekend."
                ),
            )
        )

        self.assertEqual(
            result.tier,
            DecisionTier.REJECT,
        )

    def test_outside_service_area_rejected(
        self,
    ):
        result = engine().evaluate(
            homeowner(
                candidate_id="outside",
                city="Tulsa",
                state="OK",
            )
        )

        self.assertEqual(
            result.tier,
            DecisionTier.REJECT,
        )

    def test_duplicate_suppression(
        self,
    ):
        ai = engine()

        first = ai.evaluate(
            homeowner()
        )

        second = ai.evaluate(
            homeowner(
                candidate_id="candidate-2",
                source_uri=(
                    "https://example.test/post/2"
                ),
                raw_text=(
                    "Need a quote on my "
                    "concrete driveway."
                ),
            ),
            existing=(
                first.lead,
            ),
        )

        self.assertEqual(
            second.lead.duplicate_of,
            first.lead.lead_id,
        )

        self.assertEqual(
            second.tier,
            DecisionTier.REJECT,
        )

    def test_external_communications_are_governed(
        self,
    ):
        result = engine().evaluate(
            homeowner()
        )

        if result.action.kind in {
            ActionKind.CALL,
            ActionKind.SMS,
            ActionKind.EMAIL,
        }:
            self.assertTrue(
                result.action
                .requires_human_approval
            )

    def test_graph_constructed(
        self,
    ):
        ai = engine()

        result = ai.evaluate(
            homeowner()
        )

        self.assertGreaterEqual(
            ai.graph.node_count(),
            2,
        )

        self.assertGreaterEqual(
            ai.graph.edge_count(),
            1,
        )

        neighbors = (
            ai.graph.neighbors(
                (
                    f"lead:"
                    f"{result.lead.lead_id}"
                ),
                relation=(
                    RelationType
                    .INTERESTED_IN
                ),
            )
        )

        self.assertEqual(
            len(
                neighbors
            ),
            1,
        )


class LearningTests(
    unittest.TestCase
):
    def test_source_memory_learns(
        self,
    ):
        memory = (
            AdaptiveRevenueMemory()
        )

        before = (
            memory.source_reliability(
                SourceType.NEXTDOOR
            )
        )

        for index in range(
            60
        ):
            memory.observe(
                OutcomeEvent(
                    lead_id=str(
                        index
                    ),
                    source_type=(
                        SourceType.NEXTDOOR
                    ),
                    outcome=(
                        OutcomeType.WON
                    ),
                    occurred_at=BASE,
                    action_kind=(
                        ActionKind.CALL
                    ),
                )
            )

        after = (
            memory.source_reliability(
                SourceType.NEXTDOOR
            )
        )

        self.assertGreater(
            after,
            before,
        )

        self.assertLessEqual(
            after,
            0.90,
        )

    def test_strategy_requires_evidence(
        self,
    ):
        memory = (
            AdaptiveRevenueMemory()
        )

        signal = (
            memory.source_signal(
                SourceType.BRAVE
            )
        )

        proposal = (
            StrategyEvolutionGovernor()
            .propose(
                signal,
                parameter=(
                    "brave_weight"
                ),
                current_value=0.50,
                now=BASE,
            )
        )

        self.assertIsNone(
            proposal
        )

    def test_strategy_proposal_after_large_sample(
        self,
    ):
        memory = (
            AdaptiveRevenueMemory()
        )

        for index in range(
            150
        ):
            memory.observe(
                OutcomeEvent(
                    lead_id=str(
                        index
                    ),
                    source_type=(
                        SourceType.BRAVE
                    ),
                    outcome=(
                        OutcomeType.WON
                    ),
                    occurred_at=BASE,
                )
            )

        proposal = (
            StrategyEvolutionGovernor()
            .propose(
                memory.source_signal(
                    SourceType.BRAVE
                ),
                parameter=(
                    "brave_weight"
                ),
                current_value=0.50,
                now=BASE,
            )
        )

        self.assertIsNotNone(
            proposal
        )

        self.assertTrue(
            proposal.shadow_required
        )

        self.assertTrue(
            proposal.canary_required
        )


class CalibrationTests(
    unittest.TestCase
):
    def test_calibration_snapshot(
        self,
    ):
        tracker = (
            ProbabilityCalibrationTracker()
        )

        tracker.observe(
            0.90,
            True,
        )

        tracker.observe(
            0.10,
            False,
        )

        snapshot = (
            tracker.snapshot()
        )

        self.assertEqual(
            snapshot.count,
            2,
        )

        self.assertLess(
            snapshot.brier_score,
            0.02,
        )


class DriftTests(
    unittest.TestCase
):
    def test_stable_population(
        self,
    ):
        monitor = (
            PopulationDriftMonitor()
        )

        values = [
            0.05,
            0.15,
            0.25,
            0.35,
            0.45,
            0.55,
            0.65,
            0.75,
            0.85,
            0.95,
        ] * 20

        result = monitor.compare(
            values,
            values,
        )

        self.assertEqual(
            result.level,
            "stable",
        )

        self.assertAlmostEqual(
            result.psi,
            0.0,
            places=6,
        )

    def test_material_shift_detected(
        self,
    ):
        monitor = (
            PopulationDriftMonitor()
        )

        baseline = [
            0.05
        ] * 100 + [
            0.15
        ] * 100

        current = [
            0.85
        ] * 100 + [
            0.95
        ] * 100

        result = monitor.compare(
            baseline,
            current,
        )

        self.assertEqual(
            result.level,
            "material",
        )


class SimulationTests(
    unittest.TestCase
):
    def test_simulation_deterministic(
        self,
    ):
        ai = engine()

        decision = ai.evaluate(
            homeowner()
        )

        first = ai.simulate_value(
            decision,
            nominal_project_value=(
                20_000
            ),
            trials=500,
            seed=77,
        )

        second = ai.simulate_value(
            decision,
            nominal_project_value=(
                20_000
            ),
            trials=500,
            seed=77,
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertGreaterEqual(
            first.mean_value,
            0.0,
        )


class AttributionTests(
    unittest.TestCase
):
    def test_latest_action_gets_more_credit(
        self,
    ):
        engine_ = (
            OutcomeAttributionEngine()
        )

        result = engine_.attribute(
            (
                ActionObservation(
                    action_id="email",
                    action_kind="email",
                    occurred_at=BASE,
                ),
                ActionObservation(
                    action_id="call",
                    action_kind="call",
                    occurred_at=(
                        BASE
                        + timedelta(
                            minutes=10
                        )
                    ),
                ),
            )
        )

        self.assertGreater(
            result[1].credit,
            result[0].credit,
        )

        self.assertAlmostEqual(
            sum(
                item.credit
                for item in result
            ),
            1.0,
            places=6,
        )


class RepositoryTests(
    unittest.TestCase
):
    def test_durable_round_trip(
        self,
    ):
        store = FakeStore()

        repository = (
            RevenueRepository(
                store,
                tenant_id="t1",
            )
        )

        ai = engine(
            repository=repository
        )

        decision = ai.evaluate(
            homeowner()
        )

        restored = (
            repository.list()
        )

        self.assertEqual(
            len(
                restored
            ),
            1,
        )

        self.assertEqual(
            restored[0].lead_id,
            decision.lead.lead_id,
        )

        self.assertEqual(
            restored[0].score,
            decision.lead.score,
        )


class FakeCRM:
    def __init__(
        self,
    ) -> None:
        self.actions = []

    def create_contact(
        self,
        name,
        phone=None,
        email=None,
    ):
        return {
            "contact_id":
                "contact-1",
            "name":
                name,
        }

    def create_lead(
        self,
        contact_id,
        source,
        notes=None,
    ):
        return {
            "lead_id":
                "lead-1",
            "contact_id":
                contact_id,
            "source":
                source,
        }

    def set_lead_next_action(
        self,
        lead_id,
        next_action,
    ):
        self.actions.append(
            (
                lead_id,
                next_action,
            )
        )


class AdapterTests(
    unittest.TestCase
):
    def test_crm_contract_adapter(
        self,
    ):
        decision = engine().evaluate(
            homeowner()
        )

        crm = FakeCRM()

        result = (
            GoatCRMAdapter(
                crm
            ).sync(
                decision.lead,
                decision.action,
            )
        )

        self.assertEqual(
            result[
                "contact_id"
            ],
            "contact-1",
        )

        self.assertEqual(
            result[
                "crm_lead_id"
            ],
            "lead-1",
        )

        self.assertEqual(
            len(
                crm.actions
            ),
            1,
        )


class BulkStressTests(
    unittest.TestCase
):
    def test_bulk_deterministic_intelligence(
        self,
    ):
        ai = engine()

        scores = []

        for index in range(
            400
        ):
            result = ai.evaluate(
                homeowner(
                    candidate_id=(
                        f"bulk-{index}"
                    ),
                    phone=(
                        f"817555"
                        f"{index % 10000:04d}"
                    ),
                    source_uri=(
                        f"https://example.test/"
                        f"bulk/{index}"
                    ),
                )
            )

            scores.append(
                result.lead
                .score
                .fit_probability
            )

        self.assertEqual(
            len(
                scores
            ),
            400,
        )

        self.assertTrue(
            all(
                0.0
                <= value
                <= 1.0
                for value
                in scores
            )
        )

        self.assertTrue(
            ai.provenance.verify()
        )


if __name__ == "__main__":
    unittest.main()
