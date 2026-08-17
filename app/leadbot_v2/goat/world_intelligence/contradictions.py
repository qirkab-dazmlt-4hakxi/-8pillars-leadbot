from __future__ import annotations

from .canonical import (
    stable_hash,
)

from .models import (
    Contradiction,
    FactState,
)


class ContradictionDetector:
    def detect(
        self,
        facts,
    ):
        groups = {}

        for fact in facts:
            if fact.state not in {
                FactState.ACTIVE,
                FactState.CONTESTED,
            }:
                continue

            key = (
                fact.domain,
                fact.subject,
                fact.predicate,
                fact.jurisdiction,
            )

            groups.setdefault(
                key,
                []
            ).append(
                fact
            )

        contradictions = []

        for (
            key,
            rows,
        ) in groups.items():
            values = {
                repr(
                    row.value
                )
                for row
                in rows
            }

            if len(values) <= 1:
                continue

            ranked = sorted(
                rows,
                key=lambda fact: (
                    fact.confidence,
                    fact.authority.value,
                    fact.fact_id,
                ),
                reverse=True,
            )

            severity = min(
                1.0,
                sum(
                    fact.confidence
                    for fact
                    in ranked[
                        :2
                    ]
                )
                / 2.0,
            )

            contradiction_id = stable_hash(
                {
                    "key":
                        key,

                    "fact_ids":
                        tuple(
                            fact.fact_id
                            for fact
                            in ranked
                        ),
                }
            )[:24]

            contradictions.append(
                Contradiction(
                    contradiction_id=(
                        contradiction_id
                    ),
                    subject=key[
                        1
                    ],
                    predicate=key[
                        2
                    ],
                    jurisdiction=key[
                        3
                    ],
                    fact_ids=tuple(
                        fact.fact_id
                        for fact
                        in ranked
                    ),
                    severity=(
                        severity
                    ),
                    reason=(
                        "multiple active facts assert "
                        "different values for the same "
                        "subject/predicate/jurisdiction"
                    ),
                )
            )

        return tuple(
            sorted(
                contradictions,
                key=lambda item: (
                    item.severity,
                    item.contradiction_id,
                ),
                reverse=True,
            )
        )
