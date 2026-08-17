from __future__ import annotations

from datetime import timedelta

from .canonical import (
    stable_hash,
)

from .models import (
    RefreshCadence,
    RefreshTask,
)


CADENCE_SECONDS = {
    RefreshCadence.IMMEDIATE:
        0,

    RefreshCadence.HOURLY:
        3600,

    RefreshCadence.DAILY:
        86400,

    RefreshCadence.WEEKLY:
        604800,

    RefreshCadence.MONTHLY:
        2592000,

    RefreshCadence.QUARTERLY:
        7776000,

    RefreshCadence.ANNUAL:
        31536000,
}


class KnowledgeRefreshPlanner:
    def __init__(
        self,
        *,
        policies,
    ) -> None:
        self.policies = dict(
            policies
        )

    def incremental_task(
        self,
        *,
        domain,
        now,
        source_id=None,
        reason="scheduled incremental refresh",
    ):
        policy = self.policies[
            domain
        ]

        seconds = CADENCE_SECONDS[
            policy.cadence
        ]

        due_at = (
            now
            + timedelta(
                seconds=seconds
            )
        )

        priority = (
            100
            if policy.cadence
            in {
                RefreshCadence.IMMEDIATE,
                RefreshCadence.HOURLY,
            }
            else 70
            if policy.cadence
            in {
                RefreshCadence.DAILY,
                RefreshCadence.WEEKLY,
            }
            else 40
        )

        task_id = stable_hash(
            {
                "domain":
                    domain,

                "source_id":
                    source_id,

                "due_at":
                    due_at,

                "full_audit":
                    False,

                "reason":
                    reason,
            }
        )[:24]

        return RefreshTask(
            task_id=(
                task_id
            ),
            domain=domain,
            source_id=source_id,
            due_at=due_at,
            full_audit=False,
            priority=priority,
            reason=reason,
        )

    def quarterly_audit_task(
        self,
        *,
        domain,
        now,
        source_id=None,
    ):
        policy = self.policies[
            domain
        ]

        seconds = CADENCE_SECONDS[
            policy.full_audit_cadence
        ]

        due_at = (
            now
            + timedelta(
                seconds=seconds
            )
        )

        task_id = stable_hash(
            {
                "domain":
                    domain,

                "source_id":
                    source_id,

                "due_at":
                    due_at,

                "full_audit":
                    True,
            }
        )[:24]

        return RefreshTask(
            task_id=(
                task_id
            ),
            domain=domain,
            source_id=source_id,
            due_at=due_at,
            full_audit=True,
            priority=85,
            reason=(
                "scheduled deep knowledge audit"
            ),
        )

    def event_driven_task(
        self,
        *,
        domain,
        now,
        source_id=None,
        reason,
    ):
        task_id = stable_hash(
            {
                "domain":
                    domain,

                "source_id":
                    source_id,

                "due_at":
                    now,

                "full_audit":
                    False,

                "reason":
                    reason,
            }
        )[:24]

        return RefreshTask(
            task_id=(
                task_id
            ),
            domain=domain,
            source_id=source_id,
            due_at=now,
            full_audit=False,
            priority=100,
            reason=reason,
        )
