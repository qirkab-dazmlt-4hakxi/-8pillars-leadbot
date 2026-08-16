from __future__ import annotations

import json
import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from leadbot_v2.goat.workflow_control import (
    ActionRisk,
    ApprovalError,
    AuditIntegrityError,
    CompensationStatus,
    EffectKind,
    ExecutionPolicy,
    FailureClass,
    HashChainJournal,
    InMemoryWorkflowRepository,
    RetryPolicy,
    StepSpec,
    StepStatus,
    WorkflowConcurrencyConflict,
    WorkflowDefinitionError,
    WorkflowEngine,
    WorkflowInvariantError,
    WorkflowService,
    WorkflowSpec,
    WorkflowSpecNotRegistered,
    WorkflowStatus,
    state_from_dict,
    state_to_dict,
    topological_order,
    validate_spec,
)


BASE = datetime(
    2026,
    8,
    15,
    22,
    40,
    tzinfo=timezone.utc,
)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
):
    return RetryPolicy(
        max_attempts=max_attempts,
        base_delay_seconds=delay,
        multiplier=2.0,
        max_delay_seconds=30.0,
        jitter_fraction=0.0,
    )


def simple_spec(
    *,
    risk=ActionRisk.LOW,
    approval=False,
    retry_policy=None,
):
    return WorkflowSpec(
        name="test",
        version=1,
        steps=(
            StepSpec(
                step_id="a",
                action="test.a",
                risk=risk,
                requires_approval=approval,
                retry_policy=(
                    retry_policy
                    or retry()
                ),
            ),
        ),
    )


class DefinitionTests(
    unittest.TestCase
):
    def test_duplicate_step_rejected(
        self,
    ):
        spec = WorkflowSpec(
            name="dup",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "x",
                ),
                StepSpec(
                    "a",
                    "y",
                ),
            ),
        )

        with self.assertRaises(
            WorkflowDefinitionError
        ):
            validate_spec(
                spec
            )

    def test_unknown_dependency_rejected(
        self,
    ):
        spec = WorkflowSpec(
            name="bad-dep",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "x",
                    dependencies=(
                        "missing",
                    ),
                ),
            ),
        )

        with self.assertRaises(
            WorkflowDefinitionError
        ):
            validate_spec(
                spec
            )

    def test_cycle_rejected(
        self,
    ):
        spec = WorkflowSpec(
            name="cycle",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "x",
                    dependencies=(
                        "b",
                    ),
                ),
                StepSpec(
                    "b",
                    "y",
                    dependencies=(
                        "a",
                    ),
                ),
            ),
        )

        with self.assertRaises(
            WorkflowDefinitionError
        ):
            validate_spec(
                spec
            )

    def test_topological_order(
        self,
    ):
        spec = WorkflowSpec(
            name="dag",
            version=1,
            steps=(
                StepSpec(
                    "c",
                    "c",
                    (
                        "b",
                    ),
                ),
                StepSpec(
                    "a",
                    "a",
                ),
                StepSpec(
                    "b",
                    "b",
                    (
                        "a",
                    ),
                ),
            ),
        )

        self.assertEqual(
            topological_order(
                spec
            ),
            (
                "a",
                "b",
                "c",
            ),
        )


class RetryTests(
    unittest.TestCase
):
    def test_retry_delay_deterministic(
        self,
    ):
        policy = RetryPolicy()

        first = policy.delay_seconds(
            workflow_id="w",
            step_id="s",
            attempt=2,
        )

        second = policy.delay_seconds(
            workflow_id="w",
            step_id="s",
            attempt=2,
        )

        self.assertEqual(
            first,
            second,
        )

    def test_retry_delay_capped(
        self,
    ):
        policy = RetryPolicy(
            max_attempts=20,
            base_delay_seconds=10,
            multiplier=10,
            max_delay_seconds=15,
            jitter_fraction=0,
        )

        self.assertEqual(
            policy.delay_seconds(
                workflow_id="w",
                step_id="s",
                attempt=8,
            ),
            15,
        )


class PolicyTests(
    unittest.TestCase
):
    def test_high_risk_requires_approval(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec(
                risk=ActionRisk.HIGH
            )
        )

        state = engine.new_state(
            workflow_id="w1",
            tenant_id="t1",
            now=BASE,
        )

        effects = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            effects[0].kind,
            EffectKind.REQUEST_APPROVAL,
        )

    def test_blocked_action_denied(
        self,
    ):
        spec = WorkflowSpec(
            name="blocked",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "danger.delete",
                ),
            ),
        )

        policy = ExecutionPolicy(
            blocked_action_prefixes=(
                "danger.",
            )
        )

        engine = WorkflowEngine(
            spec,
            policy=policy,
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effects = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.FAILED,
        )

        self.assertEqual(
            effects[0].kind,
            EffectKind.ESCALATE,
        )

    def test_irreversible_requires_approval(
        self,
    ):
        spec = WorkflowSpec(
            name="irrev",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "external.commit",
                    side_effect=True,
                    irreversible=True,
                ),
            ),
        )

        engine = WorkflowEngine(
            spec
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effects = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            effects[0].kind,
            EffectKind.REQUEST_APPROVAL,
        )


class EngineTests(
    unittest.TestCase
):
    def test_low_risk_step_starts(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effects = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            len(effects),
            1,
        )

        self.assertEqual(
            effects[0].kind,
            EffectKind.RUN_STEP,
        )

        self.assertEqual(
            state.step_runs[
                "a"
            ].attempt,
            1,
        )

    def test_dependency_ordering(
        self,
    ):
        spec = WorkflowSpec(
            name="deps",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "a",
                ),
                StepSpec(
                    "b",
                    "b",
                    dependencies=(
                        "a",
                    ),
                ),
            ),
        )

        engine = WorkflowEngine(
            spec
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        first = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            [
                effect.step_id
                for effect
                in first
            ],
            [
                "a",
            ],
        )

        engine.complete_effect(
            state,
            effect_id=(
                first[0].effect_id
            ),
            success=True,
            now=BASE,
        )

        second = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            [
                effect.step_id
                for effect
                in second
            ],
            [
                "b",
            ],
        )

    def test_parallelism_cap(
        self,
    ):
        spec = WorkflowSpec(
            name="parallel",
            version=1,
            max_parallelism=2,
            steps=(
                StepSpec(
                    "a",
                    "a",
                ),
                StepSpec(
                    "b",
                    "b",
                ),
                StepSpec(
                    "c",
                    "c",
                ),
            ),
        )

        engine = WorkflowEngine(
            spec
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effects = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            len(effects),
            2,
        )

    def test_approval_then_run(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec(
                risk=ActionRisk.HIGH
            )
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        approval = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.approve(
            state,
            step_id="a",
            approver_id="owner",
            approval_id=(
                approval.payload[
                    "approval_id"
                ]
            ),
            now=BASE,
        )

        effects = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            effects[0].kind,
            EffectKind.RUN_STEP,
        )

    def test_wrong_approval_token_rejected(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec(
                risk=ActionRisk.HIGH
            )
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        engine.tick(
            state,
            now=BASE,
        )

        with self.assertRaises(
            ApprovalError
        ):
            engine.approve(
                state,
                step_id="a",
                approver_id="owner",
                approval_id="wrong",
                now=BASE,
            )

    def test_rejection_fails(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec(
                risk=ActionRisk.HIGH
            )
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        approval = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.reject(
            state,
            step_id="a",
            approver_id="owner",
            approval_id=(
                approval.payload[
                    "approval_id"
                ]
            ),
            reason="not approved",
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.FAILED,
        )

    def test_success_terminal(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effect = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                effect.effect_id
            ),
            success=True,
            output={
                "ok":
                    True,
            },
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.SUCCEEDED,
        )

        self.assertEqual(
            state.step_runs[
                "a"
            ].output,
            {
                "ok":
                    True,
            },
        )

    def test_transient_retry(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec(
                retry_policy=retry(
                    max_attempts=3,
                    delay=1,
                )
            )
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        first = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                first.effect_id
            ),
            success=False,
            failure_class=(
                FailureClass.TRANSIENT
            ),
            error="temporary",
            now=BASE,
        )

        self.assertEqual(
            state.step_runs[
                "a"
            ].status,
            StepStatus.WAITING_RETRY,
        )

        self.assertEqual(
            engine.tick(
                state,
                now=(
                    BASE
                    + timedelta(
                        milliseconds=500
                    )
                ),
            ),
            [],
        )

        second = engine.tick(
            state,
            now=(
                BASE
                + timedelta(
                    seconds=1
                )
            ),
        )[0]

        self.assertNotEqual(
            first.effect_id,
            second.effect_id,
        )

        self.assertEqual(
            state.step_runs[
                "a"
            ].attempt,
            2,
        )

    def test_retry_exhaustion_fails(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec(
                retry_policy=retry(
                    max_attempts=1
                )
            )
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effect = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                effect.effect_id
            ),
            success=False,
            failure_class=(
                FailureClass.TRANSIENT
            ),
            error="still broken",
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.FAILED,
        )

    def test_integrity_failure_quarantines(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effect = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                effect.effect_id
            ),
            success=False,
            failure_class=(
                FailureClass.INTEGRITY
            ),
            error="hash mismatch",
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.QUARANTINED,
        )

        escalation = engine.tick(
            state,
            now=BASE,
        )

        self.assertEqual(
            escalation[0].kind,
            EffectKind.ESCALATE,
        )

        self.assertEqual(
            engine.tick(
                state,
                now=BASE,
            ),
            [],
        )

    def test_timeout_fails_closed(
        self,
    ):
        spec = WorkflowSpec(
            name="timeout",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "a",
                    timeout_seconds=1,
                    retry_policy=retry(
                        max_attempts=1
                    ),
                ),
            ),
        )

        engine = WorkflowEngine(
            spec
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        engine.tick(
            state,
            now=BASE,
        )

        engine.tick(
            state,
            now=(
                BASE
                + timedelta(
                    seconds=2
                )
            ),
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.FAILED,
        )

    def test_duplicate_completion_idempotent(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        effect = engine.tick(
            state,
            now=BASE,
        )[0]

        first = engine.complete_effect(
            state,
            effect_id=(
                effect.effect_id
            ),
            success=True,
            now=BASE,
        )

        second = engine.complete_effect(
            state,
            effect_id=(
                effect.effect_id
            ),
            success=True,
            now=BASE,
        )

        self.assertTrue(
            first
        )

        self.assertFalse(
            second
        )

    def test_unknown_effect_rejected(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        with self.assertRaises(
            WorkflowInvariantError
        ):
            engine.complete_effect(
                state,
                effect_id="unknown",
                success=True,
                now=BASE,
            )

    def test_pause_resume(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        engine.pause(
            state,
            reason="maintenance",
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.PAUSED,
        )

        self.assertEqual(
            engine.tick(
                state,
                now=BASE,
            ),
            [],
        )

        engine.resume(
            state,
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.RUNNING,
        )


class CompensationTests(
    unittest.TestCase
):
    def make_spec(
        self,
    ):
        return WorkflowSpec(
            name="saga",
            version=1,
            steps=(
                StepSpec(
                    "a",
                    "create.a",
                    side_effect=True,
                    compensation_action=(
                        "delete.a"
                    ),
                    retry_policy=retry(
                        max_attempts=1
                    ),
                ),
                StepSpec(
                    "b",
                    "create.b",
                    dependencies=(
                        "a",
                    ),
                    side_effect=True,
                    compensation_action=(
                        "delete.b"
                    ),
                    retry_policy=retry(
                        max_attempts=1
                    ),
                ),
                StepSpec(
                    "c",
                    "validate.c",
                    dependencies=(
                        "b",
                    ),
                    retry_policy=retry(
                        max_attempts=1
                    ),
                ),
            ),
        )

    def test_reverse_compensation_order(
        self,
    ):
        engine = WorkflowEngine(
            self.make_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        a = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                a.effect_id
            ),
            success=True,
            now=BASE,
        )

        b = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                b.effect_id
            ),
            success=True,
            now=BASE,
        )

        c = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                c.effect_id
            ),
            success=False,
            failure_class=(
                FailureClass.VALIDATION
            ),
            error="bad result",
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.COMPENSATING,
        )

        comp_b = engine.tick(
            state,
            now=BASE,
        )[0]

        self.assertEqual(
            comp_b.action,
            "delete.b",
        )

        engine.complete_effect(
            state,
            effect_id=(
                comp_b.effect_id
            ),
            success=True,
            now=BASE,
        )

        comp_a = engine.tick(
            state,
            now=BASE,
        )[0]

        self.assertEqual(
            comp_a.action,
            "delete.a",
        )

        engine.complete_effect(
            state,
            effect_id=(
                comp_a.effect_id
            ),
            success=True,
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.FAILED,
        )

    def test_compensation_failure_quarantines(
        self,
    ):
        engine = WorkflowEngine(
            self.make_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        a = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                a.effect_id
            ),
            success=True,
            now=BASE,
        )

        b = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                b.effect_id
            ),
            success=True,
            now=BASE,
        )

        c = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                c.effect_id
            ),
            success=False,
            failure_class=(
                FailureClass.VALIDATION
            ),
            error="failure",
            now=BASE,
        )

        comp_b = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                comp_b.effect_id
            ),
            success=False,
            failure_class=(
                FailureClass.VALIDATION
            ),
            error="rollback failed",
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.QUARANTINED,
        )

        self.assertEqual(
            state.step_runs[
                "b"
            ].compensation_status,
            CompensationStatus.FAILED,
        )

    def test_cancel_compensates_completed(
        self,
    ):
        engine = WorkflowEngine(
            self.make_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            now=BASE,
        )

        a = engine.tick(
            state,
            now=BASE,
        )[0]

        engine.complete_effect(
            state,
            effect_id=(
                a.effect_id
            ),
            success=True,
            now=BASE,
        )

        engine.cancel(
            state,
            reason="operator cancelled",
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.COMPENSATING,
        )

        compensation = engine.tick(
            state,
            now=BASE,
        )[0]

        self.assertEqual(
            compensation.action,
            "delete.a",
        )

        engine.complete_effect(
            state,
            effect_id=(
                compensation.effect_id
            ),
            success=True,
            now=BASE,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.CANCELLED,
        )


class RepositoryTests(
    unittest.TestCase
):
    def test_occ_conflict(
        self,
    ):
        repo = (
            InMemoryWorkflowRepository()
        )

        engine = WorkflowEngine(
            simple_spec()
        )

        created = repo.create(
            engine.new_state(
                workflow_id="w",
                tenant_id="t",
                now=BASE,
            )
        )

        copy_a = repo.load(
            "w"
        )

        copy_b = repo.load(
            "w"
        )

        copy_a.metadata[
            "a"
        ] = 1

        saved = repo.save(
            copy_a,
            expected_revision=(
                created.revision
            ),
        )

        self.assertEqual(
            saved.revision,
            created.revision + 1,
        )

        copy_b.metadata[
            "b"
        ] = 2

        with self.assertRaises(
            WorkflowConcurrencyConflict
        ):
            repo.save(
                copy_b,
                expected_revision=(
                    created.revision
                ),
            )

    def test_repository_clone_isolation(
        self,
    ):
        repo = (
            InMemoryWorkflowRepository()
        )

        engine = WorkflowEngine(
            simple_spec()
        )

        repo.create(
            engine.new_state(
                workflow_id="w",
                tenant_id="t",
                now=BASE,
            )
        )

        loaded = repo.load(
            "w"
        )

        loaded.metadata[
            "mutated"
        ] = True

        fresh = repo.load(
            "w"
        )

        self.assertNotIn(
            "mutated",
            fresh.metadata,
        )


class AuditTests(
    unittest.TestCase
):
    def test_audit_chain_valid(
        self,
    ):
        journal = (
            HashChainJournal()
        )

        journal.append(
            workflow_id="w",
            tenant_id="t",
            event_type="one",
            actor_id="a",
            payload={
                "x":
                    1,
            },
            occurred_at=BASE,
        )

        journal.append(
            workflow_id="w",
            tenant_id="t",
            event_type="two",
            actor_id="a",
            payload={
                "x":
                    2,
            },
            occurred_at=BASE,
        )

        self.assertTrue(
            journal.verify()
        )

    def test_audit_tamper_detected(
        self,
    ):
        journal = (
            HashChainJournal()
        )

        journal.append(
            workflow_id="w",
            tenant_id="t",
            event_type="one",
            actor_id="a",
            payload={
                "x":
                    1,
            },
            occurred_at=BASE,
        )

        journal._entries[
            0
        ].payload[
            "x"
        ] = 999

        with self.assertRaises(
            AuditIntegrityError
        ):
            journal.verify()


class CodecTests(
    unittest.TestCase
):
    def test_round_trip(
        self,
    ):
        engine = WorkflowEngine(
            simple_spec()
        )

        state = engine.new_state(
            workflow_id="w",
            tenant_id="t",
            metadata={
                "project":
                    "P1",
            },
            now=BASE,
        )

        effect = engine.tick(
            state,
            now=BASE,
        )[0]

        payload = state_to_dict(
            state
        )

        json.dumps(
            payload
        )

        restored = state_from_dict(
            payload
        )

        self.assertEqual(
            state_to_dict(
                restored
            ),
            payload,
        )

        self.assertEqual(
            restored.step_runs[
                "a"
            ].active_effect_id,
            effect.effect_id,
        )


class ServiceTests(
    unittest.TestCase
):
    def test_service_lifecycle(
        self,
    ):
        repo = (
            InMemoryWorkflowRepository()
        )

        journal = (
            HashChainJournal()
        )

        service = WorkflowService(
            repo,
            journal=journal,
        )

        service.register(
            simple_spec()
        )

        state = service.start(
            spec_name="test",
            spec_version=1,
            workflow_id="w",
            tenant_id="t",
            actor_id="owner",
            now=BASE,
        )

        self.assertEqual(
            state.revision,
            1,
        )

        state, effects = service.tick(
            "w",
            now=BASE,
        )

        state, accepted = service.complete(
            "w",
            effect_id=(
                effects[0].effect_id
            ),
            success=True,
            actor_id="worker",
            output={
                "done":
                    True,
            },
            now=BASE,
        )

        self.assertTrue(
            accepted
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.SUCCEEDED,
        )

        self.assertTrue(
            journal.verify()
        )

    def test_unregistered_spec_rejected(
        self,
    ):
        service = WorkflowService(
            InMemoryWorkflowRepository()
        )

        with self.assertRaises(
            WorkflowSpecNotRegistered
        ):
            service.start(
                spec_name="missing",
                spec_version=1,
                workflow_id="w",
                tenant_id="t",
                actor_id="owner",
                now=BASE,
            )


if __name__ == "__main__":
    unittest.main()
