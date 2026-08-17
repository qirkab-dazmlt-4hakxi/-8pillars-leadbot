from __future__ import annotations

from collections import (
    defaultdict,
)

from .canonical import (
    canonical_json,
)

from .models import (
    ExpertOpinion,
    RiskLevel,
    clamp01,
)


class ConsensusEngine:
    RISK_PENALTY = {
        RiskLevel.LOW:
            1.0,

        RiskLevel.MODERATE:
            0.90,

        RiskLevel.HIGH:
            0.72,

        RiskLevel.CRITICAL:
            0.45,
    }

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

        ranked = []

        for key, group in (
            groups.items()
        ):
            score = 0.0
            total_weight = 0.0

            for opinion in group:
                expert_weight = max(
                    0.01,
                    float(
                        weights.get(
                            opinion.expert_id,
                            1.0,
                        )
                    ),
                )

                total_weight += (
                    expert_weight
                )

                score += (
                    expert_weight
                    * opinion.confidence
                    * self.RISK_PENALTY[
                        opinion.risk
                    ]
                )

            normalized = (
                score
                / total_weight
                if total_weight
                else 0.0
            )

            agreement_bonus = min(
                0.12,
                0.03
                * (
                    len(
                        group
                    )
                    - 1
                ),
            )

            ranked.append(
                (
                    clamp01(
                        normalized
                        + agreement_bonus
                    ),
                    key,
                    group[0].answer,
                    tuple(
                        group
                    ),
                )
            )

        ranked.sort(
            key=lambda row: (
                row[0],
                row[1],
            ),
            reverse=True,
        )

        best = ranked[
            0
        ]

        runner = (
            ranked[1][0]
            if len(
                ranked
            ) > 1
            else 0.0
        )

        confidence = clamp01(
            best[0]
            * 0.85
            + max(
                0.0,
                best[0]
                - runner,
            )
            * 0.15
        )

        alternatives = tuple(
            row[2]
            for row
            in ranked[
                1:
            ]
        )

        return (
            best[2],
            confidence,
            alternatives,
        )
