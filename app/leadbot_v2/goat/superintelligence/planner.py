from __future__ import annotations

from dataclasses import (
    dataclass,
)

from .canonical import (
    stable_hash,
)


@dataclass(frozen=True)
class PlanStep:
    step_id: str

    action: str

    expected_value: float

    cost: float
    risk: float

    reversible: bool

    prerequisites: tuple[
        str,
        ...,
    ] = ()

    @property
    def utility(
        self,
    ) -> float:
        return (
            self.expected_value
            - self.cost
            - self.risk
        )


@dataclass(frozen=True)
class Plan:
    plan_id: str

    steps: tuple[
        PlanStep,
        ...,
    ]

    utility: float


class BeamPlanner:
    def __init__(
        self,
        *,
        beam_width: int = 8,
        max_steps: int = 8,
    ) -> None:
        if (
            beam_width <= 0
            or max_steps <= 0
        ):
            raise ValueError(
                "beam_width and max_steps "
                "must be positive"
            )

        self.beam_width = (
            beam_width
        )

        self.max_steps = (
            max_steps
        )

    def plan(
        self,
        candidate_steps: tuple[
            PlanStep,
            ...,
        ],
    ) -> Plan:
        if not candidate_steps:
            return Plan(
                plan_id=stable_hash(
                    {
                        "steps":
                            [],
                    }
                )[:32],
                steps=(),
                utility=0.0,
            )

        beam = [
            (
                0.0,
                tuple(),
                frozenset(),
            )
        ]

        best = beam[
            0
        ]

        for _ in range(
            min(
                self.max_steps,
                len(
                    candidate_steps
                ),
            )
        ):
            next_beam = []

            for (
                score,
                steps,
                used,
            ) in beam:
                for step in (
                    candidate_steps
                ):
                    if (
                        step.step_id
                        in used
                    ):
                        continue

                    if any(
                        dependency
                        not in used
                        for dependency
                        in step.prerequisites
                    ):
                        continue

                    new_steps = (
                        steps
                        + (
                            step,
                        )
                    )

                    new_used = (
                        used
                        | {
                            step.step_id
                        }
                    )

                    new_score = (
                        score
                        + step.utility
                    )

                    next_beam.append(
                        (
                            new_score,
                            new_steps,
                            new_used,
                        )
                    )

            if not next_beam:
                break

            next_beam.sort(
                key=lambda row: (
                    row[0],
                    tuple(
                        step.step_id
                        for step
                        in row[1]
                    ),
                ),
                reverse=True,
            )

            beam = next_beam[
                :
                self.beam_width
            ]

            if (
                beam[0][0]
                > best[0]
            ):
                best = beam[
                    0
                ]

        score, steps, _ = best

        plan_id = stable_hash(
            {
                "steps":
                    tuple(
                        step.step_id
                        for step
                        in steps
                    ),
                "utility":
                    score,
            }
        )[:32]

        return Plan(
            plan_id=(
                plan_id
            ),
            steps=steps,
            utility=score,
        )
