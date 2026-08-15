import unittest

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from leadbot_v2.goat.preconstruction.command_center.engine import (
    BidAuditIntegrityError,
    BidCaseState,
    BidCommandBlocked,
    BidCommandCenter,
    BidCommandConflict,
    BidIdempotencyConflict,
    BidOptimisticLockError,
    DeadlineRisk,
    OutcomeType,
)


UTC = timezone.utc


def now():
    return datetime(
        2026,
        8,
        15,
        16,
        0,
        tzinfo=UTC,
    )


class Finding:
    def __init__(
        self,
        code,
        severity,
        message="finding",
    ):
        self.code = code
        self.severity = SimpleNamespace(
            value=severity
        )
        self.message = message
        self.source_ref = None


class FakePackageControl:
    def __init__(
        self,
        *,
        revision="rev-1",
        ready=True,
        due_hours=72,
        findings=(),
    ):
        self.revision = revision
        self.ready = ready
        self.findings = tuple(
            findings
        )
        self.due_at = (
            now()
            + timedelta(
                hours=due_hours
            )
            if due_hours
            is not None
            else None
        )

        self.package = (
            SimpleNamespace(
                package_id="pkg-1",
                tenant_id="tenant",
                business_unit_id="twins",
                opportunity_id="opp-1",
                project_name=(
                    "Dallas Medical Center"
                ),
                city="Dallas",
            )
        )

    def get_package(
        self,
        package_id,
    ):
        if package_id != "pkg-1":
            raise KeyError(package_id)
        return self.package

    def execution_manifest(
        self,
        *,
        package_id,
        as_of=None,
    ):
        return SimpleNamespace(
            package_id=package_id,
            revision_id=(
                self.revision
            ),
            previous_revision_id=None,
            project_name=(
                self.package
                .project_name
            ),
            city="Dallas",
            opportunity_id="opp-1",
            gc_name="GC",
            client_name="Owner",
            package_source="direct_gc",
            due_at=self.due_at,
            ready_for_execution=(
                self.ready
            ),
            findings=self.findings,
        )

    def advance_revision(
        self,
        revision="rev-2",
    ):
        self.revision = revision


def initial_result(
    *,
    ready=True,
    direct=100_000,
    bid=140_000,
    issues=(),
):
    return SimpleNamespace(
        estimate_id="estimate-1",
        session_id="session-1",
        direct_cost_cents=direct,
        bid_price_cents=bid,
        proposal_ready=ready,
        review_queue=tuple(
            issues
        ),
    )


def revision_result(
    *,
    ready=True,
    direct_delta=10_000,
    bid_delta=20_000,
    issues=(),
    estimate_id="estimate-1",
):
    return SimpleNamespace(
        approval_packet=(
            SimpleNamespace(
                estimate_id=(
                    estimate_id
                ),
                financial_delta=(
                    SimpleNamespace(
                        direct_cost_delta_cents=(
                            direct_delta
                        ),
                        bid_price_delta_cents=(
                            bid_delta
                        ),
                    )
                ),
                ready_for_revised_proposal=(
                    ready
                ),
                approval_items=tuple(
                    issues
                ),
            )
        )
    )


def ready_case(
    *,
    dual_threshold=None,
):
    package = FakePackageControl()

    center = BidCommandCenter(
        package_control=package,
        dual_approval_threshold_cents=(
            dual_threshold
        ),
    )

    case = center.create_case(
        package_id="pkg-1",
        actor_id="creator",
        as_of=now(),
    )

    case = center.record_initial_result(
        case_id=case.case_id,
        actor_id="estimator",
        package_revision_id="rev-1",
        result=initial_result(),
        expected_version=(
            case.version
        ),
        as_of=now(),
    )

    return (
        center,
        package,
        case,
    )


class DeadlineTests(
    unittest.TestCase
):
    def test_unknown_deadline(self):
        self.assertEqual(
            BidCommandCenter.deadline_risk(
                None,
                as_of=now(),
            ),
            DeadlineRisk.UNKNOWN,
        )

    def test_expired_deadline(self):
        self.assertEqual(
            BidCommandCenter.deadline_risk(
                now()
                - timedelta(seconds=1),
                as_of=now(),
            ),
            DeadlineRisk.EXPIRED,
        )

    def test_critical_deadline(self):
        self.assertEqual(
            BidCommandCenter.deadline_risk(
                now()
                + timedelta(hours=1),
                as_of=now(),
            ),
            DeadlineRisk.CRITICAL,
        )

    def test_high_deadline(self):
        self.assertEqual(
            BidCommandCenter.deadline_risk(
                now()
                + timedelta(hours=8),
                as_of=now(),
            ),
            DeadlineRisk.HIGH,
        )

    def test_watch_deadline(self):
        self.assertEqual(
            BidCommandCenter.deadline_risk(
                now()
                + timedelta(hours=20),
                as_of=now(),
            ),
            DeadlineRisk.WATCH,
        )


class CreationTests(
    unittest.TestCase
):
    def test_ready_package_creates_ready_case(self):
        center = BidCommandCenter(
            package_control=(
                FakePackageControl()
            )
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="user",
            as_of=now(),
        )

        self.assertEqual(
            case.state,
            BidCaseState.READY,
        )

        self.assertEqual(
            case.authority_revision_id,
            "rev-1",
        )

    def test_blocked_package_creates_blocked_case(self):
        center = BidCommandCenter(
            package_control=(
                FakePackageControl(
                    ready=False,
                    findings=(
                        Finding(
                            "PLAN_SET_MISSING",
                            "blocker",
                        ),
                    ),
                )
            )
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="user",
            as_of=now(),
        )

        self.assertEqual(
            case.state,
            BidCaseState.BLOCKED,
        )

    def test_one_case_per_package(self):
        center = BidCommandCenter(
            package_control=(
                FakePackageControl()
            )
        )

        first = center.create_case(
            package_id="pkg-1",
            actor_id="a",
            as_of=now(),
        )

        second = center.create_case(
            package_id="pkg-1",
            actor_id="b",
            as_of=now(),
        )

        self.assertEqual(
            first.case_id,
            second.case_id,
        )


class InitialExecutionTests(
    unittest.TestCase
):
    def test_ready_result_moves_to_approval_ready(self):
        center = BidCommandCenter(
            package_control=(
                FakePackageControl()
            )
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        case = center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(),
            expected_version=(
                case.version
            ),
            as_of=now(),
        )

        self.assertEqual(
            case.state,
            BidCaseState
            .APPROVAL_READY,
        )

        self.assertEqual(
            case.bid_price_cents,
            140_000,
        )

    def test_stale_initial_revision_is_rejected(self):
        center = BidCommandCenter(
            package_control=(
                FakePackageControl(
                    revision="rev-2"
                )
            )
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        with self.assertRaises(
            BidCommandConflict
        ):
            center.record_initial_result(
                case_id=case.case_id,
                actor_id="estimator",
                package_revision_id="rev-1",
                result=initial_result(),
                as_of=now(),
            )

    def test_review_result_enters_review_state(self):
        issue = Finding(
            "RATE_REVIEW",
            "review",
        )

        center = BidCommandCenter(
            package_control=(
                FakePackageControl()
            )
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        case = center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(
                issues=(issue,)
            ),
            as_of=now(),
        )

        self.assertEqual(
            case.state,
            BidCaseState.REVIEW,
        )

    def test_bid_below_direct_cost_is_review(self):
        center = BidCommandCenter(
            package_control=(
                FakePackageControl()
            )
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        case = center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(
                direct=200_000,
                bid=150_000,
            ),
            as_of=now(),
        )

        self.assertEqual(
            case.state,
            BidCaseState.REVIEW,
        )

        self.assertIn(
            "BID_BELOW_DIRECT_COST",
            {
                issue.code
                for issue
                in case.issues
            },
        )


class ConcurrencyTests(
    unittest.TestCase
):
    def test_optimistic_lock_blocks_stale_command(self):
        center, _, case = ready_case()

        with self.assertRaises(
            BidOptimisticLockError
        ):
            center.resolve_issue(
                case_id=case.case_id,
                actor_id="user",
                code="anything",
                note="test",
                expected_version=1,
            )

    def test_idempotent_initial_replay(self):
        package = FakePackageControl()

        center = BidCommandCenter(
            package_control=package
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        first = center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(),
            idempotency_key="initial-1",
            as_of=now(),
        )

        second = center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(),
            idempotency_key="initial-1",
            as_of=now(),
        )

        self.assertEqual(
            first.version,
            second.version,
        )

        self.assertEqual(
            len(
                center.audit_records(
                    case.case_id
                )
            ),
            2,
        )

    def test_idempotency_key_conflict(self):
        package = FakePackageControl()

        center = BidCommandCenter(
            package_control=package
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(),
            idempotency_key="same-key",
            as_of=now(),
        )

        with self.assertRaises(
            BidIdempotencyConflict
        ):
            center.record_initial_result(
                case_id=case.case_id,
                actor_id="estimator",
                package_revision_id="rev-1",
                result=initial_result(
                    bid=150_000
                ),
                idempotency_key="same-key",
                as_of=now(),
            )


class RevisionTests(
    unittest.TestCase
):
    def test_new_authority_requires_revision(self):
        center, package, case = ready_case()

        package.advance_revision(
            "rev-2"
        )

        case = center.sync_authority(
            case_id=case.case_id,
            actor_id="system",
            as_of=now(),
            expected_version=(
                case.version
            ),
        )

        self.assertEqual(
            case.authority_revision_id,
            "rev-2",
        )

        self.assertEqual(
            case.state,
            BidCaseState.REVIEW,
        )

        self.assertEqual(
            case.processed_revision_id,
            "rev-1",
        )

    def test_revision_delta_updates_totals(self):
        center, package, case = ready_case()

        package.advance_revision(
            "rev-2"
        )

        case = center.sync_authority(
            case_id=case.case_id,
            actor_id="system",
            as_of=now(),
        )

        case = center.record_revision_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-2",
            result=revision_result(
                direct_delta=10_000,
                bid_delta=20_000,
            ),
            expected_version=(
                case.version
            ),
            as_of=now(),
        )

        self.assertEqual(
            case.direct_cost_cents,
            110_000,
        )

        self.assertEqual(
            case.bid_price_cents,
            160_000,
        )

        self.assertEqual(
            case.state,
            BidCaseState
            .APPROVAL_READY,
        )

    def test_revision_cannot_change_estimate_identity(self):
        center, package, case = ready_case()

        package.advance_revision(
            "rev-2"
        )

        case = center.sync_authority(
            case_id=case.case_id,
            actor_id="system",
            as_of=now(),
        )

        with self.assertRaises(
            BidCommandConflict
        ):
            center.record_revision_result(
                case_id=case.case_id,
                actor_id="estimator",
                package_revision_id="rev-2",
                result=revision_result(
                    estimate_id=(
                        "different-estimate"
                    )
                ),
                as_of=now(),
            )

    def test_revision_must_be_current_authority(self):
        center, package, case = ready_case()

        package.advance_revision(
            "rev-3"
        )

        with self.assertRaises(
            BidCommandConflict
        ):
            center.record_revision_result(
                case_id=case.case_id,
                actor_id="estimator",
                package_revision_id="rev-2",
                result=revision_result(),
                as_of=now(),
            )


class ReviewResolutionTests(
    unittest.TestCase
):
    def test_review_issue_can_be_resolved(self):
        package = FakePackageControl()

        center = BidCommandCenter(
            package_control=package
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        case = center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(
                issues=(
                    Finding(
                        "CHECK_RATE",
                        "review",
                    ),
                )
            ),
            as_of=now(),
        )

        case = center.resolve_issue(
            case_id=case.case_id,
            actor_id="estimator",
            code="CHECK_RATE",
            note=(
                "Supplier quote verified."
            ),
            expected_version=(
                case.version
            ),
        )

        self.assertEqual(
            case.state,
            BidCaseState
            .APPROVAL_READY,
        )

    def test_blocker_requires_privileged_override(self):
        package = FakePackageControl()

        center = BidCommandCenter(
            package_control=package
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        case = center.record_initial_result(
            case_id=case.case_id,
            actor_id="estimator",
            package_revision_id="rev-1",
            result=initial_result(
                ready=False,
                issues=(
                    Finding(
                        "BLOCK",
                        "blocker",
                    ),
                ),
            ),
            as_of=now(),
        )

        with self.assertRaises(
            BidCommandBlocked
        ):
            center.resolve_issue(
                case_id=case.case_id,
                actor_id="estimator",
                code="BLOCK",
                note="override",
            )

        case = center.resolve_issue(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            code="BLOCK",
            note=(
                "Documented executive "
                "exception after verification."
            ),
            allow_blocker_override=True,
        )

        self.assertFalse(
            any(
                issue.code == "BLOCK"
                for issue in case.issues
            )
        )


class ApprovalTests(
    unittest.TestCase
):
    def test_single_approval_policy(self):
        center, _, case = ready_case()

        case = center.approve(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            note="Approved",
            expected_version=(
                case.version
            ),
            as_of=now(),
        )

        self.assertEqual(
            case.state,
            BidCaseState.APPROVED,
        )

    def test_dual_approval_policy(self):
        center, _, case = ready_case(
            dual_threshold=100_000
        )

        first = center.approve(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            note="Approval one",
            as_of=now(),
        )

        self.assertEqual(
            first.state,
            BidCaseState
            .APPROVAL_READY,
        )

        second = center.approve(
            case_id=case.case_id,
            actor_id="vp",
            actor_role="vice_president",
            note="Approval two",
            expected_version=(
                first.version
            ),
            as_of=now(),
        )

        self.assertEqual(
            second.state,
            BidCaseState.APPROVED,
        )

    def test_unapproved_role_rejected(self):
        center, _, case = ready_case()

        with self.assertRaises(
            BidCommandBlocked
        ):
            center.approve(
                case_id=case.case_id,
                actor_id="sales",
                actor_role="sales",
                note="approve",
                as_of=now(),
            )


class SubmissionTests(
    unittest.TestCase
):
    def test_approved_bid_can_submit(self):
        center, _, case = ready_case()

        case = center.approve(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            note="Approved",
            as_of=now(),
        )

        case = center.submit(
            case_id=case.case_id,
            actor_id="estimator",
            note="Submitted to GC",
            external_reference=(
                "BC-12345"
            ),
            expected_version=(
                case.version
            ),
            as_of=now(),
        )

        self.assertEqual(
            case.state,
            BidCaseState.SUBMITTED,
        )

        self.assertEqual(
            case.submission
            .external_reference,
            "BC-12345",
        )

    def test_package_change_blocks_submission(self):
        center, package, case = ready_case()

        case = center.approve(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            note="Approved",
            as_of=now(),
        )

        package.advance_revision(
            "rev-2"
        )

        with self.assertRaises(
            BidCommandBlocked
        ):
            center.submit(
                case_id=case.case_id,
                actor_id="estimator",
                note="submit",
                as_of=now(),
            )

    def test_expired_deadline_blocks_submission(self):
        center, package, case = ready_case()

        case = center.approve(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            note="Approved",
            as_of=now(),
        )

        package.due_at = (
            now()
            - timedelta(minutes=1)
        )

        with self.assertRaises(
            BidCommandBlocked
        ):
            center.submit(
                case_id=case.case_id,
                actor_id="estimator",
                note="submit",
                as_of=now(),
            )


class OutcomeTests(
    unittest.TestCase
):
    def _submitted(self):
        center, _, case = ready_case()

        case = center.approve(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            note="Approved",
            as_of=now(),
        )

        case = center.submit(
            case_id=case.case_id,
            actor_id="estimator",
            note="Submitted",
            as_of=now(),
        )

        return center, case

    def test_award_closes_case(self):
        center, case = self._submitted()

        case = center.record_outcome(
            case_id=case.case_id,
            actor_id="president",
            outcome=(
                OutcomeType.AWARDED
            ),
            reason="Award received",
        )

        self.assertEqual(
            case.state,
            BidCaseState.AWARDED,
        )

    def test_loss_closes_case(self):
        center, case = self._submitted()

        case = center.record_outcome(
            case_id=case.case_id,
            actor_id="estimator",
            outcome=OutcomeType.LOST,
            reason=(
                "GC selected "
                "another contractor."
            ),
        )

        self.assertEqual(
            case.state,
            BidCaseState.LOST,
        )

    def test_no_bid_before_submission(self):
        package = FakePackageControl()

        center = BidCommandCenter(
            package_control=package
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        case = center.record_outcome(
            case_id=case.case_id,
            actor_id="president",
            outcome=(
                OutcomeType.NO_BID
            ),
            reason=(
                "Capacity conflict."
            ),
        )

        self.assertEqual(
            case.state,
            BidCaseState.NO_BID,
        )


class AuditTests(
    unittest.TestCase
):
    def test_audit_chain_verifies(self):
        center, _, case = ready_case()

        center.approve(
            case_id=case.case_id,
            actor_id="president",
            actor_role="president",
            note="Approved",
            as_of=now(),
        )

        self.assertTrue(
            center.verify_audit_chain(
                case.case_id
            )
        )

    def test_audit_tampering_detected(self):
        center, _, case = ready_case()

        records = (
            center._audits[
                case.case_id
            ]
        )

        records[0] = replace(
            records[0],
            event_hash="0" * 64,
        )

        with self.assertRaises(
            BidAuditIntegrityError
        ):
            center.verify_audit_chain(
                case.case_id
            )


class SnapshotTests(
    unittest.TestCase
):
    def test_snapshot_calculates_margin(self):
        center, _, case = ready_case()

        snapshot = center.snapshot(
            case.case_id,
            as_of=now(),
        )

        self.assertEqual(
            snapshot
            .gross_profit_cents,
            40_000,
        )

        self.assertGreater(
            snapshot
            .gross_margin_bps,
            0,
        )

        self.assertEqual(
            snapshot.next_action,
            "collect_approval",
        )

    def test_dual_policy_snapshot_reports_quorum(self):
        center, _, case = ready_case(
            dual_threshold=100_000
        )

        snapshot = center.snapshot(
            case.case_id,
            as_of=now(),
        )

        self.assertEqual(
            snapshot.approval_quorum,
            2,
        )

    def test_portfolio_orders_by_deadline(self):
        package = FakePackageControl()

        center = BidCommandCenter(
            package_control=package
        )

        case = center.create_case(
            package_id="pkg-1",
            actor_id="creator",
            as_of=now(),
        )

        portfolio = center.portfolio(
            as_of=now()
        )

        self.assertEqual(
            portfolio[0].case_id,
            case.case_id,
        )


if __name__ == "__main__":
    unittest.main()
