from __future__ import annotations

import math
import re

from collections import (
    Counter,
    defaultdict,
)

from .models import (
    CostCodePrediction,
)


TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+"
)


def tokenize(
    *values,
):
    result = []

    for value in values:
        if not value:
            continue

        result.extend(
            token.lower()
            for token
            in TOKEN_RE.findall(
                str(
                    value
                )
            )
            if len(
                token
            ) >= 2
        )

    return tuple(
        result
    )


class AdaptiveCostCoder:
    """
    Multinomial Naive Bayes cost-code learner.

    Important control:
    only explicitly approved examples are learned.
    Model predictions never self-train automatically.
    """

    def __init__(
        self,
        *,
        minimum_examples: int = 3,
        auto_accept_threshold: float = 0.90,
    ) -> None:
        self.minimum_examples = int(
            minimum_examples
        )

        self.auto_accept_threshold = float(
            auto_accept_threshold
        )

        self._label_examples = Counter()

        self._token_counts = defaultdict(
            Counter
        )

        self._token_totals = Counter()

        self._vocabulary = set()

    @property
    def examples_seen(
        self,
    ) -> int:
        return sum(
            self._label_examples.values()
        )

    def learn_approved(
        self,
        *,
        description: str,
        merchant_name: str | None,
        cost_code: str,
    ) -> None:
        if not cost_code.strip():
            raise ValueError(
                "cost_code required"
            )

        tokens = tokenize(
            description,
            merchant_name,
        )

        if not tokens:
            raise ValueError(
                "approved example requires tokens"
            )

        self._label_examples[
            cost_code
        ] += 1

        for token in tokens:
            self._token_counts[
                cost_code
            ][
                token
            ] += 1

            self._token_totals[
                cost_code
            ] += 1

            self._vocabulary.add(
                token
            )

    def predict(
        self,
        *,
        description: str,
        merchant_name: str | None = None,
    ) -> CostCodePrediction:
        tokens = tokenize(
            description,
            merchant_name,
        )

        if (
            self.examples_seen
            < self.minimum_examples
            or not self._label_examples
        ):
            return CostCodePrediction(
                label=None,
                confidence=0.0,
                examples_seen=(
                    self.examples_seen
                ),
                evidence_tokens=(
                    tokens
                ),
                review_required=True,
            )

        total_examples = float(
            self.examples_seen
        )

        vocabulary_size = max(
            1,
            len(
                self._vocabulary
            ),
        )

        scores = {}

        for (
            label,
            examples,
        ) in (
            self._label_examples.items()
        ):
            log_probability = math.log(
                examples
                / total_examples
            )

            denominator = (
                self._token_totals[
                    label
                ]
                + vocabulary_size
            )

            for token in tokens:
                numerator = (
                    self._token_counts[
                        label
                    ][
                        token
                    ]
                    + 1
                )

                log_probability += (
                    math.log(
                        numerator
                        / denominator
                    )
                )

            scores[
                label
            ] = log_probability

        maximum = max(
            scores.values()
        )

        exp_scores = {
            label:
                math.exp(
                    score
                    - maximum
                )
            for label, score
            in scores.items()
        }

        denominator = sum(
            exp_scores.values()
        )

        probabilities = {
            label:
                value
                / denominator
            for label, value
            in exp_scores.items()
        }

        label = max(
            probabilities,
            key=lambda candidate: (
                probabilities[
                    candidate
                ],
                candidate,
            ),
        )

        confidence = (
            probabilities[
                label
            ]
        )

        return CostCodePrediction(
            label=label,
            confidence=(
                confidence
            ),
            examples_seen=(
                self.examples_seen
            ),
            evidence_tokens=(
                tokens
            ),
            review_required=(
                confidence
                < self.auto_accept_threshold
            ),
        )
