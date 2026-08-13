from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class WorkSource(str, Enum):
    GOAT = "goat"
    CRM = "crm"
    COMPANY_EMAIL = "company_email"
    COMPANY_PHONE = "company_phone"
    COMPANY_CALENDAR = "company_calendar"
    PROJECT = "project"
    ESTIMATING = "estimating"
    ACCOUNTING = "accounting"
    COMPANY_DRIVE = "company_drive"
    SECURITY = "security"


class WorkEventType(str, Enum):
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    CALL = "call"
    SMS = "sms"
    DECISION = "decision"
    APPROVAL = "approval"
    REJECTION = "rejection"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    HANDOFF = "handoff"
    ESTIMATE = "estimate"
    BID = "bid"
    RFI = "rfi"
    CHANGE_ORDER = "change_order"
    PROJECT_UPDATE = "project_update"
    CUSTOMER_UPDATE = "customer_update"
    VENDOR_UPDATE = "vendor_update"
    FINANCIAL_ACTION = "financial_action"
    SOP_UPDATE = "sop_update"


BLOCKED_SOURCES = frozenset({
    "personal_email",
    "private_message",
    "personal_phone",
    "microphone_surveillance",
    "webcam_surveillance",
    "keystroke_logging",
    "private_location_tracking",
})


@dataclass(frozen=True)
class MonitoringContext:
    legitimate_business_purpose: str
    workforce_notice_acknowledged: bool
    company_managed_source: bool

    def validate(self) -> None:
        if not self.legitimate_business_purpose.strip():
            raise PermissionError("business purpose required")

        if not self.workforce_notice_acknowledged:
            raise PermissionError(
                "workforce monitoring notice not acknowledged"
            )

        if not self.company_managed_source:
            raise PermissionError(
                "only approved company-managed sources may be captured"
            )


@dataclass(frozen=True)
class WorkEvent:
    actor_id: str
    tenant_id: str
    business_unit: str
    event_type: WorkEventType
    source: WorkSource
    summary: str
    timestamp: str
    project_id: str | None = None
    opportunity_id: str | None = None
    contact_id: str | None = None
    artifact_ref: str | None = None
    decision_rationale: str | None = None
    classification: str = "internal"
    previous_hash: str = ""
    event_hash: str = ""


class OrganizationalActivityLedger:
    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._events: list[WorkEvent] = []

    @staticmethod
    def _hash(payload: dict) -> str:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def record(
        self,
        *,
        context: MonitoringContext,
        actor_id: str,
        tenant_id: str,
        business_unit: str,
        event_type: WorkEventType,
        source: WorkSource,
        summary: str,
        project_id: str | None = None,
        opportunity_id: str | None = None,
        contact_id: str | None = None,
        artifact_ref: str | None = None,
        decision_rationale: str | None = None,
        classification: str = "internal",
    ) -> WorkEvent:

        context.validate()

        if source.value in BLOCKED_SOURCES:
            raise PermissionError("private surveillance source prohibited")

        if not actor_id.strip():
            raise ValueError("actor_id required")

        if not summary.strip():
            raise ValueError("work summary required")

        previous_hash = (
            self._events[-1].event_hash
            if self._events
            else self.GENESIS
        )

        timestamp = datetime.now(timezone.utc).isoformat()

        payload = {
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "business_unit": business_unit,
            "event_type": event_type.value,
            "source": source.value,
            "summary": summary,
            "timestamp": timestamp,
            "project_id": project_id,
            "opportunity_id": opportunity_id,
            "contact_id": contact_id,
            "artifact_ref": artifact_ref,
            "decision_rationale": decision_rationale,
            "classification": classification,
            "previous_hash": previous_hash,
        }

        event = WorkEvent(
            **{
                **payload,
                "event_type": event_type,
                "source": source,
            },
            event_hash=self._hash(payload),
        )

        self._events.append(event)
        return event

    def events_for_actor(
        self,
        actor_id: str,
    ) -> tuple[WorkEvent, ...]:
        return tuple(
            event
            for event in self._events
            if event.actor_id == actor_id
        )

    def verify(self) -> bool:
        previous = self.GENESIS

        for event in self._events:
            if event.previous_hash != previous:
                return False

            payload = {
                "actor_id": event.actor_id,
                "tenant_id": event.tenant_id,
                "business_unit": event.business_unit,
                "event_type": event.event_type.value,
                "source": event.source.value,
                "summary": event.summary,
                "timestamp": event.timestamp,
                "project_id": event.project_id,
                "opportunity_id": event.opportunity_id,
                "contact_id": event.contact_id,
                "artifact_ref": event.artifact_ref,
                "decision_rationale": event.decision_rationale,
                "classification": event.classification,
                "previous_hash": event.previous_hash,
            }

            if self._hash(payload) != event.event_hash:
                return False

            previous = event.event_hash

        return True


@dataclass(frozen=True)
class RoleContinuityProfile:
    actor_id: str
    event_count: int
    common_event_types: tuple[tuple[str, int], ...]
    common_sources: tuple[tuple[str, int], ...]
    project_ids: tuple[str, ...]
    opportunity_ids: tuple[str, ...]
    recurring_decision_patterns: tuple[str, ...]
    artifact_refs: tuple[str, ...]


class WorkPatternLearner:
    """
    Learns business-process patterns, not private personality traits.
    """

    @staticmethod
    def build_profile(
        actor_id: str,
        events: tuple[WorkEvent, ...],
    ) -> RoleContinuityProfile:

        actor_events = [
            event
            for event in events
            if event.actor_id == actor_id
        ]

        event_counts = Counter(
            event.event_type.value
            for event in actor_events
        )

        source_counts = Counter(
            event.source.value
            for event in actor_events
        )

        projects = sorted({
            event.project_id
            for event in actor_events
            if event.project_id
        })

        opportunities = sorted({
            event.opportunity_id
            for event in actor_events
            if event.opportunity_id
        })

        rationales = Counter(
            event.decision_rationale.strip()
            for event in actor_events
            if event.decision_rationale
            and event.decision_rationale.strip()
        )

        artifacts = sorted({
            event.artifact_ref
            for event in actor_events
            if event.artifact_ref
        })

        return RoleContinuityProfile(
            actor_id=actor_id,
            event_count=len(actor_events),
            common_event_types=tuple(
                event_counts.most_common(10)
            ),
            common_sources=tuple(
                source_counts.most_common(10)
            ),
            project_ids=tuple(projects),
            opportunity_ids=tuple(opportunities),
            recurring_decision_patterns=tuple(
                rationale
                for rationale, _ in rationales.most_common(20)
            ),
            artifact_refs=tuple(artifacts),
        )


@dataclass(frozen=True)
class ContinuitySnapshot:
    actor_id: str
    open_projects: tuple[str, ...]
    open_opportunities: tuple[str, ...]
    known_artifacts: tuple[str, ...]
    recurring_decisions: tuple[str, ...]
    created_at: str


class BusinessContinuityEngine:

    @staticmethod
    def snapshot(
        profile: RoleContinuityProfile,
    ) -> ContinuitySnapshot:

        return ContinuitySnapshot(
            actor_id=profile.actor_id,
            open_projects=profile.project_ids,
            open_opportunities=profile.opportunity_ids,
            known_artifacts=profile.artifact_refs,
            recurring_decisions=profile.recurring_decision_patterns,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )
