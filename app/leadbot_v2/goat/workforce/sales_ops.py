from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from statistics import mean
from zoneinfo import ZoneInfo
from uuid import uuid4

from leadbot_v2.goat.access_control import (
    EXECUTIVE_ROLES,
    Principal,
    Role,
)
from leadbot_v2.goat.crm.service import GoatCRM
from leadbot_v2.goat.data_spine.models import (
    Lead,
    Opportunity,
)
from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
    TenantIsolationError,
)
from leadbot_v2.goat.workflow.follow_through import (
    FollowThroughEngine,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkforceRegion(str, Enum):
    TEXAS = "texas"
    PHILIPPINES = "philippines"


class WorkforceLevel(str, Enum):
    AGENT = "agent"
    TEAM_LEAD = "team_lead"
    MANAGER = "manager"


class SalesWorkType(str, Enum):
    QUALIFY = "qualify"
    CALL = "call"
    SMS = "sms"
    EMAIL = "email"
    FOLLOW_UP = "follow_up"
    APPOINTMENT = "appointment"
    BID_FOLLOW_UP = "bid_follow_up"
    ESTIMATE_FOLLOW_UP = "estimate_follow_up"
    CUSTOMER_CHECK_IN = "customer_check_in"
    RESEARCH = "research"


class WorkChannel(str, Enum):
    PHONE = "phone"
    SMS = "sms"
    EMAIL = "email"
    CRM = "crm"
    WEB = "web"


class QueueStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class SalesOpsAuthorizationError(PermissionError):
    pass


class CapacityError(RuntimeError):
    pass


class QueueStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShiftSchedule:
    timezone_name: str
    start_hour: int
    end_hour: int
    weekdays: frozenset[int] = frozenset({
        0, 1, 2, 3, 4,
    })

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone_name)

        if not 0 <= self.start_hour <= 23:
            raise ValueError("start_hour must be 0-23")

        if not 0 <= self.end_hour <= 23:
            raise ValueError("end_hour must be 0-23")

    def is_on_shift(
        self,
        at: datetime,
    ) -> bool:
        if at.tzinfo is None:
            raise ValueError(
                "shift evaluation requires timezone-aware datetime"
            )

        local = at.astimezone(
            ZoneInfo(self.timezone_name)
        )

        if local.weekday() not in self.weekdays:
            return False

        hour = local.hour

        if self.start_hour == self.end_hour:
            return True

        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour

        # Overnight shift.
        return (
            hour >= self.start_hour
            or hour < self.end_hour
        )


@dataclass(frozen=True)
class SalesTeam:
    team_id: str
    tenant_id: str
    business_unit_id: str
    name: str
    manager_user_id: str
    active: bool = True


@dataclass(frozen=True)
class AgentProfile:
    user_id: str
    tenant_id: str
    business_unit_id: str
    region: WorkforceRegion
    level: WorkforceLevel
    team_id: str
    shift: ShiftSchedule
    skills: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset({"english"})
    max_open_items: int = 25
    active: bool = True

    def __post_init__(self) -> None:
        if self.max_open_items < 1:
            raise ValueError(
                "max_open_items must be >= 1"
            )


@dataclass(frozen=True)
class CompensationPlan:
    """
    Configurable business rules only.

    These values calculate projections. They do not create payroll,
    transfer money, or authorize payment.
    """

    hourly_rate_cents: int
    direct_bonus_bps: int = 0
    team_override_bps: int = 0

    def __post_init__(self) -> None:
        if self.hourly_rate_cents < 0:
            raise ValueError(
                "hourly rate cannot be negative"
            )

        for value in (
            self.direct_bonus_bps,
            self.team_override_bps,
        ):
            if not 0 <= value <= 10_000:
                raise ValueError(
                    "basis points must be 0-10000"
                )

    def direct_bonus(
        self,
        revenue_cents: int,
    ) -> int:
        if revenue_cents < 0:
            raise ValueError(
                "revenue cannot be negative"
            )

        return (
            revenue_cents
            * self.direct_bonus_bps
            // 10_000
        )

    def team_override(
        self,
        revenue_cents: int,
    ) -> int:
        if revenue_cents < 0:
            raise ValueError(
                "revenue cannot be negative"
            )

        return (
            revenue_cents
            * self.team_override_bps
            // 10_000
        )


@dataclass(frozen=True)
class QueueItem:
    item_id: str
    tenant_id: str
    business_unit_id: str
    entity_type: str
    entity_id: str
    work_type: SalesWorkType
    channel: WorkChannel
    assigned_to: str
    team_id: str
    region: WorkforceRegion
    priority: int
    created_at: datetime
    due_at: datetime
    commitment_id: str
    status: QueueStatus = QueueStatus.PENDING
    attempts: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completion_evidence: str | None = None
    disposition: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.priority <= 100:
            raise ValueError(
                "priority must be 1-100"
            )

        if self.due_at.tzinfo is None:
            raise ValueError(
                "due_at must be timezone-aware"
            )


@dataclass(frozen=True)
class QualityReview:
    review_id: str
    item_id: str
    agent_user_id: str
    reviewer_user_id: str
    score: int
    notes: str
    created_at: datetime
    coaching_required: bool

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError(
                "QA score must be 0-100"
            )


@dataclass(frozen=True)
class PerformanceSnapshot:
    user_id: str
    open_items: int
    completed_items: int
    overdue_items: int
    total_attempts: int
    average_qa_score: float | None


class SalesOperations:
    """
    Unified Texas / Philippines sales operations layer.

    Connects workforce execution directly to:
      GOAT Data Spine
      GOAT CRM
      GOAT Follow-Through Engine
    """

    DEFAULT_SLA = {
        SalesWorkType.QUALIFY:
            timedelta(hours=1),

        SalesWorkType.CALL:
            timedelta(hours=2),

        SalesWorkType.SMS:
            timedelta(hours=2),

        SalesWorkType.EMAIL:
            timedelta(hours=4),

        SalesWorkType.FOLLOW_UP:
            timedelta(hours=24),

        SalesWorkType.APPOINTMENT:
            timedelta(hours=4),

        SalesWorkType.BID_FOLLOW_UP:
            timedelta(hours=8),

        SalesWorkType.ESTIMATE_FOLLOW_UP:
            timedelta(hours=8),

        SalesWorkType.CUSTOMER_CHECK_IN:
            timedelta(hours=24),

        SalesWorkType.RESEARCH:
            timedelta(hours=8),
    }

    def __init__(
        self,
        *,
        spine: InMemoryDataSpine,
        crm: GoatCRM,
        follow_through: FollowThroughEngine,
    ) -> None:
        self.spine = spine
        self.crm = crm
        self.follow_through = follow_through

        self._teams: dict[str, SalesTeam] = {}
        self._agents: dict[str, AgentProfile] = {}
        self._queue: dict[str, QueueItem] = {}
        self._reviews: list[QualityReview] = []
        self._compensation: dict[
            str,
            CompensationPlan,
        ] = {}

    @staticmethod
    def _require_executive(
        principal: Principal,
    ) -> None:
        if principal.role not in EXECUTIVE_ROLES:
            raise SalesOpsAuthorizationError(
                "executive authority required"
            )

    def _profile(
        self,
        user_id: str,
    ) -> AgentProfile:
        try:
            return self._agents[user_id]
        except KeyError as exc:
            raise KeyError(
                f"sales profile not found: {user_id}"
            ) from exc

    def _validate_actor_tenant(
        self,
        principal: Principal,
        tenant_id: str,
    ) -> None:
        if principal.tenant_id != tenant_id:
            raise TenantIsolationError(
                "cross-tenant sales operation denied"
            )

    def _can_manage_team(
        self,
        *,
        principal: Principal,
        team_id: str,
    ) -> bool:
        if principal.role in EXECUTIVE_ROLES:
            return True

        profile = self._agents.get(
            principal.user_id
        )

        if profile is None:
            return False

        return (
            profile.team_id == team_id
            and profile.level
            in {
                WorkforceLevel.TEAM_LEAD,
                WorkforceLevel.MANAGER,
            }
        )

    def create_team(
        self,
        *,
        principal: Principal,
        team_id: str,
        business_unit_id: str,
        name: str,
        manager_user_id: str,
    ) -> SalesTeam:
        self._require_executive(principal)

        if team_id in self._teams:
            raise ValueError(
                "team already exists"
            )

        team = SalesTeam(
            team_id=team_id,
            tenant_id=principal.tenant_id,
            business_unit_id=business_unit_id,
            name=name.strip(),
            manager_user_id=manager_user_id,
        )

        self._teams[team_id] = team

        self.spine.append_event(
            tenant_id=principal.tenant_id,
            aggregate_type="SalesTeam",
            aggregate_id=team_id,
            event_type="workforce.sales_team.created",
            actor_id=principal.user_id,
            payload={
                "name": team.name,
                "manager_user_id": manager_user_id,
            },
        )

        return team

    def register_agent(
        self,
        *,
        principal: Principal,
        profile: AgentProfile,
        compensation: CompensationPlan | None = None,
    ) -> AgentProfile:
        self._require_executive(principal)
        self._validate_actor_tenant(
            principal,
            profile.tenant_id,
        )

        if profile.team_id not in self._teams:
            raise ValueError(
                "agent team does not exist"
            )

        team = self._teams[profile.team_id]

        if (
            team.tenant_id != profile.tenant_id
            or team.business_unit_id
            != profile.business_unit_id
        ):
            raise TenantIsolationError(
                "agent/team scope mismatch"
            )

        self._agents[profile.user_id] = profile

        if compensation is not None:
            self._compensation[
                profile.user_id
            ] = compensation

        self.spine.append_event(
            tenant_id=profile.tenant_id,
            aggregate_type="WorkforceUser",
            aggregate_id=profile.user_id,
            event_type="workforce.agent.registered",
            actor_id=principal.user_id,
            payload={
                "region": profile.region.value,
                "level": profile.level.value,
                "team_id": profile.team_id,
                "skills": sorted(profile.skills),
            },
        )

        return profile

    def open_count(
        self,
        *,
        user_id: str,
    ) -> int:
        return sum(
            1
            for item in self._queue.values()
            if (
                item.assigned_to == user_id
                and item.status
                in {
                    QueueStatus.PENDING,
                    QueueStatus.IN_PROGRESS,
                    QueueStatus.BLOCKED,
                }
            )
        )

    def route_agent(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        region: WorkforceRegion,
        skill: str | None,
        at: datetime,
    ) -> AgentProfile:
        candidates: list[
            tuple[int, str, AgentProfile]
        ] = []

        for agent in self._agents.values():

            if not agent.active:
                continue

            if agent.tenant_id != tenant_id:
                continue

            if (
                agent.business_unit_id
                != business_unit_id
            ):
                continue

            if agent.region != region:
                continue

            if (
                skill
                and skill not in agent.skills
            ):
                continue

            if not agent.shift.is_on_shift(at):
                continue

            load = self.open_count(
                user_id=agent.user_id
            )

            if load >= agent.max_open_items:
                continue

            candidates.append(
                (
                    load,
                    agent.user_id,
                    agent,
                )
            )

        if not candidates:
            raise CapacityError(
                "no qualified on-shift sales capacity"
            )

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        return candidates[0][2]

    def assign_work(
        self,
        *,
        principal: Principal,
        entity_type: str,
        entity_id: str,
        work_type: SalesWorkType,
        channel: WorkChannel,
        assignee_user_id: str,
        priority: int = 50,
        due_at: datetime | None = None,
    ) -> QueueItem:
        assignee = self._profile(
            assignee_user_id
        )

        self._validate_actor_tenant(
            principal,
            assignee.tenant_id,
        )

        if not self._can_manage_team(
            principal=principal,
            team_id=assignee.team_id,
        ):
            raise SalesOpsAuthorizationError(
                "actor cannot assign this team"
            )

        self.spine.get(
            entity_id=entity_id,
            tenant_id=assignee.tenant_id,
        )

        if self.open_count(
            user_id=assignee.user_id
        ) >= assignee.max_open_items:
            raise CapacityError(
                "agent is at queue capacity"
            )

        if due_at is None:
            due_at = utc_now() + self.DEFAULT_SLA[
                work_type
            ]

        commitment = (
            self.follow_through.create_commitment(
                tenant_id=assignee.tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                owner_user_id=assignee.user_id,
                description=(
                    f"{work_type.value} via "
                    f"{channel.value}"
                ),
                due_at=due_at,
            )
        )

        item = QueueItem(
            item_id=f"work_{uuid4().hex}",
            tenant_id=assignee.tenant_id,
            business_unit_id=(
                assignee.business_unit_id
            ),
            entity_type=entity_type,
            entity_id=entity_id,
            work_type=work_type,
            channel=channel,
            assigned_to=assignee.user_id,
            team_id=assignee.team_id,
            region=assignee.region,
            priority=priority,
            created_at=utc_now(),
            due_at=due_at,
            commitment_id=(
                commitment.commitment_id
            ),
        )

        self._queue[item.item_id] = item

        self.spine.append_event(
            tenant_id=item.tenant_id,
            aggregate_type=entity_type,
            aggregate_id=entity_id,
            event_type="sales.work.assigned",
            actor_id=principal.user_id,
            payload={
                "work_item_id": item.item_id,
                "assigned_to": item.assigned_to,
                "work_type": work_type.value,
                "channel": channel.value,
                "due_at": due_at.isoformat(),
            },
        )

        return item

    def auto_route_work(
        self,
        *,
        principal: Principal,
        entity_type: str,
        entity_id: str,
        work_type: SalesWorkType,
        channel: WorkChannel,
        region: WorkforceRegion,
        business_unit_id: str,
        skill: str | None = None,
        priority: int = 50,
        at: datetime | None = None,
    ) -> QueueItem:
        self._validate_actor_tenant(
            principal,
            principal.tenant_id,
        )

        at = at or utc_now()

        agent = self.route_agent(
            tenant_id=principal.tenant_id,
            business_unit_id=business_unit_id,
            region=region,
            skill=skill,
            at=at,
        )

        return self.assign_work(
            principal=principal,
            entity_type=entity_type,
            entity_id=entity_id,
            work_type=work_type,
            channel=channel,
            assignee_user_id=agent.user_id,
            priority=priority,
        )

    def claim_work(
        self,
        *,
        principal: Principal,
        item_id: str,
    ) -> QueueItem:
        item = self._queue[item_id]

        self._validate_actor_tenant(
            principal,
            item.tenant_id,
        )

        if (
            principal.user_id
            != item.assigned_to
            and principal.role
            not in EXECUTIVE_ROLES
        ):
            raise SalesOpsAuthorizationError(
                "work is assigned to another user"
            )

        if item.status != QueueStatus.PENDING:
            raise QueueStateError(
                "only pending work may be claimed"
            )

        updated = replace(
            item,
            status=QueueStatus.IN_PROGRESS,
            started_at=utc_now(),
            attempts=item.attempts + 1,
        )

        self._queue[item_id] = updated

        self.spine.append_event(
            tenant_id=item.tenant_id,
            aggregate_type=item.entity_type,
            aggregate_id=item.entity_id,
            event_type="sales.work.started",
            actor_id=principal.user_id,
            payload={
                "work_item_id": item_id,
            },
        )

        return updated

    def record_attempt(
        self,
        *,
        principal: Principal,
        item_id: str,
        evidence: str,
    ) -> QueueItem:
        item = self._queue[item_id]

        self._validate_actor_tenant(
            principal,
            item.tenant_id,
        )

        if (
            principal.user_id
            != item.assigned_to
            and principal.role
            not in EXECUTIVE_ROLES
        ):
            raise SalesOpsAuthorizationError(
                "cannot record attempt for another agent"
            )

        if item.status not in {
            QueueStatus.PENDING,
            QueueStatus.IN_PROGRESS,
        }:
            raise QueueStateError(
                "work is not attemptable"
            )

        if not evidence.strip():
            raise ValueError(
                "attempt evidence required"
            )

        updated = replace(
            item,
            status=QueueStatus.IN_PROGRESS,
            started_at=(
                item.started_at
                or utc_now()
            ),
            attempts=item.attempts + 1,
        )

        self._queue[item_id] = updated

        self.spine.append_event(
            tenant_id=item.tenant_id,
            aggregate_type=item.entity_type,
            aggregate_id=item.entity_id,
            event_type="sales.work.attempt.recorded",
            actor_id=principal.user_id,
            payload={
                "work_item_id": item_id,
                "evidence": evidence.strip(),
                "attempt_number": updated.attempts,
            },
        )

        return updated

    def complete_work(
        self,
        *,
        principal: Principal,
        item_id: str,
        evidence: str,
        disposition: str,
        next_action: str | None = None,
        next_action_due_at: datetime | None = None,
    ) -> QueueItem:
        item = self._queue[item_id]

        self._validate_actor_tenant(
            principal,
            item.tenant_id,
        )

        if (
            principal.user_id
            != item.assigned_to
            and principal.role
            not in EXECUTIVE_ROLES
        ):
            raise SalesOpsAuthorizationError(
                "cannot complete another agent's work"
            )

        if item.status not in {
            QueueStatus.PENDING,
            QueueStatus.IN_PROGRESS,
        }:
            raise QueueStateError(
                "work is not open"
            )

        if not evidence.strip():
            raise ValueError(
                "completion evidence required"
            )

        if not disposition.strip():
            raise ValueError(
                "disposition required"
            )

        if (
            (next_action is None)
            != (next_action_due_at is None)
        ):
            raise ValueError(
                "next action and due date must "
                "be supplied together"
            )

        self.follow_through.complete_commitment(
            commitment_id=item.commitment_id,
            actor_id=principal.user_id,
            evidence=evidence.strip(),
        )

        updated = replace(
            item,
            status=QueueStatus.COMPLETED,
            completed_at=utc_now(),
            completion_evidence=evidence.strip(),
            disposition=disposition.strip(),
        )

        self._queue[item_id] = updated

        if next_action and next_action_due_at:

            if item.entity_type == "Lead":
                self.crm.set_lead_next_action(
                    tenant_id=item.tenant_id,
                    actor_id=principal.user_id,
                    lead_id=item.entity_id,
                    action=next_action,
                    due_at=next_action_due_at,
                )

            elif item.entity_type == "Opportunity":
                self.crm.set_opportunity_next_action(
                    tenant_id=item.tenant_id,
                    actor_id=principal.user_id,
                    opportunity_id=item.entity_id,
                    action=next_action,
                    due_at=next_action_due_at,
                )

        self.spine.append_event(
            tenant_id=item.tenant_id,
            aggregate_type=item.entity_type,
            aggregate_id=item.entity_id,
            event_type="sales.work.completed",
            actor_id=principal.user_id,
            payload={
                "work_item_id": item_id,
                "disposition": disposition.strip(),
                "evidence": evidence.strip(),
                "next_action": next_action,
            },
        )

        return updated

    def handoff(
        self,
        *,
        principal: Principal,
        item_id: str,
        new_assignee_user_id: str,
        reason: str,
    ) -> QueueItem:
        item = self._queue[item_id]

        self._validate_actor_tenant(
            principal,
            item.tenant_id,
        )

        if item.status == QueueStatus.COMPLETED:
            raise QueueStateError(
                "completed work cannot be handed off"
            )

        if (
            principal.user_id
            != item.assigned_to
            and not self._can_manage_team(
                principal=principal,
                team_id=item.team_id,
            )
            and principal.role
            not in EXECUTIVE_ROLES
        ):
            raise SalesOpsAuthorizationError(
                "handoff not authorized"
            )

        if not reason.strip():
            raise ValueError(
                "handoff reason required"
            )

        new_agent = self._profile(
            new_assignee_user_id
        )

        if new_agent.tenant_id != item.tenant_id:
            raise TenantIsolationError(
                "cross-tenant handoff denied"
            )

        if (
            new_agent.business_unit_id
            != item.business_unit_id
        ):
            raise SalesOpsAuthorizationError(
                "cross-business-unit handoff denied"
            )

        if self.open_count(
            user_id=new_agent.user_id
        ) >= new_agent.max_open_items:
            raise CapacityError(
                "new agent is at capacity"
            )

        old_assignee = item.assigned_to

        updated = replace(
            item,
            assigned_to=new_agent.user_id,
            team_id=new_agent.team_id,
            region=new_agent.region,
            status=QueueStatus.PENDING,
            started_at=None,
        )

        self._queue[item_id] = updated

        self.spine.append_event(
            tenant_id=item.tenant_id,
            aggregate_type=item.entity_type,
            aggregate_id=item.entity_id,
            event_type="sales.work.handed_off",
            actor_id=principal.user_id,
            payload={
                "work_item_id": item_id,
                "from": old_assignee,
                "to": new_agent.user_id,
                "from_region": item.region.value,
                "to_region": new_agent.region.value,
                "reason": reason.strip(),
            },
        )

        return updated

    def submit_quality_review(
        self,
        *,
        principal: Principal,
        item_id: str,
        score: int,
        notes: str,
    ) -> QualityReview:
        item = self._queue[item_id]

        self._validate_actor_tenant(
            principal,
            item.tenant_id,
        )

        if principal.user_id == item.assigned_to:
            raise SalesOpsAuthorizationError(
                "agent cannot QA-review own work"
            )

        if (
            not self._can_manage_team(
                principal=principal,
                team_id=item.team_id,
            )
            and principal.role
            not in EXECUTIVE_ROLES
        ):
            raise SalesOpsAuthorizationError(
                "QA reviewer lacks authority"
            )

        review = QualityReview(
            review_id=f"qa_{uuid4().hex}",
            item_id=item_id,
            agent_user_id=item.assigned_to,
            reviewer_user_id=principal.user_id,
            score=score,
            notes=notes.strip(),
            created_at=utc_now(),
            coaching_required=score < 80,
        )

        self._reviews.append(review)

        self.spine.append_event(
            tenant_id=item.tenant_id,
            aggregate_type="WorkforceUser",
            aggregate_id=item.assigned_to,
            event_type="sales.qa.reviewed",
            actor_id=principal.user_id,
            payload={
                "work_item_id": item_id,
                "score": score,
                "coaching_required": (
                    review.coaching_required
                ),
            },
        )

        return review

    def queue_for(
        self,
        *,
        principal: Principal,
        user_id: str | None = None,
    ) -> tuple[QueueItem, ...]:
        target = user_id or principal.user_id

        if (
            target != principal.user_id
            and principal.role
            not in EXECUTIVE_ROLES
        ):
            profile = self._profile(
                principal.user_id
            )

            target_profile = self._profile(
                target
            )

            if (
                profile.level
                not in {
                    WorkforceLevel.TEAM_LEAD,
                    WorkforceLevel.MANAGER,
                }
                or profile.team_id
                != target_profile.team_id
            ):
                raise SalesOpsAuthorizationError(
                    "cannot view another agent's queue"
                )

        items = [
            item
            for item in self._queue.values()
            if (
                item.tenant_id
                == principal.tenant_id
                and item.assigned_to == target
            )
        ]

        items.sort(
            key=lambda item: (
                item.status
                == QueueStatus.COMPLETED,
                -item.priority,
                item.due_at,
                item.created_at,
            )
        )

        return tuple(items)

    def overdue_items(
        self,
        *,
        tenant_id: str,
        now: datetime,
    ) -> tuple[QueueItem, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._queue.values()
                    if (
                        item.tenant_id == tenant_id
                        and item.status
                        in {
                            QueueStatus.PENDING,
                            QueueStatus.IN_PROGRESS,
                            QueueStatus.BLOCKED,
                        }
                        and now > item.due_at
                    )
                ),
                key=lambda item: (
                    item.due_at,
                    -item.priority,
                ),
            )
        )

    def performance(
        self,
        *,
        tenant_id: str,
        user_id: str,
        now: datetime,
    ) -> PerformanceSnapshot:
        items = [
            item
            for item in self._queue.values()
            if (
                item.tenant_id == tenant_id
                and item.assigned_to == user_id
            )
        ]

        open_items = sum(
            1
            for item in items
            if item.status
            in {
                QueueStatus.PENDING,
                QueueStatus.IN_PROGRESS,
                QueueStatus.BLOCKED,
            }
        )

        completed = sum(
            1
            for item in items
            if item.status
            == QueueStatus.COMPLETED
        )

        overdue = sum(
            1
            for item in items
            if (
                item.status
                in {
                    QueueStatus.PENDING,
                    QueueStatus.IN_PROGRESS,
                    QueueStatus.BLOCKED,
                }
                and now > item.due_at
            )
        )

        attempts = sum(
            item.attempts
            for item in items
        )

        qa_scores = [
            review.score
            for review in self._reviews
            if review.agent_user_id == user_id
        ]

        return PerformanceSnapshot(
            user_id=user_id,
            open_items=open_items,
            completed_items=completed,
            overdue_items=overdue,
            total_attempts=attempts,
            average_qa_score=(
                mean(qa_scores)
                if qa_scores
                else None
            ),
        )

    def compensation_projection(
        self,
        *,
        user_id: str,
        attributable_revenue_cents: int,
    ) -> dict[str, int]:
        plan = self._compensation[user_id]

        return {
            "direct_bonus_cents":
                plan.direct_bonus(
                    attributable_revenue_cents
                ),

            "team_override_cents":
                plan.team_override(
                    attributable_revenue_cents
                ),
        }
