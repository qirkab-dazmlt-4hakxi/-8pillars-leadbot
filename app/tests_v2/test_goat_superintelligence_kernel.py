from __future__ import annotations

import unittest

from copy import deepcopy

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from types import SimpleNamespace

from leadbot_v2.goat.superintelligence import (
    AdaptiveMemory,
    AutonomyLevel,
    BeamPlanner,
    CognitiveKernel,
    EvidenceLedger,
    Goal,
    GoalGraph,
    HypothesisEngine,
    InvariantViolation,
    LatencyBudget,
    LatencyMonitor,
    MonteCarloSimulator,
    PlanStep,
    QualificationSuite,
    SuperintelligenceRepository,
)


BASE = datetime(
    2026,
    8,
    17,
    5,
    30,
    tzinfo=timezone.utc,
)


class FakeStore:
    def __init__(
        self,
    ):
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
                current.version
                + 1
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


class EvidenceTests(
    unittest.TestCase
):
    def test_chain_integrity_and_tamper_detection(
        self,
    ):
        ledger = (
            EvidenceLedger()
        )

        one = ledger.append(
            source="official",
            claim="price",
            value=100,
            confidence=0.9,
            authority=1.0,
            observed_at=BASE,
        )

        two = ledger.append(
            source="official",
            claim="price",
            value=101,
            confidence=0.9,
            authority=1.0,
            observed_at=(
                BASE
                + timedelta(
                    minutes=1
                )
            ),
        )

        self.assertNotEqual(
            one.chain_hash,
            two.chain_hash,
        )

        self.assertTrue(
            ledger.verify()
        )

        ledger._entries[
            0
        ] = type(
            one
        )(
            **{
                **one.__dict__,
                "value":
                    999,
            }
        )

        with self.assertRaises(
            Exception
        ):
            ledger.verify()


class HypothesisTests(
    unittest.TestCase
):
    def test_support_and_opposition_move_posterior(
        self,
    ):
        ledger = (
            EvidenceLedger()
        )

        support = ledger.append(
            source="a",
            claim="x",
            value=True,
            confidence=0.95,
            authority=0.95,
            observed_at=BASE,
        )

        oppose = ledger.append(
            source="b",
            claim="x",
            value=False,
            confidence=0.40,
            authority=0.50,
            observed_at=BASE,
        )

        hypothesis = (
            HypothesisEngine()
            .evaluate(
                statement=(
                    "project remains profitable"
                ),
                prior=0.5,
                supporting=(
                    support,
                ),
                opposing=(
                    oppose,
                ),
            )
        )

        self.assertGreater(
            hypothesis.posterior,
            0.5,
        )


class GoalTests(
    unittest.TestCase
):
    def test_dependency_order(
        self,
    ):
        graph = (
            GoalGraph()
        )

        graph.add(
            Goal(
                goal_id="research",
                description="research",
                priority=0.8,
            )
        )

        graph.add(
            Goal(
                goal_id="decide",
                description="decide",
                priority=1.0,
                dependencies=(
                    "research",
                ),
            )
        )

        ordered = (
            graph.ordered()
        )

        self.assertEqual(
            tuple(
                goal.goal_id
                for goal
                in ordered
            ),
            (
                "research",
                "decide",
            ),
        )

    def test_cycle_rejected(
        self,
    ):
        graph = (
            GoalGraph()
        )

        graph.add(
            Goal(
                goal_id="a",
                description="a",
                priority=1.0,
                dependencies=(
                    "b",
                ),
            )
        )

        graph.add(
            Goal(
                goal_id="b",
                description="b",
                priority=1.0,
                dependencies=(
                    "a",
                ),
            )
        )

        with self.assertRaises(
            InvariantViolation
        ):
            graph.ordered()


class PlannerTests(
    unittest.TestCase
):
    def test_planner_prefers_positive_utility_with_prerequisite(
        self,
    ):
        planner = (
            BeamPlanner(
                beam_width=8,
                max_steps=4,
            )
        )

        steps = (
            PlanStep(
                "research",
                "research",
                expected_value=5,
                cost=1,
                risk=0.5,
                reversible=True,
            ),

            PlanStep(
                "buy",
                "buy",
                expected_value=10,
                cost=2,
                risk=1,
                reversible=False,
                prerequisites=(
                    "research",
                ),
            ),

            PlanStep(
                "noise",
                "noise",
                expected_value=1,
                cost=3,
                risk=1,
                reversible=True,
            ),
        )

        plan = planner.plan(
            steps
        )

        ids = tuple(
            step.step_id
            for step
            in plan.steps
        )

        self.assertIn(
            "research",
            ids,
        )

        self.assertIn(
            "buy",
            ids,
        )

        self.assertNotIn(
            "noise",
            ids,
        )


class SimulationTests(
    unittest.TestCase
):
    def test_seeded_monte_carlo_is_deterministic(
        self,
    ):
        simulator = (
            MonteCarloSimulator()
        )

        model = lambda rng: (
            rng.gauss(
                10.0,
                2.0,
            )
        )

        first = simulator.run(
            model,
            simulations=5000,
            seed=42,
        )

        second = simulator.run(
            model,
            simulations=5000,
            seed=42,
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertGreater(
            first.p95,
            first.p50,
        )

        self.assertGreater(
            first.p50,
            first.p05,
        )


class MemoryTests(
    unittest.TestCase
):
    def test_memory_recall_prefers_important_recent_items(
        self,
    ):
        memory = (
            AdaptiveMemory(
                half_life_days=30
            )
        )

        memory.remember(
            kind="fact",
            key="old-low",
            value=1,
            importance=0.1,
            confidence=0.3,
            now=(
                BASE
                - timedelta(
                    days=90
                )
            ),
        )

        memory.remember(
            kind="fact",
            key="new-high",
            value=2,
            importance=0.95,
            confidence=0.95,
            now=BASE,
        )

        recalled = (
            memory.recall(
                kind="fact",
                now=BASE,
            )
        )

        self.assertEqual(
            recalled[
                0
            ][
                1
            ].key,
            "new-high",
        )


class LatencyTests(
    unittest.TestCase
):
    def test_latency_budget(
        self,
    ):
        monitor = (
            LatencyMonitor()
        )

        monitor.set_budget(
            LatencyBudget(
                "route",
                10,
                20,
                30,
            )
        )

        for value in (
            5,
            6,
            7,
            8,
            9,
            10,
            12,
            15,
            18,
            20,
        ):
            monitor.observe(
                "route",
                value,
            )

        snapshot = (
            monitor.snapshot(
                "route"
            )
        )

        self.assertTrue(
            snapshot
            .within_budget
        )

        self.assertEqual(
            snapshot.samples,
            10,
        )


class KernelTests(
    unittest.TestCase
):
    def _kernel(
        self,
    ):
        kernel = (
            CognitiveKernel()
        )

        kernel.register_expert(
            expert_id=(
                "finance-a"
            ),
            domain="finance",
            handler=lambda ctx: {
                "answer":
                    "hold",
                "confidence":
                    0.92,
                "risk":
                    "low",
                "reasoning_summary":
                    (
                        "cash runway "
                        "too short"
                    ),
                "evidence_ids":
                    (
                        "e1",
                        "e2",
                    ),
            },
        )

        kernel.register_expert(
            expert_id=(
                "finance-b"
            ),
            domain="finance",
            handler=lambda ctx: {
                "answer":
                    "hold",
                "confidence":
                    0.86,
                "risk":
                    "moderate",
                "reasoning_summary":
                    (
                        "downside dominates"
                    ),
                "evidence_ids":
                    (
                        "e1",
                    ),
            },
        )

        return kernel

    def test_consensus_and_policy(
        self,
    ):
        kernel = (
            self._kernel()
        )

        decision = (
            kernel.reason(
                domain="finance",
                question=(
                    "deploy capital?"
                ),
                context={
                    "cash_runway_days":
                        20,
                },
                evidence=(
                    "e1",
                    "e2",
                ),
                requested_autonomy=(
                    AutonomyLevel
                    .EXECUTE_REVERSIBLE
                ),
            )
        )

        self.assertEqual(
            decision.recommendation,
            "hold",
        )

        self.assertGreater(
            decision.confidence,
            0.80,
        )

        self.assertFalse(
            decision
            .requires_human_approval
        )

    def test_irreversible_high_risk_requires_human(
        self,
    ):
        kernel = (
            CognitiveKernel()
        )

        kernel.register_expert(
            expert_id="legal-a",
            domain="legal",
            handler=lambda ctx: {
                "answer":
                    "file",
                "confidence":
                    0.95,
                "risk":
                    "high",
                "reasoning_summary":
                    (
                        "material legal consequence"
                    ),
            },
        )

        decision = (
            kernel.reason(
                domain="legal",
                question=(
                    "file action?"
                ),
                context={},
                evidence=(
                    "e1",
                    "e2",
                ),
                requested_autonomy=(
                    AutonomyLevel
                    .EXECUTE_BOUNDED
                ),
                irreversible=True,
                external_side_effect=True,
            )
        )

        self.assertTrue(
            decision
            .requires_human_approval
        )

        self.assertLessEqual(
            decision.autonomy_level,
            AutonomyLevel.PREPARE,
        )

    def test_low_evidence_triggers_critic(
        self,
    ):
        kernel = (
            self._kernel()
        )

        decision = (
            kernel.reason(
                domain="finance",
                question="deploy?",
                context={},
                evidence=(),
                requested_autonomy=(
                    AutonomyLevel
                    .RECOMMEND
                ),
            )
        )

        self.assertTrue(
            any(
                critique.critic_id
                == "evidence"
                for critique
                in decision.critiques
            )
        )

    def test_outcome_updates_calibration_and_weights(
        self,
    ):
        kernel = (
            self._kernel()
        )

        decision = (
            kernel.reason(
                domain="finance",
                question="deploy?",
                context={},
                evidence=(
                    "e1",
                    "e2",
                ),
            )
        )

        before = (
            kernel.learning
            .weight(
                "finance-a"
            )
        )

        kernel.record_outcome(
            decision_id=(
                decision
                .decision_id
            ),
            success=True,
            expected_answer=(
                "hold"
            ),
            observed_at=BASE,
        )

        after = (
            kernel.learning
            .weight(
                "finance-a"
            )
        )

        self.assertGreater(
            after,
            before,
        )

        self.assertEqual(
            kernel.calibration
            .snapshot()
            .samples,
            1,
        )

    def test_persistence_adapter(
        self,
    ):
        store = (
            FakeStore()
        )

        repository = (
            SuperintelligenceRepository(
                store,
                tenant_id=(
                    "tenant-1"
                ),
            )
        )

        kernel = (
            CognitiveKernel(
                repository=(
                    repository
                )
            )
        )

        kernel.register_expert(
            expert_id="ops",
            domain="ops",
            handler=lambda ctx: {
                "answer":
                    "continue",
                "confidence":
                    0.9,
                "risk":
                    "low",
                "reasoning_summary":
                    "healthy",
            },
        )

        decision = kernel.reason(
            domain="ops",
            question="continue?",
            context={},
            evidence=(
                "a",
                "b",
            ),
        )

        self.assertTrue(
            any(
                key[1]
                == (
                    "goat."
                    "superintelligence."
                    "decision"
                )
                for key
                in store.entities
            )
        )

        kernel.record_outcome(
            decision_id=(
                decision
                .decision_id
            ),
            success=True,
            observed_at=BASE,
        )

        self.assertTrue(
            any(
                key[1]
                == (
                    "goat."
                    "superintelligence."
                    "outcome"
                )
                for key
                in store.entities
            )
        )


class QualificationTests(
    unittest.TestCase
):
    def test_qualification_suite_surfaces_failure(
        self,
    ):
        suite = (
            QualificationSuite()
        )

        suite.add(
            "pass",
            lambda:
                "ok",
        )

        suite.add(
            "fail",
            lambda: (
                _ for _
                in ()
            ).throw(
                RuntimeError(
                    "boom"
                )
            ),
        )

        results = (
            suite.run()
        )

        self.assertEqual(
            tuple(
                result.passed
                for result
                in results
            ),
            (
                True,
                False,
            ),
        )

        with self.assertRaises(
            RuntimeError
        ):
            suite.require_all(
                results
            )


class StressTests(
    unittest.TestCase
):
    def test_1000_decisions(
        self,
    ):
        kernel = (
            CognitiveKernel()
        )

        kernel.register_expert(
            expert_id="fast-a",
            domain="stress",
            handler=lambda ctx: {
                "answer":
                    ctx[
                        "value"
                    ]
                    % 3,
                "confidence":
                    0.90,
                "risk":
                    "low",
                "reasoning_summary":
                    "deterministic",
            },
        )

        kernel.register_expert(
            expert_id="fast-b",
            domain="stress",
            handler=lambda ctx: {
                "answer":
                    ctx[
                        "value"
                    ]
                    % 3,
                "confidence":
                    0.85,
                "risk":
                    "low",
                "reasoning_summary":
                    "deterministic",
            },
        )

        for index in range(
            1000
        ):
            decision = (
                kernel.reason(
                    domain="stress",
                    question=(
                        f"q-{index}"
                    ),
                    context={
                        "value":
                            index,
                    },
                    evidence=(
                        "e1",
                        "e2",
                    ),
                )
            )

            self.assertEqual(
                decision
                .recommendation,
                index % 3,
            )

        self.assertEqual(
            kernel.memory.count(),
            1000,
        )

        self.assertEqual(
            kernel.latency
            .snapshot(
                "reason"
            )
            .samples,
            1000,
        )


if __name__ == "__main__":
    unittest.main()
