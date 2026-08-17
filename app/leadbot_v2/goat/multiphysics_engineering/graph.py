from __future__ import annotations

from .models import (
    GraphExecutionResult,
    MultiphysicsError,
)


class MultiphysicsGraph:
    def __init__(self) -> None:
        self._nodes = {}

    def add_node(
        self,
        node,
    ) -> None:
        if node.node_id in self._nodes:
            raise MultiphysicsError(
                "duplicate analysis node"
            )

        self._nodes[
            node.node_id
        ] = node

    def execution_order(self):
        indegree = {
            node_id: 0
            for node_id
            in self._nodes
        }

        dependents = {
            node_id: []
            for node_id
            in self._nodes
        }

        for node in self._nodes.values():
            for dependency in node.dependencies:
                if dependency not in self._nodes:
                    raise MultiphysicsError(
                        f"missing dependency "
                        f"{dependency} "
                        f"for {node.node_id}"
                    )

                indegree[
                    node.node_id
                ] += 1

                dependents[
                    dependency
                ].append(
                    node.node_id
                )

        ready = sorted(
            node_id
            for node_id, degree
            in indegree.items()
            if degree == 0
        )

        order = []

        while ready:
            node_id = ready.pop(0)

            order.append(node_id)

            for dependent in sorted(
                dependents[node_id]
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
                    ready.append(
                        dependent
                    )

                    ready.sort()

        if len(order) != len(
            self._nodes
        ):
            raise MultiphysicsError(
                "multiphysics dependency "
                "cycle detected"
            )

        return tuple(order)

    def execute(
        self,
        *,
        initial_context=None,
    ):
        values = dict(
            initial_context
            or {}
        )

        order = self.execution_order()

        for node_id in order:
            node = self._nodes[
                node_id
            ]

            dependency_values = {
                dependency:
                    values[dependency]
                for dependency
                in node.dependencies
            }

            context = {
                **values,
                "dependencies":
                    dependency_values,
            }

            values[node_id] = (
                node.evaluator(
                    context
                )
            )

        return GraphExecutionResult(
            values=values,
            execution_order=order,
        )
