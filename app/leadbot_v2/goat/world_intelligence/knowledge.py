from __future__ import annotations

from dataclasses import replace

from .canonical import (
    stable_hash,
)

from .models import (
    EvidenceStatus,
    FactState,
    KnowledgeDecision,
    KnowledgeFact,
    SourceAuthority,
)

from .sources import (
    AUTHORITY_WEIGHT,
)


class WorldKnowledgeGraph:
    def __init__(
        self,
        *,
        freshness_engine,
        policies,
    ) -> None:
        self.freshness_engine = (
            freshness_engine
        )

        self.policies = dict(
            policies
        )

        self._facts = {}

        self._subject_index = {}

    def fact(
        self,
        fact_id,
    ):
        return self._facts.get(
            fact_id
        )

    def all_facts(
        self,
    ):
        return tuple(
            self._facts.values()
        )

    def _index(
        self,
        fact,
    ):
        key = (
            fact.domain,
            fact.subject,
            fact.predicate,
            fact.jurisdiction,
        )

        self._subject_index.setdefault(
            key,
            []
        ).append(
            fact.fact_id
        )

    def derive_fact(
        self,
        *,
        evidence,
        authority,
    ):
        if (
            evidence.status
            is not EvidenceStatus.ACCEPTED
        ):
            return None

        fact_id = stable_hash(
            {
                "domain":
                    evidence.domain,

                "subject":
                    evidence.subject,

                "predicate":
                    evidence.predicate,

                "value":
                    evidence.value,

                "jurisdiction":
                    evidence.jurisdiction,

                "source_id":
                    evidence.source_id,

                "evidence_id":
                    evidence.evidence_id,
            }
        )[:32]

        fact = KnowledgeFact(
            fact_id=fact_id,
            domain=evidence.domain,
            subject=(
                evidence.subject
            ),
            predicate=(
                evidence.predicate
            ),
            value=(
                evidence.value
            ),
            jurisdiction=(
                evidence.jurisdiction
            ),
            authority=authority,
            confidence=(
                evidence.confidence
            ),
            evidence_ids=(
                evidence.evidence_id,
            ),
            state=(
                FactState.ACTIVE
            ),
            valid_from=(
                evidence.valid_from
            ),
            valid_until=(
                evidence.valid_until
            ),
            first_seen_at=(
                evidence.acquired_at
            ),
            last_confirmed_at=(
                evidence.acquired_at
            ),
        )

        self._facts[
            fact_id
        ] = fact

        self._index(
            fact
        )

        return fact

    def candidates(
        self,
        *,
        domain,
        subject,
        predicate,
        jurisdiction,
    ):
        key = (
            domain,
            subject,
            predicate,
            jurisdiction,
        )

        return tuple(
            self._facts[
                fact_id
            ]
            for fact_id
            in self._subject_index.get(
                key,
                ()
            )
        )

    def resolve(
        self,
        *,
        domain,
        subject,
        predicate,
        jurisdiction,
        now,
        contradictions=(),
        high_impact=False,
    ):
        candidates = list(
            self.candidates(
                domain=domain,
                subject=subject,
                predicate=predicate,
                jurisdiction=jurisdiction,
            )
        )

        policy = self.policies[
            domain
        ]

        valid = []

        for fact in candidates:
            if fact.state not in {
                FactState.ACTIVE,
                FactState.CONTESTED,
            }:
                continue

            if (
                fact.valid_from
                and now
                < fact.valid_from
            ):
                continue

            if (
                fact.valid_until
                and now
                > fact.valid_until
            ):
                continue

            freshness = (
                self.freshness_engine
                .assess(
                    timestamp=(
                        fact.last_confirmed_at
                    ),
                    now=now,
                    freshness_seconds=(
                        policy.freshness_seconds
                    ),
                )
            )

            if freshness.expired:
                continue

            adjusted = (
                fact.confidence
                * AUTHORITY_WEIGHT[
                    fact.authority
                ]
                * freshness.freshness_score
            )

            valid.append(
                (
                    adjusted,
                    fact,
                )
            )

        valid.sort(
            key=lambda row: (
                row[
                    0
                ],
                row[
                    1
                ].fact_id,
            ),
            reverse=True,
        )

        related = tuple(
            contradiction
            for contradiction
            in contradictions
            if (
                contradiction.subject
                == subject
                and contradiction.predicate
                == predicate
                and contradiction.jurisdiction
                == jurisdiction
            )
        )

        if not valid:
            return KnowledgeDecision(
                fact=None,
                contradictions=related,
                usable=False,
                reason=(
                    "no fresh active fact available"
                ),
            )

        winner = valid[
            0
        ][
            1
        ]

        if (
            high_impact
            and policy
            .require_primary_for_high_impact
            and winner.authority
            not in {
                SourceAuthority.OFFICIAL,
                SourceAuthority.PRIMARY,
            }
        ):
            return KnowledgeDecision(
                fact=winner,
                contradictions=related,
                usable=False,
                reason=(
                    "high-impact decision requires "
                    "official or primary evidence"
                ),
            )

        if related:
            return KnowledgeDecision(
                fact=winner,
                contradictions=related,
                usable=False,
                reason=(
                    "material contradiction requires "
                    "resolution before authoritative use"
                ),
            )

        return KnowledgeDecision(
            fact=winner,
            contradictions=(),
            usable=True,
            reason=(
                "highest-authority fresh fact selected"
            ),
        )
