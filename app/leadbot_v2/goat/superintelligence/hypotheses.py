from __future__ import annotations

import math

from .canonical import (
    stable_hash,
)

from .models import (
    Hypothesis,
    clamp01,
)


def _logit(
    p: float,
) -> float:
    p = min(
        1.0 - 1e-9,
        max(
            1e-9,
            p,
        ),
    )

    return math.log(
        p
        / (
            1.0
            - p
        )
    )


def _sigmoid(
    x: float,
) -> float:
    if x >= 0:
        z = math.exp(
            -x
        )

        return (
            1.0
            / (
                1.0
                + z
            )
        )

    z = math.exp(
        x
    )

    return (
        z
        / (
            1.0
            + z
        )
    )


class HypothesisEngine:
    def evaluate(
        self,
        *,
        statement: str,
        prior: float,
        supporting=(),
        opposing=(),
        assumptions=(),
    ) -> Hypothesis:
        prior = clamp01(
            prior
        )

        score = _logit(
            prior
        )

        support_ids = []
        oppose_ids = []

        for evidence in supporting:
            strength = (
                clamp01(
                    evidence.confidence
                )
                * clamp01(
                    evidence.authority
                )
            )

            score += (
                2.5
                * strength
            )

            support_ids.append(
                evidence.evidence_id
            )

        for evidence in opposing:
            strength = (
                clamp01(
                    evidence.confidence
                )
                * clamp01(
                    evidence.authority
                )
            )

            score -= (
                2.5
                * strength
            )

            oppose_ids.append(
                evidence.evidence_id
            )

        posterior = clamp01(
            _sigmoid(
                score
            )
        )

        hypothesis_id = stable_hash(
            {
                "statement":
                    statement,
                "prior":
                    prior,
                "supporting":
                    tuple(
                        sorted(
                            support_ids
                        )
                    ),
                "opposing":
                    tuple(
                        sorted(
                            oppose_ids
                        )
                    ),
                "assumptions":
                    tuple(
                        assumptions
                    ),
            }
        )[:32]

        return Hypothesis(
            hypothesis_id=(
                hypothesis_id
            ),
            statement=(
                statement
            ),
            prior=prior,
            posterior=(
                posterior
            ),
            supporting_evidence=(
                tuple(
                    support_ids
                )
            ),
            opposing_evidence=(
                tuple(
                    oppose_ids
                )
            ),
            assumptions=tuple(
                assumptions
            ),
        )

    def rank(
        self,
        hypotheses,
    ) -> tuple[
        Hypothesis,
        ...,
    ]:
        return tuple(
            sorted(
                hypotheses,
                key=lambda h: (
                    h.posterior,
                    h.hypothesis_id,
                ),
                reverse=True,
            )
        )
