from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.data_spine.models import (
    Lead,
    Opportunity,
    TERMINAL_OPPORTUNITY_STAGES,
)
from leadbot_v2.goat.data_spine.store import InMemoryDataSpine


class WorkStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EscalationLevel(str, Enum):
    NONE = "none"
    OWNER = "owner"
    MANAGER = "manager"
    EXECUTIVE = "executive"


@dataclass(frozen=True)
class Commitment:
    commitment_id: str
    tenant_id: str
    entity_type: str
    entity_id: str
    owner_user_id: str
    description: str
    due_at: datetime
    created_at: datetime
    status: WorkStatus = WorkStatus.OPEN
    escalation: EscalationLevel = EscalationLevel.NONE
    completed_at: datetime | None = None
    completion_evidence: str | None = None


@dataclass(frozen=True)
class FollowThroughFinding:
    entity_type: str
    entity_id: str
    reason: str
    severity: str


class FollowThroughEngine:
    """
    Prevents leads, bids and commitments from silently falling through.

    Prototype stores commitments in memory.
    Production will persist them through the GOAT Data Spine.
    """

    def __init__(
        self,
        *,
        spine: InMemoryDataSpine,
        stale_after: timedelta = timedelta(days=3),
        manager_escalation_after: timedelta = timedelta(hours=24),
        executive_escalation_after: timedelta = timedelta(hours=72),
    ) -> None:
        self.spine = spine
        self.stale_after = stale_after
        self.manager_escalation_after = manager_escalation_after
        self.executive_escalation_after = executive_escalation_after
        self._commitments: dict[str, Commitment] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def create_commitment(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        owner_user_id: str,
        description: str,
        due_at: datetime,
    ) -> Commitment:
        if not description.strip():
            raise ValueError("commitment description required")

        if due_at.tzinfo is None:
            raise ValueError("due_at must be timezone-aware")

        commitment = Commitment(
            commitment_id=f"commit_{uuid4().hex}",
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            owner_user_id=owner_user_id,
            description=description.strip(),
            due_at=due_at,
            created_at=self._now(),
        )

        self._commitments[commitment.commitment_id] = commitment

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type=entity_type,
            aggregate_id=entity_id,
            event_type="workflow.commitment.created",
            actor_id=owner_user_id,
            payload={
                "commitment_id": commitment.commitment_id,
                "description": commitment.description,
                "due_at": due_at.isoformat(),
            },
        )

        return commitment

    def complete_commitment(
        self,
        *,
        commitment_id: str,
        actor_id: str,
        evidence: str,
    ) -> Commitment:
        if not evidence.strip():
            raise ValueError(
                "completion evidence required"
            )

        commitment = self._commitments[commitment_id]

        if commitment.status != WorkStatus.OPEN:
            raise RuntimeError(
                "only open commitments can be completed"
            )

        completed = replace(
            commitment,
            status=WorkStatus.COMPLETED,
            completed_at=self._now(),
            completion_evidence=evidence.strip(),
        )

        self._commitments[commitment_id] = completed

        self.spine.append_event(
            tenant_id=completed.tenant_id,
            aggregate_type=completed.entity_type,
            aggregate_id=completed.entity_id,
            event_type="workflow.commitment.completed",
            actor_id=actor_id,
            payload={
                "commitment_id": completed.commitment_id,
                "evidence": evidence.strip(),
            },
        )

        return completed

    def escalation_for(
        self,
        commitment: Commitment,
        *,
        now: datetime,
    ) -> EscalationLevel:
        if commitment.status != WorkStatus.OPEN:
            return EscalationLevel.NONE

        overdue = now - commitment.due_at

        if overdue <= timedelta(0):
            return EscalationLevel.NONE

        if overdue >= self.executive_escalation_after:
            return EscalationLevel.EXECUTIVE

        if overdue >= self.manager_escalation_after:
            return EscalationLevel.MANAGER

        return EscalationLevel.OWNER

    def refresh_escalations(
        self,
        *,
        tenant_id: str,
        now: datetime,
    ) -> tuple[Commitment, ...]:
        changed: list[Commitment] = []

        for commitment_id, commitment in list(
            self._commitments.items()
        ):
            if commitment.tenant_id != tenant_id:
                continue

            new_level = self.escalation_for(
                commitment,
                now=now,
            )

            if new_level == commitment.escalation:
                continue

            updated = replace(
                commitment,
                escalation=new_level,
            )

            self._commitments[commitment_id] = updated
            changed.append(updated)

            self.spine.append_event(
                tenant_id=tenant_id,
                aggregate_type=updated.entity_type,
                aggregate_id=updated.entity_id,
                event_type="workflow.commitment.escalated",
                actor_id="goat-follow-through",
                payload={
                    "commitment_id": commitment_id,
                    "escalation": new_level.value,
                },
            )

        return tuple(changed)

    def open_commitments(
        self,
        *,
        tenant_id: str,
    ) -> tuple[Commitment, ...]:
        return tuple(
            commitment
            for commitment in self._commitments.values()
            if (
                commitment.tenant_id == tenant_id
                and commitment.status == WorkStatus.OPEN
            )
        )

    def audit_active_crm(
        self,
        *,
        tenant_id: str,
        now: datetime,
    ) -> tuple[FollowThroughFinding, ...]:
        findings: list[FollowThroughFinding] = []

        for lead in self.spine.list_type(
            tenant_id=tenant_id,
            entity_type=Lead,
        ):
            if not lead.next_action or not lead.next_action_due_at:
                findings.append(
                    FollowThroughFinding(
                        entity_type="Lead",
                        entity_id=lead.entity_id,
                        reason="active lead has no next action",
                        severity="high",
                    )
                )
                continue

            if now > lead.next_action_due_at + self.stale_after:
                findings.append(
                    FollowThroughFinding(
                        entity_type="Lead",
                        entity_id=lead.entity_id,
                        reason="lead next action is stale",
                        severity="high",
                    )
                )

        for opportunity in self.spine.list_type(
            tenant_id=tenant_id,
            entity_type=Opportunity,
        ):
            if opportunity.stage in TERMINAL_OPPORTUNITY_STAGES:
                continue

            if (
                not opportunity.next_action
                or not opportunity.next_action_due_at
            ):
                findings.append(
                    FollowThroughFinding(
                        entity_type="Opportunity",
                        entity_id=opportunity.entity_id,
                        reason=(
                            "active opportunity has no next action"
                        ),
                        severity="critical",
                    )
                )
                continue

            if (
                opportunity.bid_due_at is not None
                and now > opportunity.bid_due_at
                and opportunity.stage.value not in {
                    "submitted",
                    "won",
                    "lost",
                    "no_bid",
                }
            ):
                findings.append(
                    FollowThroughFinding(
                        entity_type="Opportunity",
                        entity_id=opportunity.entity_id,
                        reason="bid due date passed without submission",
                        severity="critical",
                    )
                )

        return tuple(findings)
