from __future__ import annotations

import hashlib
import json
import uuid

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class BidCommandError(RuntimeError):
    pass


class BidCommandConflict(BidCommandError):
    pass


class BidCommandBlocked(BidCommandError):
    pass


class BidOptimisticLockError(BidCommandConflict):
    pass


class BidIdempotencyConflict(BidCommandConflict):
    pass


class BidAuditIntegrityError(BidCommandError):
    pass


class BidCaseState(str, Enum):
    INTAKE = "intake"
    READY = "ready"
    EXECUTING = "executing"
    REVIEW = "review"
    BLOCKED = "blocked"
    APPROVAL_READY = "approval_ready"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    AWARDED = "awarded"
    LOST = "lost"
    NO_BID = "no_bid"


class BidRunType(str, Enum):
    INITIAL = "initial"
    REVISION = "revision"


class DecisionSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    BLOCKER = "blocker"


class DeadlineRisk(str, Enum):
    UNKNOWN = "unknown"
    NONE = "none"
    WATCH = "watch"
    HIGH = "high"
    CRITICAL = "critical"
    EXPIRED = "expired"


class OutcomeType(str, Enum):
    AWARDED = "awarded"
    LOST = "lost"
    NO_BID = "no_bid"


@dataclass(frozen=True)
class BidDecisionIssue:
    code: str
    severity: DecisionSeverity
    message: str
    source: str
    source_ref: str | None = None


@dataclass(frozen=True)
class BidRunRecord:
    run_id: str
    run_type: BidRunType
    package_revision_id: str
    estimate_id: str
    session_id: str | None
    direct_cost_cents: int
    bid_price_cents: int
    direct_cost_delta_cents: int
    bid_price_delta_cents: int
    proposal_ready: bool
    issues: tuple[BidDecisionIssue, ...]
    recorded_at: datetime
    recorded_by: str


@dataclass(frozen=True)
class BidApproval:
    approval_id: str
    package_revision_id: str
    bid_price_cents: int
    actor_id: str
    actor_role: str
    note: str
    approved_at: datetime


@dataclass(frozen=True)
class BidSubmission:
    submission_id: str
    package_revision_id: str
    estimate_id: str
    bid_price_cents: int
    external_reference: str | None
    note: str
    submitted_at: datetime
    submitted_by: str


@dataclass(frozen=True)
class BidOutcome:
    outcome_id: str
    outcome: OutcomeType
    reason: str
    external_reference: str | None
    recorded_at: datetime
    recorded_by: str


@dataclass(frozen=True)
class BidAuditRecord:
    audit_id: str
    case_id: str
    sequence: int
    case_version: int
    action: str
    actor_id: str
    occurred_at: datetime
    payload_digest: str
    previous_hash: str
    event_hash: str


@dataclass(frozen=True)
class BidCase:
    case_id: str
    package_id: str
    tenant_id: str
    business_unit_id: str
    opportunity_id: str | None
    project_name: str
    city: str
    state: BidCaseState
    authority_revision_id: str
    processed_revision_id: str | None
    estimate_id: str | None
    session_id: str | None
    direct_cost_cents: int
    bid_price_cents: int
    due_at: datetime | None
    issues: tuple[BidDecisionIssue, ...]
    runs: tuple[BidRunRecord, ...]
    approvals: tuple[BidApproval, ...]
    submission: BidSubmission | None
    outcome: BidOutcome | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class BidCommandSnapshot:
    case_id: str
    package_id: str
    project_name: str
    opportunity_id: str | None
    state: BidCaseState
    authority_revision_id: str
    processed_revision_id: str | None
    estimate_id: str | None
    session_id: str | None
    direct_cost_cents: int
    bid_price_cents: int
    gross_profit_cents: int
    gross_margin_bps: int | None
    due_at: datetime | None
    due_in_seconds: int | None
    deadline_risk: DeadlineRisk
    unresolved_reviews: int
    blockers: int
    approval_count: int
    approval_quorum: int
    run_count: int
    ready_to_submit: bool
    next_action: str
    version: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _text(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw)


def _required(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _aware(value: datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _money(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} cannot be boolean")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be integer cents") from exc
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def _severity(value: Any) -> DecisionSeverity:
    text = _text(value).strip().lower()
    if text == "blocker":
        return DecisionSeverity.BLOCKER
    if text == "info":
        return DecisionSeverity.INFO
    return DecisionSeverity.REVIEW


def _stable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _stable(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple, set)):
        return [_stable(v) for v in value]
    if hasattr(value, "__dict__"):
        return {
            str(k): _stable(v)
            for k, v in sorted(vars(value).items())
            if not str(k).startswith("_")
        }
    return value


def _digest(value: Any) -> str:
    body = json.dumps(
        _stable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


class BidCommandCenter:
    """
    High-assurance control plane for one live bid case per authoritative
    bid package.

    This service does not perform takeoff itself. It governs outputs from
    the GOAT plan-to-bid and revision execution engines.

    Guarantees:
      * one authoritative package revision at a time;
      * optimistic concurrency for all mutating commands;
      * idempotent mutation replay;
      * stale revision results cannot overwrite current authority;
      * estimate identity cannot silently change during addenda;
      * prior approvals do not approve a later package revision;
      * submission requires current document authority and approval quorum;
      * deadline expiration blocks submission;
      * every mutation enters a tamper-evident audit chain.
    """

    def __init__(
        self,
        *,
        package_control: Any,
        approval_roles: set[str] | None = None,
        dual_approval_threshold_cents: int | None = None,
    ) -> None:
        self.package_control = package_control
        self.approval_roles = {
            item.strip().lower()
            for item in (
                approval_roles
                or {
                    "president",
                    "vice_president",
                    "senior_estimator",
                }
            )
        }

        if dual_approval_threshold_cents is not None:
            dual_approval_threshold_cents = _money(
                dual_approval_threshold_cents,
                "dual_approval_threshold_cents",
            )
            if dual_approval_threshold_cents == 0:
                raise ValueError(
                    "dual_approval_threshold_cents must be positive"
                )

        self.dual_approval_threshold_cents = (
            dual_approval_threshold_cents
        )

        self._cases: dict[str, BidCase] = {}
        self._case_by_package: dict[str, str] = {}
        self._audits: dict[str, list[BidAuditRecord]] = {}
        self._idempotency: dict[
            tuple[str, str],
            tuple[str, BidCase],
        ] = {}

    def _case(self, case_id: str) -> BidCase:
        result = self._cases.get(case_id)
        if result is None:
            raise KeyError(f"bid case not found: {case_id}")
        return result

    def _manifest(
        self,
        package_id: str,
        as_of: datetime,
    ) -> Any:
        return self.package_control.execution_manifest(
            package_id=package_id,
            as_of=as_of,
        )

    def _package(self, package_id: str) -> Any:
        return self.package_control.get_package(package_id)

    @staticmethod
    def deadline_risk(
        due_at: datetime | None,
        *,
        as_of: datetime,
    ) -> DeadlineRisk:
        as_of = _aware(as_of, "as_of")
        due_at = _aware(due_at, "due_at")

        if due_at is None:
            return DeadlineRisk.UNKNOWN

        seconds = int((due_at - as_of).total_seconds())

        if seconds <= 0:
            return DeadlineRisk.EXPIRED
        if seconds <= 2 * 60 * 60:
            return DeadlineRisk.CRITICAL
        if seconds <= 12 * 60 * 60:
            return DeadlineRisk.HIGH
        if seconds <= 24 * 60 * 60:
            return DeadlineRisk.WATCH
        return DeadlineRisk.NONE

    @staticmethod
    def _manifest_issues(manifest: Any) -> tuple[BidDecisionIssue, ...]:
        result = []

        for finding in getattr(manifest, "findings", ()):
            result.append(
                BidDecisionIssue(
                    code=str(
                        getattr(
                            finding,
                            "code",
                            "PACKAGE_FINDING",
                        )
                    ),
                    severity=_severity(
                        getattr(
                            finding,
                            "severity",
                            "review",
                        )
                    ),
                    message=str(
                        getattr(
                            finding,
                            "message",
                            "Package review required.",
                        )
                    ),
                    source="bid_package",
                    source_ref=getattr(
                        finding,
                        "source_ref",
                        None,
                    ),
                )
            )

        return tuple(result)

    @staticmethod
    def _external_issues(
        values: Any,
        *,
        source: str,
    ) -> tuple[BidDecisionIssue, ...]:
        result = []

        for item in values or ():
            result.append(
                BidDecisionIssue(
                    code=str(
                        getattr(
                            item,
                            "code",
                            "EXECUTION_FINDING",
                        )
                    ),
                    severity=_severity(
                        getattr(
                            item,
                            "severity",
                            "review",
                        )
                    ),
                    message=str(
                        getattr(
                            item,
                            "message",
                            "Execution review required.",
                        )
                    ),
                    source=source,
                    source_ref=getattr(
                        item,
                        "source_ref",
                        None,
                    ),
                )
            )

        return tuple(result)

    @staticmethod
    def _dedupe_issues(
        issues: tuple[BidDecisionIssue, ...] | list[BidDecisionIssue],
    ) -> tuple[BidDecisionIssue, ...]:
        unique = {}

        for issue in issues:
            key = (
                issue.code,
                issue.severity.value,
                issue.message,
                issue.source,
                issue.source_ref,
            )
            unique[key] = issue

        return tuple(unique.values())

    @staticmethod
    def _state_from_execution(
        issues: tuple[BidDecisionIssue, ...],
        *,
        proposal_ready: bool,
    ) -> BidCaseState:
        if any(
            item.severity == DecisionSeverity.BLOCKER
            for item in issues
        ):
            return BidCaseState.BLOCKED

        if any(
            item.severity == DecisionSeverity.REVIEW
            for item in issues
        ):
            return BidCaseState.REVIEW

        if proposal_ready:
            return BidCaseState.APPROVAL_READY

        return BidCaseState.BLOCKED

    @staticmethod
    def _issue_counts(
        issues: tuple[BidDecisionIssue, ...],
    ) -> tuple[int, int]:
        reviews = sum(
            1
            for item in issues
            if item.severity == DecisionSeverity.REVIEW
        )
        blockers = sum(
            1
            for item in issues
            if item.severity == DecisionSeverity.BLOCKER
        )
        return reviews, blockers

    def _approval_quorum_for(
        self,
        case: BidCase,
    ) -> int:
        threshold = self.dual_approval_threshold_cents

        if (
            threshold is not None
            and case.bid_price_cents >= threshold
        ):
            return 2

        return 1

    def _current_approval_actors(
        self,
        case: BidCase,
    ) -> set[str]:
        return {
            approval.actor_id
            for approval in case.approvals
            if (
                approval.package_revision_id
                == case.processed_revision_id
                and approval.bid_price_cents
                == case.bid_price_cents
            )
        }

    def _append_audit(
        self,
        case: BidCase,
        *,
        action: str,
        actor_id: str,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> BidAuditRecord:
        records = self._audits.setdefault(
            case.case_id,
            [],
        )

        sequence = len(records) + 1
        previous_hash = (
            records[-1].event_hash
            if records
            else "GENESIS"
        )

        payload_digest = _digest(payload)

        material = {
            "case_id": case.case_id,
            "sequence": sequence,
            "case_version": case.version,
            "action": action,
            "actor_id": actor_id,
            "occurred_at": occurred_at.isoformat(),
            "payload_digest": payload_digest,
            "previous_hash": previous_hash,
        }

        event_hash = _digest(material)

        record = BidAuditRecord(
            audit_id=_id("audit"),
            case_id=case.case_id,
            sequence=sequence,
            case_version=case.version,
            action=action,
            actor_id=actor_id,
            occurred_at=occurred_at,
            payload_digest=payload_digest,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )

        records.append(record)
        return record

    def _commit(
        self,
        case: BidCase,
        *,
        actor_id: str,
        action: str,
        payload: dict[str, Any],
    ) -> BidCase:
        now = _now()

        updated = replace(
            case,
            version=case.version + 1,
            updated_at=now,
        )

        self._cases[case.case_id] = updated

        self._append_audit(
            updated,
            action=action,
            actor_id=actor_id,
            payload=payload,
            occurred_at=now,
        )

        return updated

    @staticmethod
    def _check_expected(
        case: BidCase,
        expected_version: int | None,
    ) -> None:
        if (
            expected_version is not None
            and expected_version != case.version
        ):
            raise BidOptimisticLockError(
                "stale bid case version: "
                f"expected {expected_version}, "
                f"current {case.version}"
            )

    def _idempotency_replay(
        self,
        *,
        case_id: str,
        idempotency_key: str | None,
        fingerprint: str,
    ) -> BidCase | None:
        if not idempotency_key:
            return None

        key = (
            case_id,
            idempotency_key,
        )

        existing = self._idempotency.get(key)

        if existing is None:
            return None

        prior_fingerprint, result = existing

        if prior_fingerprint != fingerprint:
            raise BidIdempotencyConflict(
                "idempotency key reused "
                "with different command payload"
            )

        return result

    def _idempotency_store(
        self,
        *,
        case_id: str,
        idempotency_key: str | None,
        fingerprint: str,
        result: BidCase,
    ) -> None:
        if not idempotency_key:
            return

        self._idempotency[
            (
                case_id,
                idempotency_key,
            )
        ] = (
            fingerprint,
            result,
        )

    def create_case(
        self,
        *,
        package_id: str,
        actor_id: str,
        as_of: datetime | None = None,
    ) -> BidCase:
        package_id = _required(
            package_id,
            "package_id",
        )
        actor_id = _required(
            actor_id,
            "actor_id",
        )

        existing_id = self._case_by_package.get(
            package_id
        )

        if existing_id:
            return self._case(existing_id)

        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        package = self._package(package_id)
        manifest = self._manifest(
            package_id,
            as_of,
        )

        issues = self._manifest_issues(
            manifest
        )

        state = (
            BidCaseState.READY
            if bool(
                getattr(
                    manifest,
                    "ready_for_execution",
                    False,
                )
            )
            else BidCaseState.BLOCKED
        )

        now = _now()

        case = BidCase(
            case_id=_id("bcase"),
            package_id=package_id,
            tenant_id=str(
                getattr(
                    package,
                    "tenant_id",
                    "",
                )
            ),
            business_unit_id=str(
                getattr(
                    package,
                    "business_unit_id",
                    "",
                )
            ),
            opportunity_id=getattr(
                package,
                "opportunity_id",
                None,
            ),
            project_name=str(
                getattr(
                    package,
                    "project_name",
                    "",
                )
            ),
            city=str(
                getattr(
                    package,
                    "city",
                    "",
                )
            ),
            state=state,
            authority_revision_id=str(
                getattr(
                    manifest,
                    "revision_id",
                    "",
                )
            ),
            processed_revision_id=None,
            estimate_id=None,
            session_id=None,
            direct_cost_cents=0,
            bid_price_cents=0,
            due_at=getattr(
                manifest,
                "due_at",
                None,
            ),
            issues=issues,
            runs=(),
            approvals=(),
            submission=None,
            outcome=None,
            version=1,
            created_at=now,
            updated_at=now,
        )

        self._cases[
            case.case_id
        ] = case

        self._case_by_package[
            package_id
        ] = case.case_id

        self._append_audit(
            case,
            action="bid_case.created",
            actor_id=actor_id,
            payload={
                "package_id": package_id,
                "authority_revision_id":
                    case.authority_revision_id,
                "state": case.state.value,
            },
            occurred_at=now,
        )

        return case

    def sync_authority(
        self,
        *,
        case_id: str,
        actor_id: str,
        as_of: datetime | None = None,
        expected_version: int | None = None,
    ) -> BidCase:
        case = self._case(case_id)
        self._check_expected(
            case,
            expected_version,
        )

        if case.state in {
            BidCaseState.AWARDED,
            BidCaseState.LOST,
            BidCaseState.NO_BID,
        }:
            return case

        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        manifest = self._manifest(
            case.package_id,
            as_of,
        )

        revision_id = str(
            getattr(
                manifest,
                "revision_id",
                "",
            )
        )

        if (
            revision_id
            == case.authority_revision_id
        ):
            return case

        issues = list(
            self._manifest_issues(
                manifest
            )
        )

        if case.state == BidCaseState.SUBMITTED:
            issues.append(
                BidDecisionIssue(
                    code=(
                        "POST_SUBMISSION_REVISION"
                    ),
                    severity=(
                        DecisionSeverity.BLOCKER
                    ),
                    message=(
                        "Authoritative bid package "
                        "changed after submission."
                    ),
                    source="command_center",
                )
            )
            state = BidCaseState.BLOCKED

        elif not bool(
            getattr(
                manifest,
                "ready_for_execution",
                False,
            )
        ):
            state = BidCaseState.BLOCKED

        else:
            issues.append(
                BidDecisionIssue(
                    code=(
                        "PACKAGE_REVISION_PENDING"
                    ),
                    severity=(
                        DecisionSeverity.REVIEW
                    ),
                    message=(
                        "A newer authoritative "
                        "package revision requires "
                        "revision execution."
                    ),
                    source="command_center",
                )
            )
            state = BidCaseState.REVIEW

        updated = replace(
            case,
            authority_revision_id=revision_id,
            due_at=getattr(
                manifest,
                "due_at",
                None,
            ),
            issues=self._dedupe_issues(
                issues
            ),
            state=state,
        )

        return self._commit(
            updated,
            actor_id=actor_id,
            action="bid_case.authority_changed",
            payload={
                "old_revision":
                    case.authority_revision_id,
                "new_revision":
                    revision_id,
                "state":
                    state.value,
            },
        )

    def record_initial_result(
        self,
        *,
        case_id: str,
        actor_id: str,
        package_revision_id: str,
        result: Any,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
        as_of: datetime | None = None,
    ) -> BidCase:
        fingerprint = _digest(
            {
                "command":
                    "record_initial_result",
                "package_revision_id":
                    package_revision_id,
                "estimate_id":
                    getattr(
                        result,
                        "estimate_id",
                        None,
                    ),
                "session_id":
                    getattr(
                        result,
                        "session_id",
                        None,
                    ),
                "direct":
                    getattr(
                        result,
                        "direct_cost_cents",
                        None,
                    ),
                "bid":
                    getattr(
                        result,
                        "bid_price_cents",
                        None,
                    ),
                "proposal_ready":
                    getattr(
                        result,
                        "proposal_ready",
                        None,
                    ),
            }
        )

        replay = self._idempotency_replay(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )

        if replay is not None:
            return replay

        case = self._case(case_id)
        self._check_expected(
            case,
            expected_version,
        )

        if case.runs:
            raise BidCommandConflict(
                "initial result already exists"
            )

        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        manifest = self._manifest(
            case.package_id,
            as_of,
        )

        current_revision = str(
            getattr(
                manifest,
                "revision_id",
                "",
            )
        )

        if package_revision_id != current_revision:
            raise BidCommandConflict(
                "initial result references "
                "a stale package revision"
            )

        if not bool(
            getattr(
                manifest,
                "ready_for_execution",
                False,
            )
        ):
            raise BidCommandBlocked(
                "authoritative package is "
                "not ready for execution"
            )

        direct = _money(
            getattr(
                result,
                "direct_cost_cents",
                None,
            ),
            "direct_cost_cents",
        )

        bid = _money(
            getattr(
                result,
                "bid_price_cents",
                None,
            ),
            "bid_price_cents",
        )

        estimate_id = _required(
            getattr(
                result,
                "estimate_id",
                None,
            ),
            "estimate_id",
        )

        session_id_raw = getattr(
            result,
            "session_id",
            None,
        )

        session_id = (
            str(session_id_raw)
            if session_id_raw
            else None
        )

        proposal_ready = bool(
            getattr(
                result,
                "proposal_ready",
                False,
            )
        )

        issues = list(
            self._manifest_issues(
                manifest
            )
        )

        issues.extend(
            self._external_issues(
                getattr(
                    result,
                    "review_queue",
                    (),
                ),
                source="plan_to_bid",
            )
        )

        if (
            proposal_ready
            and bid <= 0
        ):
            issues.append(
                BidDecisionIssue(
                    code="ZERO_BID_PRICE",
                    severity=(
                        DecisionSeverity.BLOCKER
                    ),
                    message=(
                        "Proposal cannot be ready "
                        "with a zero bid price."
                    ),
                    source="command_center",
                )
            )

        if (
            bid > 0
            and bid < direct
        ):
            issues.append(
                BidDecisionIssue(
                    code=(
                        "BID_BELOW_DIRECT_COST"
                    ),
                    severity=(
                        DecisionSeverity.REVIEW
                    ),
                    message=(
                        "Bid price is below "
                        "direct estimated cost."
                    ),
                    source="command_center",
                )
            )

        if (
            not proposal_ready
            and not issues
        ):
            issues.append(
                BidDecisionIssue(
                    code=(
                        "INITIAL_EXECUTION_NOT_READY"
                    ),
                    severity=(
                        DecisionSeverity.BLOCKER
                    ),
                    message=(
                        "Initial plan-to-bid "
                        "execution is not ready."
                    ),
                    source="plan_to_bid",
                )
            )

        issues_tuple = self._dedupe_issues(
            issues
        )

        state = self._state_from_execution(
            issues_tuple,
            proposal_ready=proposal_ready,
        )

        run = BidRunRecord(
            run_id=_id("brun"),
            run_type=BidRunType.INITIAL,
            package_revision_id=(
                package_revision_id
            ),
            estimate_id=estimate_id,
            session_id=session_id,
            direct_cost_cents=direct,
            bid_price_cents=bid,
            direct_cost_delta_cents=direct,
            bid_price_delta_cents=bid,
            proposal_ready=proposal_ready,
            issues=issues_tuple,
            recorded_at=_now(),
            recorded_by=actor_id,
        )

        updated = replace(
            case,
            authority_revision_id=(
                current_revision
            ),
            processed_revision_id=(
                package_revision_id
            ),
            estimate_id=estimate_id,
            session_id=session_id,
            direct_cost_cents=direct,
            bid_price_cents=bid,
            due_at=getattr(
                manifest,
                "due_at",
                None,
            ),
            issues=issues_tuple,
            runs=case.runs + (run,),
            state=state,
        )

        committed = self._commit(
            updated,
            actor_id=actor_id,
            action="bid_case.initial_result_recorded",
            payload={
                "run_id":
                    run.run_id,
                "package_revision_id":
                    package_revision_id,
                "estimate_id":
                    estimate_id,
                "direct_cost_cents":
                    direct,
                "bid_price_cents":
                    bid,
                "proposal_ready":
                    proposal_ready,
                "state":
                    state.value,
            },
        )

        self._idempotency_store(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            result=committed,
        )

        return committed

    def record_revision_result(
        self,
        *,
        case_id: str,
        actor_id: str,
        package_revision_id: str,
        result: Any,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
        as_of: datetime | None = None,
    ) -> BidCase:
        packet = getattr(
            result,
            "approval_packet",
            None,
        )

        if packet is None:
            raise ValueError(
                "revision result has no approval_packet"
            )

        financial = getattr(
            packet,
            "financial_delta",
            None,
        )

        if financial is None:
            raise ValueError(
                "approval packet has no financial_delta"
            )

        fingerprint = _digest(
            {
                "command":
                    "record_revision_result",
                "revision":
                    package_revision_id,
                "estimate_id":
                    getattr(
                        packet,
                        "estimate_id",
                        None,
                    ),
                "direct_delta":
                    getattr(
                        financial,
                        "direct_cost_delta_cents",
                        None,
                    ),
                "bid_delta":
                    getattr(
                        financial,
                        "bid_price_delta_cents",
                        None,
                    ),
                "ready":
                    getattr(
                        packet,
                        "ready_for_revised_proposal",
                        None,
                    ),
            }
        )

        replay = self._idempotency_replay(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )

        if replay is not None:
            return replay

        case = self._case(case_id)
        self._check_expected(
            case,
            expected_version,
        )

        if not case.runs:
            raise BidCommandConflict(
                "cannot record revision "
                "before initial execution"
            )

        if case.state in {
            BidCaseState.AWARDED,
            BidCaseState.LOST,
            BidCaseState.NO_BID,
        }:
            raise BidCommandBlocked(
                "terminal bid case cannot "
                "receive revision execution"
            )

        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        manifest = self._manifest(
            case.package_id,
            as_of,
        )

        current_revision = str(
            getattr(
                manifest,
                "revision_id",
                "",
            )
        )

        if package_revision_id != current_revision:
            raise BidCommandConflict(
                "revision result is stale"
            )

        if (
            package_revision_id
            == case.processed_revision_id
        ):
            raise BidCommandConflict(
                "current package revision "
                "has already been processed"
            )

        estimate_id = _required(
            getattr(
                packet,
                "estimate_id",
                None,
            ),
            "estimate_id",
        )

        if (
            case.estimate_id is not None
            and estimate_id
            != case.estimate_id
        ):
            raise BidCommandConflict(
                "estimate identity changed "
                "during package revision"
            )

        direct_delta = int(
            getattr(
                financial,
                "direct_cost_delta_cents",
                0,
            )
        )

        bid_delta = int(
            getattr(
                financial,
                "bid_price_delta_cents",
                0,
            )
        )

        new_direct = (
            case.direct_cost_cents
            + direct_delta
        )

        new_bid = (
            case.bid_price_cents
            + bid_delta
        )

        if new_direct < 0:
            raise BidCommandConflict(
                "revision produces negative "
                "total direct cost"
            )

        if new_bid < 0:
            raise BidCommandConflict(
                "revision produces negative "
                "total bid price"
            )

        proposal_ready = bool(
            getattr(
                packet,
                "ready_for_revised_proposal",
                False,
            )
        )

        issues = list(
            self._manifest_issues(
                manifest
            )
        )

        issues.extend(
            self._external_issues(
                getattr(
                    packet,
                    "approval_items",
                    (),
                ),
                source="revision_execution",
            )
        )

        if (
            new_bid > 0
            and new_bid < new_direct
        ):
            issues.append(
                BidDecisionIssue(
                    code=(
                        "REVISED_BID_BELOW_DIRECT_COST"
                    ),
                    severity=(
                        DecisionSeverity.REVIEW
                    ),
                    message=(
                        "Revised bid price is below "
                        "revised direct cost."
                    ),
                    source="command_center",
                )
            )

        if (
            not proposal_ready
            and not issues
        ):
            issues.append(
                BidDecisionIssue(
                    code=(
                        "REVISION_EXECUTION_NOT_READY"
                    ),
                    severity=(
                        DecisionSeverity.BLOCKER
                    ),
                    message=(
                        "Revision execution did not "
                        "produce a proposal-ready result."
                    ),
                    source="revision_execution",
                )
            )

        issues_tuple = self._dedupe_issues(
            issues
        )

        state = self._state_from_execution(
            issues_tuple,
            proposal_ready=proposal_ready,
        )

        run = BidRunRecord(
            run_id=_id("brun"),
            run_type=BidRunType.REVISION,
            package_revision_id=(
                package_revision_id
            ),
            estimate_id=estimate_id,
            session_id=case.session_id,
            direct_cost_cents=new_direct,
            bid_price_cents=new_bid,
            direct_cost_delta_cents=(
                direct_delta
            ),
            bid_price_delta_cents=(
                bid_delta
            ),
            proposal_ready=proposal_ready,
            issues=issues_tuple,
            recorded_at=_now(),
            recorded_by=actor_id,
        )

        updated = replace(
            case,
            authority_revision_id=(
                current_revision
            ),
            processed_revision_id=(
                package_revision_id
            ),
            direct_cost_cents=(
                new_direct
            ),
            bid_price_cents=new_bid,
            due_at=getattr(
                manifest,
                "due_at",
                None,
            ),
            issues=issues_tuple,
            runs=case.runs + (run,),
            state=state,
            submission=None,
        )

        committed = self._commit(
            updated,
            actor_id=actor_id,
            action="bid_case.revision_result_recorded",
            payload={
                "run_id":
                    run.run_id,
                "package_revision_id":
                    package_revision_id,
                "direct_delta":
                    direct_delta,
                "bid_delta":
                    bid_delta,
                "new_direct":
                    new_direct,
                "new_bid":
                    new_bid,
                "proposal_ready":
                    proposal_ready,
                "state":
                    state.value,
            },
        )

        self._idempotency_store(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            result=committed,
        )

        return committed

    def resolve_issue(
        self,
        *,
        case_id: str,
        actor_id: str,
        code: str,
        note: str,
        expected_version: int | None = None,
        allow_blocker_override: bool = False,
        actor_role: str | None = None,
    ) -> BidCase:
        case = self._case(case_id)
        self._check_expected(
            case,
            expected_version,
        )

        if case.state in {
            BidCaseState.SUBMITTED,
            BidCaseState.AWARDED,
            BidCaseState.LOST,
            BidCaseState.NO_BID,
        }:
            raise BidCommandBlocked(
                "cannot resolve issues "
                "after bid closure/submission"
            )

        code = _required(
            code,
            "code",
        )

        note = _required(
            note,
            "note",
        )

        matched = tuple(
            issue
            for issue in case.issues
            if issue.code == code
        )

        if not matched:
            raise KeyError(
                f"issue not found: {code}"
            )

        if any(
            issue.severity
            == DecisionSeverity.BLOCKER
            for issue in matched
        ):
            if not allow_blocker_override:
                raise BidCommandBlocked(
                    "blocker requires underlying "
                    "condition to be corrected "
                    "or explicit privileged override"
                )

            role = (
                str(actor_role or "")
                .strip()
                .lower()
            )

            if role not in self.approval_roles:
                raise BidCommandBlocked(
                    "actor role cannot override blocker"
                )

        remaining = tuple(
            issue
            for issue in case.issues
            if issue.code != code
        )

        if case.runs:
            state = self._state_from_execution(
                remaining,
                proposal_ready=(
                    case.runs[-1]
                    .proposal_ready
                ),
            )
        else:
            state = (
                BidCaseState.READY
                if not any(
                    item.severity
                    == DecisionSeverity.BLOCKER
                    for item in remaining
                )
                else BidCaseState.BLOCKED
            )

        updated = replace(
            case,
            issues=remaining,
            state=state,
        )

        return self._commit(
            updated,
            actor_id=actor_id,
            action="bid_case.issue_resolved",
            payload={
                "code": code,
                "note": note,
                "blocker_override":
                    bool(
                        allow_blocker_override
                    ),
                "new_state":
                    state.value,
            },
        )

    def approve(
        self,
        *,
        case_id: str,
        actor_id: str,
        actor_role: str,
        note: str,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
        as_of: datetime | None = None,
    ) -> BidCase:
        role = (
            _required(
                actor_role,
                "actor_role",
            )
            .lower()
        )

        fingerprint = _digest(
            {
                "command": "approve",
                "actor_id": actor_id,
                "role": role,
                "note": note,
            }
        )

        replay = self._idempotency_replay(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )

        if replay is not None:
            return replay

        case = self._case(case_id)
        self._check_expected(
            case,
            expected_version,
        )

        if role not in self.approval_roles:
            raise BidCommandBlocked(
                "actor role cannot approve bids"
            )

        if case.state not in {
            BidCaseState.APPROVAL_READY,
            BidCaseState.APPROVED,
        }:
            raise BidCommandBlocked(
                "bid is not approval-ready"
            )

        if case.processed_revision_id is None:
            raise BidCommandBlocked(
                "no processed package revision"
            )

        if not case.runs[-1].proposal_ready:
            raise BidCommandBlocked(
                "latest execution is not proposal-ready"
            )

        if any(
            item.severity
            in {
                DecisionSeverity.REVIEW,
                DecisionSeverity.BLOCKER,
            }
            for item in case.issues
        ):
            raise BidCommandBlocked(
                "unresolved decision issues remain"
            )

        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        manifest = self._manifest(
            case.package_id,
            as_of,
        )

        current_revision = str(
            getattr(
                manifest,
                "revision_id",
                "",
            )
        )

        if (
            current_revision
            != case.processed_revision_id
        ):
            raise BidCommandBlocked(
                "package changed after execution"
            )

        current_actors = (
            self._current_approval_actors(
                case
            )
        )

        if actor_id in current_actors:
            return case

        approval = BidApproval(
            approval_id=_id("bapr"),
            package_revision_id=(
                case.processed_revision_id
            ),
            bid_price_cents=(
                case.bid_price_cents
            ),
            actor_id=actor_id,
            actor_role=role,
            note=_required(
                note,
                "note",
            ),
            approved_at=_now(),
        )

        approvals = (
            case.approvals
            + (
                approval,
            )
        )

        actors_after = (
            current_actors
            | {
                actor_id,
            }
        )

        quorum = (
            self._approval_quorum_for(
                case
            )
        )

        state = (
            BidCaseState.APPROVED
            if len(
                actors_after
            )
            >= quorum
            else BidCaseState
            .APPROVAL_READY
        )

        updated = replace(
            case,
            approvals=approvals,
            state=state,
        )

        committed = self._commit(
            updated,
            actor_id=actor_id,
            action="bid_case.approved",
            payload={
                "approval_id":
                    approval.approval_id,
                "actor_role":
                    role,
                "quorum_required":
                    quorum,
                "quorum_after":
                    len(
                        actors_after
                    ),
                "bid_price_cents":
                    case.bid_price_cents,
                "state":
                    state.value,
            },
        )

        self._idempotency_store(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            result=committed,
        )

        return committed

    def submit(
        self,
        *,
        case_id: str,
        actor_id: str,
        note: str,
        external_reference: str | None = None,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
        as_of: datetime | None = None,
    ) -> BidCase:
        fingerprint = _digest(
            {
                "command": "submit",
                "note": note,
                "external_reference":
                    external_reference,
            }
        )

        replay = self._idempotency_replay(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )

        if replay is not None:
            return replay

        case = self._case(case_id)
        self._check_expected(
            case,
            expected_version,
        )

        if case.state != BidCaseState.APPROVED:
            raise BidCommandBlocked(
                "bid must be fully approved "
                "before submission"
            )

        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        manifest = self._manifest(
            case.package_id,
            as_of,
        )

        if not bool(
            getattr(
                manifest,
                "ready_for_execution",
                False,
            )
        ):
            raise BidCommandBlocked(
                "authoritative package is "
                "no longer submission-ready"
            )

        revision_id = str(
            getattr(
                manifest,
                "revision_id",
                "",
            )
        )

        if (
            revision_id
            != case.processed_revision_id
        ):
            raise BidCommandBlocked(
                "package revision changed "
                "after pricing/approval"
            )

        risk = self.deadline_risk(
            getattr(
                manifest,
                "due_at",
                None,
            ),
            as_of=as_of,
        )

        if risk in {
            DeadlineRisk.EXPIRED,
            DeadlineRisk.UNKNOWN,
        }:
            raise BidCommandBlocked(
                "valid future bid deadline required"
            )

        if (
            len(
                self._current_approval_actors(
                    case
                )
            )
            < self._approval_quorum_for(
                case
            )
        ):
            raise BidCommandBlocked(
                "approval quorum is incomplete"
            )

        submission = BidSubmission(
            submission_id=_id("bsub"),
            package_revision_id=(
                revision_id
            ),
            estimate_id=_required(
                case.estimate_id,
                "estimate_id",
            ),
            bid_price_cents=(
                case.bid_price_cents
            ),
            external_reference=(
                external_reference
            ),
            note=_required(
                note,
                "note",
            ),
            submitted_at=as_of,
            submitted_by=actor_id,
        )

        updated = replace(
            case,
            submission=submission,
            state=BidCaseState.SUBMITTED,
            due_at=getattr(
                manifest,
                "due_at",
                None,
            ),
        )

        committed = self._commit(
            updated,
            actor_id=actor_id,
            action="bid_case.submitted",
            payload={
                "submission_id":
                    submission.submission_id,
                "revision_id":
                    revision_id,
                "estimate_id":
                    submission.estimate_id,
                "bid_price_cents":
                    submission.bid_price_cents,
                "external_reference":
                    external_reference or "",
            },
        )

        self._idempotency_store(
            case_id=case_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            result=committed,
        )

        return committed

    def record_outcome(
        self,
        *,
        case_id: str,
        actor_id: str,
        outcome: OutcomeType,
        reason: str,
        external_reference: str | None = None,
        expected_version: int | None = None,
    ) -> BidCase:
        case = self._case(case_id)
        self._check_expected(
            case,
            expected_version,
        )

        if case.outcome is not None:
            raise BidCommandConflict(
                "bid outcome already recorded"
            )

        if outcome in {
            OutcomeType.AWARDED,
            OutcomeType.LOST,
        }:
            if case.state != BidCaseState.SUBMITTED:
                raise BidCommandBlocked(
                    "award/loss requires "
                    "submitted bid"
                )

        elif outcome == OutcomeType.NO_BID:
            if case.state in {
                BidCaseState.SUBMITTED,
                BidCaseState.AWARDED,
                BidCaseState.LOST,
            }:
                raise BidCommandBlocked(
                    "submitted/closed bid "
                    "cannot become no-bid"
                )

        state_map = {
            OutcomeType.AWARDED:
                BidCaseState.AWARDED,
            OutcomeType.LOST:
                BidCaseState.LOST,
            OutcomeType.NO_BID:
                BidCaseState.NO_BID,
        }

        record = BidOutcome(
            outcome_id=_id("bout"),
            outcome=outcome,
            reason=_required(
                reason,
                "reason",
            ),
            external_reference=(
                external_reference
            ),
            recorded_at=_now(),
            recorded_by=actor_id,
        )

        updated = replace(
            case,
            outcome=record,
            state=state_map[outcome],
        )

        return self._commit(
            updated,
            actor_id=actor_id,
            action="bid_case.outcome_recorded",
            payload={
                "outcome_id":
                    record.outcome_id,
                "outcome":
                    outcome.value,
                "reason":
                    reason,
                "external_reference":
                    external_reference or "",
            },
        )

    def audit_records(
        self,
        case_id: str,
    ) -> tuple[BidAuditRecord, ...]:
        self._case(case_id)
        return tuple(
            self._audits.get(
                case_id,
                (),
            )
        )

    def verify_audit_chain(
        self,
        case_id: str,
    ) -> bool:
        records = self.audit_records(
            case_id
        )

        previous = "GENESIS"

        for expected_sequence, record in enumerate(
            records,
            1,
        ):
            if (
                record.sequence
                != expected_sequence
            ):
                raise BidAuditIntegrityError(
                    "audit sequence mismatch"
                )

            if (
                record.previous_hash
                != previous
            ):
                raise BidAuditIntegrityError(
                    "audit previous hash mismatch"
                )

            material = {
                "case_id":
                    record.case_id,
                "sequence":
                    record.sequence,
                "case_version":
                    record.case_version,
                "action":
                    record.action,
                "actor_id":
                    record.actor_id,
                "occurred_at":
                    record
                    .occurred_at
                    .isoformat(),
                "payload_digest":
                    record
                    .payload_digest,
                "previous_hash":
                    record
                    .previous_hash,
            }

            expected_hash = _digest(
                material
            )

            if (
                record.event_hash
                != expected_hash
            ):
                raise BidAuditIntegrityError(
                    "audit event hash mismatch"
                )

            previous = (
                record.event_hash
            )

        return True

    def snapshot(
        self,
        case_id: str,
        *,
        as_of: datetime | None = None,
    ) -> BidCommandSnapshot:
        case = self._case(case_id)

        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        if case.due_at is None:
            due_in_seconds = None
        else:
            due_in_seconds = int(
                (
                    case.due_at
                    - as_of
                )
                .total_seconds()
            )

        risk = self.deadline_risk(
            case.due_at,
            as_of=as_of,
        )

        reviews, blockers = (
            self._issue_counts(
                case.issues
            )
        )

        gross_profit = (
            case.bid_price_cents
            - case.direct_cost_cents
        )

        margin_bps = (
            round(
                gross_profit
                * 10_000
                / case.bid_price_cents
            )
            if case.bid_price_cents
            > 0
            else None
        )

        approval_count = len(
            self._current_approval_actors(
                case
            )
        )

        approval_quorum = (
            self._approval_quorum_for(
                case
            )
        )

        ready_to_submit = (
            case.state
            == BidCaseState.APPROVED
            and blockers == 0
            and reviews == 0
            and approval_count
            >= approval_quorum
            and risk
            not in {
                DeadlineRisk.EXPIRED,
                DeadlineRisk.UNKNOWN,
            }
        )

        next_action_map = {
            BidCaseState.INTAKE:
                "complete_package_intake",
            BidCaseState.READY:
                (
                    "execute_initial_bid"
                    if not case.runs
                    else "execute_revision"
                ),
            BidCaseState.EXECUTING:
                "await_execution",
            BidCaseState.REVIEW:
                "resolve_review_or_rerun",
            BidCaseState.BLOCKED:
                "resolve_blockers",
            BidCaseState.APPROVAL_READY:
                "collect_approval",
            BidCaseState.APPROVED:
                "submit_bid",
            BidCaseState.SUBMITTED:
                "await_award_decision",
            BidCaseState.AWARDED:
                "handoff_to_operations",
            BidCaseState.LOST:
                "capture_loss_intelligence",
            BidCaseState.NO_BID:
                "closed_no_bid",
        }

        return BidCommandSnapshot(
            case_id=case.case_id,
            package_id=case.package_id,
            project_name=case.project_name,
            opportunity_id=(
                case.opportunity_id
            ),
            state=case.state,
            authority_revision_id=(
                case
                .authority_revision_id
            ),
            processed_revision_id=(
                case
                .processed_revision_id
            ),
            estimate_id=case.estimate_id,
            session_id=case.session_id,
            direct_cost_cents=(
                case
                .direct_cost_cents
            ),
            bid_price_cents=(
                case
                .bid_price_cents
            ),
            gross_profit_cents=(
                gross_profit
            ),
            gross_margin_bps=(
                margin_bps
            ),
            due_at=case.due_at,
            due_in_seconds=(
                due_in_seconds
            ),
            deadline_risk=risk,
            unresolved_reviews=reviews,
            blockers=blockers,
            approval_count=(
                approval_count
            ),
            approval_quorum=(
                approval_quorum
            ),
            run_count=len(case.runs),
            ready_to_submit=(
                ready_to_submit
            ),
            next_action=(
                next_action_map[
                    case.state
                ]
            ),
            version=case.version,
        )

    def portfolio(
        self,
        *,
        as_of: datetime | None = None,
    ) -> tuple[BidCommandSnapshot, ...]:
        as_of = (
            _aware(as_of, "as_of")
            if as_of is not None
            else _now()
        )

        snapshots = [
            self.snapshot(
                case_id,
                as_of=as_of,
            )
            for case_id
            in self._cases
        ]

        return tuple(
            sorted(
                snapshots,
                key=lambda item: (
                    item.due_at is None,
                    item.due_at
                    or datetime.max.replace(
                        tzinfo=timezone.utc
                    ),
                    item.project_name,
                    item.case_id,
                ),
            )
        )
