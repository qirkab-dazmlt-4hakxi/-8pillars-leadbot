from __future__ import annotations

from dataclasses import dataclass

from .canonical import (
    normalize_postal,
    normalize_state,
    normalize_text,
)

from .models import (
    LeadCandidate,
)


@dataclass(frozen=True)
class GeographicAssessment:
    score: float
    reasons: tuple[str, ...]


class ServiceArea:
    def __init__(
        self,
        *,
        states=("TX",),
        cities=(),
        postal_prefixes=(),
    ) -> None:
        self.states = {
            normalize_state(
                value
            )
            for value in states
        }

        self.cities = {
            normalize_text(
                value
            ).lower()
            for value in cities
        }

        self.postal_prefixes = tuple(
            str(
                value
            )
            for value
            in postal_prefixes
        )

    def assess(
        self,
        candidate: LeadCandidate,
    ) -> GeographicAssessment:
        state = normalize_state(
            candidate.state
        )

        city = normalize_text(
            candidate.city
        ).lower()

        postal = normalize_postal(
            candidate.postal_code
        )

        reasons = []

        if (
            state
            and self.states
            and state
            not in self.states
        ):
            return GeographicAssessment(
                score=0.0,
                reasons=(
                    "state-outside-service-area",
                ),
            )

        if (
            postal
            and self.postal_prefixes
            and any(
                postal.startswith(
                    prefix
                )
                for prefix
                in self.postal_prefixes
            )
        ):
            reasons.append(
                "postal-service-match"
            )

            return GeographicAssessment(
                score=1.0,
                reasons=tuple(
                    reasons
                ),
            )

        if (
            city
            and self.cities
            and city in self.cities
        ):
            reasons.append(
                "city-service-match"
            )

            return GeographicAssessment(
                score=1.0,
                reasons=tuple(
                    reasons
                ),
            )

        if (
            state
            and state in self.states
        ):
            reasons.append(
                "state-service-match"
            )

            return GeographicAssessment(
                score=0.72,
                reasons=tuple(
                    reasons
                ),
            )

        return GeographicAssessment(
            score=0.35,
            reasons=(
                "geography-unconfirmed",
            ),
        )
