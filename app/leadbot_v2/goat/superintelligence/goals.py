from __future__ import annotations

from collections import (
    defaultdict,
    deque,
)

from .models import (
    Goal,
    InvariantViolation,
)


class GoalGraph:
    def __init__(
        self,
    ) -> None:
        self._goals: dict[
            str,
            Goal,
        ] = {}

    def add(
        self,
        goal: Goal,
    ) -> None:
        if (
            goal.goal_id
            in self._goals
        ):
            raise InvariantViolation(
                f"duplicate goal: "
                f"{goal.goal_id}"
            )

        self._goals[
            goal.goal_id
        ] = goal

    def ordered(
        self,
    ) -> tuple[
        Goal,
        ...,
    ]:
        indegree = {
            goal_id: 0
            for goal_id
            in self._goals
        }

        dependents = defaultdict(
            list
        )

        for goal in (
            self._goals.values()
        ):
            for dependency in (
                goal.dependencies
            ):
                if (
                    dependency
                    not in self._goals
                ):
                    raise InvariantViolation(
                        f"missing goal dependency: "
                        f"{dependency}"
                    )

                indegree[
                    goal.goal_id
                ] += 1

                dependents[
                    dependency
                ].append(
                    goal.goal_id
                )

        ready = [
            goal_id
            for goal_id, degree
            in indegree.items()
            if degree == 0
        ]

        ready.sort(
            key=lambda goal_id: (
                self._goals[
                    goal_id
                ].priority,
                goal_id,
            ),
            reverse=True,
        )

        queue = deque(
            ready
        )

        ordered = []

        while queue:
            goal_id = (
                queue.popleft()
            )

            ordered.append(
                self._goals[
                    goal_id
                ]
            )

            for dependent in (
                dependents[
                    goal_id
                ]
            ):
                indegree[
                    dependent
                ] -= 1

                if (
                    indegree[
                        dependent
                    ]
                    == 0
                ):
                    queue.append(
                        dependent
                    )

        if (
            len(
                ordered
            )
            != len(
                self._goals
            )
        ):
            raise InvariantViolation(
                "goal dependency cycle detected"
            )

        return tuple(
            ordered
        )
