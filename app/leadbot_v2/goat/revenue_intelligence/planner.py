from __future__ import annotations

from .bayesian import (
    AdaptiveRevenueMemory,
)

from .models import (
    ActionKind,
    ActionPlan,
    CanonicalLead,
    DecisionTier,
)


class NextBestActionPlanner:
    def __init__(
        self,
        memory: AdaptiveRevenueMemory,
    ) -> None:
        self.memory = memory

    def plan(
        self,
        lead: CanonicalLead,
        tier: DecisionTier,
    ) -> ActionPlan:
        if tier is DecisionTier.REJECT:
            return ActionPlan(
                kind=ActionKind.NO_ACTION,
                priority=0,
                due_seconds=0,
                reason=(
                    "rejected by deterministic "
                    "revenue policy"
                ),
            )

        if tier is DecisionTier.EXECUTIVE:
            return ActionPlan(
                kind=(
                    ActionKind
                    .EXECUTIVE_REVIEW
                ),
                priority=100,
                due_seconds=60,
                reason=(
                    "high-value opportunity "
                    "requires executive visibility"
                ),
                requires_human_approval=True,
            )

        channels = []

        if lead.phone:
            channels.append(
                (
                    self.memory.action_quality(
                        ActionKind.CALL
                    )
                    + lead.features
                    .urgency
                    * 0.16,
                    ActionKind.CALL,
                )
            )

            channels.append(
                (
                    self.memory.action_quality(
                        ActionKind.SMS
                    )
                    + lead.features
                    .urgency
                    * 0.12,
                    ActionKind.SMS,
                )
            )

        if lead.email:
            channels.append(
                (
                    self.memory.action_quality(
                        ActionKind.EMAIL
                    ),
                    ActionKind.EMAIL,
                )
            )

        if not channels:
            return ActionPlan(
                kind=ActionKind.RESEARCH,
                priority=65,
                due_seconds=300,
                reason=(
                    "qualified demand without "
                    "direct contact channel"
                ),
            )

        channels.sort(
            key=lambda item: (
                item[0],
                item[1].value,
            ),
            reverse=True,
        )

        kind = channels[
            0
        ][1]

        if tier is DecisionTier.PRIORITY:
            priority = 95
            due = 60

        elif tier is DecisionTier.QUALIFY:
            priority = 75
            due = 600

        else:
            priority = 45
            due = 3600

        return ActionPlan(
            kind=kind,
            priority=priority,
            due_seconds=due,
            reason=(
                "adaptive expected-response "
                "channel selection"
            ),
            requires_human_approval=(
                kind
                in {
                    ActionKind.CALL,
                    ActionKind.SMS,
                    ActionKind.EMAIL,
                }
            ),
        )
