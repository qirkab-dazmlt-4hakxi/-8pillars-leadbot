from __future__ import annotations

import re

from .models import (
    WorkflowDefinitionError,
    WorkflowSpec,
)


_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)


def validate_spec(spec: WorkflowSpec) -> None:
    seen: set[str] = set()

    for step in spec.steps:
        if not _ID.fullmatch(step.step_id):
            raise WorkflowDefinitionError(
                f"invalid step id: {step.step_id!r}"
            )

        if step.step_id in seen:
            raise WorkflowDefinitionError(
                f"duplicate step id: {step.step_id}"
            )

        seen.add(step.step_id)

        if len(set(step.dependencies)) != len(
            step.dependencies
        ):
            raise WorkflowDefinitionError(
                f"{step.step_id}: duplicate dependencies"
            )

        if step.step_id in step.dependencies:
            raise WorkflowDefinitionError(
                f"{step.step_id}: self dependency"
            )

    for step in spec.steps:
        for dependency in step.dependencies:
            if dependency not in seen:
                raise WorkflowDefinitionError(
                    f"{step.step_id}: unknown dependency "
                    f"{dependency}"
                )

    topological_order(spec)


def topological_order(
    spec: WorkflowSpec,
) -> tuple[str, ...]:
    step_map = spec.step_map()

    incoming: dict[str, int] = {
        step_id: 0
        for step_id in step_map
    }

    outgoing: dict[str, list[str]] = {
        step_id: []
        for step_id in step_map
    }

    for step in spec.steps:
        for dependency in step.dependencies:
            incoming[step.step_id] += 1
            outgoing[dependency].append(
                step.step_id
            )

    ready = sorted(
        step_id
        for step_id, count in incoming.items()
        if count == 0
    )

    result: list[str] = []

    while ready:
        current = ready.pop(0)

        result.append(current)

        for child in sorted(
            outgoing[current]
        ):
            incoming[child] -= 1

            if incoming[child] == 0:
                ready.append(child)
                ready.sort()

    if len(result) != len(step_map):
        blocked = sorted(
            step_id
            for step_id, count
            in incoming.items()
            if count > 0
        )

        raise WorkflowDefinitionError(
            "workflow dependency cycle detected: "
            + ", ".join(blocked)
        )

    return tuple(result)


def reverse_topological_order(
    spec: WorkflowSpec,
) -> tuple[str, ...]:
    return tuple(
        reversed(
            topological_order(spec)
        )
    )


def dependencies_satisfied(
    spec: WorkflowSpec,
    *,
    step_id: str,
    succeeded: set[str],
) -> bool:
    step = spec.step_map()[step_id]

    return all(
        dependency in succeeded
        for dependency in step.dependencies
    )
