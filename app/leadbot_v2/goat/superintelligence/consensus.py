from __future__ import annotations

from collections import defaultdict

from .canonical import canonical_json

from .models import (
    ExpertOpinion,
    clamp01,
)


class ConsensusEngine:
    """
    High-assurance multi-expert consensus.

    Ranking separates three distinct concepts:

    1. Expert confidence
       How strongly the expert supports its own conclusion.

    2. Agreement mass
       How much independent expert weight supports the conclusion.

    3. Support share
       How much of all confidence-weighted evidence supports it.

    Risk is deliberately NOT a negative multiplier here.

    A high-risk conclusion must not become less likely to win merely
    because it is dangerous. Risk belongs in the autonomy/policy layer,
    where it increases review, approval and execution restrictions.
    """

    def decide(
        self,
        opinions: tuple[
            ExpertOpinion,
            ...,
        ],
        *,
        weights: dict[
            str,
            float,
        ] | None = None,
    ):
        if not opinions:
            raise ValueError(
                "at least one expert opinion required"
            )

        weights = dict(
            weights or {}
        )

        groups = defaultdict(
            list
        )

        for opinion in opinions:
            groups[
                canonical_json(
                    opinion.answer
                )
            ].append(
                opinion
            )

        expert_weights = {}

        total_weight = 0.0
        total_support = 0.0

        for opinion in opinions:
            expert_weight = max(
                0.01,
                float(
                    weights.get(
                        opinion.expert_id,
                        1.0,
                    )
                ),
            )

            expert_weights[
                opinion.expert_id
            ] = expert_weight

            total_weight += (
                expert_weight
            )

            total_support += (
                expert_weight
                * clamp01(
                    opinion.confidence
                )
            )

        ranked = []

        for key, group in groups.items():
            group_weight = 0.0
            group_support = 0.0

            for opinion in group:
                expert_weight = (
                    expert_weights[
                        opinion.expert_id
                    ]
                )

                confidence = clamp01(
                    opinion.confidence
                )

                group_weight += (
                    expert_weight
                )

                group_support += (
                    expert_weight
                    * confidence
                )

            weighted_confidence = (
                group_support
                / group_weight
                if group_weight
                else 0.0
            )

            agreement_mass = (
                group_weight
                / total_weight
                if total_weight
                else 0.0
            )

            support_share = (
                group_support
                / total_support
                if total_support
                else 0.0
            )

            score = clamp01(
                weighted_confidence
                * 0.50
                + agreement_mass
                * 0.25
                + support_share
                * 0.25
            )

            ranked.append(
                (
                    score,
                    key,
                    group[0].answer,
                    tuple(
                        group
                    ),
                    weighted_confidence,
                    agreement_mass,
                    support_share,
                )
            )

        ranked.sort(
            key=lambda row: (
                row[0],
                row[1],
            ),
            reverse=True,
        )

        winner = ranked[
            0
        ]

        runner_score = (
            ranked[
                1
            ][
                0
            ]
            if len(
                ranked
            ) > 1
            else 0.0
        )

        margin = max(
            0.0,
            winner[
                0
            ]
            - runner_score,
        )

        confidence = clamp01(
            winner[
                0
            ]
            * 0.85
            + margin
            * 0.15
        )

        alternatives = tuple(
            row[
                2
            ]
            for row
            in ranked[
                1:
            ]
        )

        return (
            winner[
                2
            ],
            confidence,
            alternatives,
        )
