from __future__ import annotations

from collections import deque

from .models import (
    DependencyEdge,
    DependencyError,
)


class ModelDependencyGraph:
    def __init__(self):
        self._edges = {}
        self._reverse = {}

    def add(
        self,
        source_id,
        dependent_id,
        *,
        relationship="depends_on",
    ):
        if source_id == dependent_id:
            raise DependencyError(
                "self dependency prohibited"
            )

        edge = DependencyEdge(
            source_id=source_id,
            dependent_id=dependent_id,
            relationship=relationship,
        )

        self._edges.setdefault(
            source_id,
            {},
        )[
            dependent_id
        ] = edge

        self._reverse.setdefault(
            dependent_id,
            set(),
        ).add(
            source_id
        )

        try:
            self.topological_order()

        except Exception:
            self._edges[
                source_id
            ].pop(
                dependent_id,
                None,
            )

            self._reverse[
                dependent_id
            ].discard(
                source_id
            )

            raise

        return edge

    def remove(
        self,
        source_id,
        dependent_id,
    ):
        self._edges.get(
            source_id,
            {},
        ).pop(
            dependent_id,
            None,
        )

        self._reverse.get(
            dependent_id,
            set(),
        ).discard(
            source_id
        )

    def nodes(self):
        result = (
            set(self._edges)
            | set(self._reverse)
        )

        for dependencies in self._edges.values():
            result.update(
                dependencies
            )

        return tuple(
            sorted(result)
        )

    def edges(self):
        return tuple(
            edge
            for source
            in sorted(self._edges)
            for _, edge
            in sorted(
                self._edges[
                    source
                ].items()
            )
        )

    def topological_order(self):
        nodes = set(
            self.nodes()
        )

        indegree = {
            node: 0
            for node
            in nodes
        }

        for source in nodes:
            for dependent in self._edges.get(
                source,
                {},
            ):
                indegree[
                    dependent
                ] += 1

        ready = deque(
            sorted(
                node
                for node, degree
                in indegree.items()
                if degree == 0
            )
        )

        order = []

        while ready:
            node = ready.popleft()

            order.append(node)

            for dependent in sorted(
                self._edges.get(
                    node,
                    {},
                )
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

        if len(order) != len(nodes):
            raise DependencyError(
                "model dependency cycle detected"
            )

        return tuple(order)

    def impacted(
        self,
        changed_ids,
    ):
        queue = deque(
            sorted(
                set(changed_ids)
            )
        )

        seen = set(queue)

        impacted = []

        while queue:
            source = queue.popleft()

            for dependent in sorted(
                self._edges.get(
                    source,
                    {},
                )
            ):
                if dependent in seen:
                    continue

                seen.add(
                    dependent
                )

                impacted.append(
                    dependent
                )

                queue.append(
                    dependent
                )

        return tuple(
            impacted
        )
