from __future__ import annotations

from .canonical import (
    normalize_text,
)

from .models import (
    ActorType,
    Hypothesis,
    LeadCandidate,
    ProjectType,
    clamp01,
)


CONCRETE_TERMS = {
    "concrete": 0.30,
    "cement": 0.12,
    "driveway": 0.32,
    "patio": 0.24,
    "foundation": 0.32,
    "slab": 0.28,
    "sidewalk": 0.23,
    "pool deck": 0.28,
    "flatwork": 0.32,
    "retaining wall": 0.20,
    "footing": 0.25,
    "pour": 0.20,
    "stamped concrete": 0.35,
    "concrete repair": 0.35,
}

BUYING_TERMS = {
    "need": 0.12,
    "looking for": 0.19,
    "recommend": 0.09,
    "estimate": 0.18,
    "quote": 0.18,
    "how much": 0.15,
    "replace": 0.12,
    "repair": 0.11,
    "contractor": 0.06,
    "someone to": 0.10,
}

URGENCY_TERMS = {
    "asap": 0.42,
    "urgent": 0.45,
    "today": 0.45,
    "tomorrow": 0.40,
    "this week": 0.30,
    "next week": 0.20,
    "soon": 0.17,
    "ready now": 0.35,
}

COMPETITOR_TERMS = {
    "we offer": 0.28,
    "our services": 0.28,
    "licensed contractor": 0.22,
    "free estimates": 0.20,
    "call us": 0.18,
    "serving dfw": 0.18,
    "specializing in": 0.18,
}

SPAM_TERMS = {
    "crypto": 0.55,
    "casino": 0.55,
    "seo services": 0.48,
    "marketing agency": 0.36,
    "loan approval": 0.45,
    "investment opportunity": 0.32,
}

HOMEOWNER_TERMS = {
    "my house": 0.18,
    "my home": 0.18,
    "my driveway": 0.22,
    "my patio": 0.22,
    "our home": 0.16,
    "our driveway": 0.18,
    "need someone": 0.16,
    "looking for": 0.15,
}

CONTRACTOR_TERMS = {
    "general contractor": 0.25,
    "project manager": 0.20,
    "subcontractor": 0.25,
    "sub needed": 0.25,
    "bid package": 0.24,
    "plans attached": 0.18,
    "looking for concrete sub": 0.30,
}

PROJECT_TERMS = {
    ProjectType.DRIVEWAY: (
        "driveway",
        "drive way",
    ),
    ProjectType.PATIO: (
        "patio",
    ),
    ProjectType.FOUNDATION: (
        "foundation",
        "footing",
    ),
    ProjectType.SLAB: (
        "slab",
        "garage floor",
        "shop floor",
    ),
    ProjectType.SIDEWALK: (
        "sidewalk",
        "walkway",
    ),
    ProjectType.POOL_DECK: (
        "pool deck",
        "pool surround",
    ),
    ProjectType.RETAINING_WALL: (
        "retaining wall",
    ),
    ProjectType.STEPS: (
        "concrete steps",
        "concrete stairs",
    ),
    ProjectType.FLATWORK: (
        "flatwork",
    ),
    ProjectType.REPAIR: (
        "concrete repair",
        "cracked concrete",
        "spalling",
    ),
    ProjectType.DEMO_REPLACE: (
        "remove and replace",
        "tear out and replace",
        "demo and replace",
    ),
    ProjectType.SITE_CONCRETE: (
        "site concrete",
        "curb and gutter",
    ),
    ProjectType.COMMERCIAL_CONCRETE: (
        "commercial concrete",
        "tilt wall",
    ),
}


def weighted_terms(
    text: str,
    terms: dict[
        str,
        float,
    ],
) -> tuple[
    float,
    tuple[str, ...],
]:
    score = 0.0
    hits = []

    for phrase, weight in terms.items():
        if phrase in text:
            score += weight
            hits.append(
                phrase
            )

    return (
        clamp01(
            score
        ),
        tuple(
            hits
        ),
    )


class IntentHypothesisEngine:
    def concrete_intent(
        self,
        candidate: LeadCandidate,
    ) -> float:
        text = normalize_text(
            candidate.raw_text
        ).lower()

        concrete, _ = weighted_terms(
            text,
            CONCRETE_TERMS,
        )

        buying, _ = weighted_terms(
            text,
            BUYING_TERMS,
        )

        return clamp01(
            concrete * 0.74
            + buying * 0.26
        )

    def urgency(
        self,
        candidate: LeadCandidate,
    ) -> float:
        text = normalize_text(
            candidate.raw_text
        ).lower()

        score, _ = weighted_terms(
            text,
            URGENCY_TERMS,
        )

        return score

    def spam_probability(
        self,
        candidate: LeadCandidate,
    ) -> float:
        text = normalize_text(
            candidate.raw_text
        ).lower()

        score, _ = weighted_terms(
            text,
            SPAM_TERMS,
        )

        return score

    def actor_hypotheses(
        self,
        candidate: LeadCandidate,
    ) -> tuple[
        Hypothesis,
        ...
    ]:
        text = normalize_text(
            candidate.raw_text
        ).lower()

        homeowner_score, homeowner_hits = (
            weighted_terms(
                text,
                HOMEOWNER_TERMS,
            )
        )

        contractor_score, contractor_hits = (
            weighted_terms(
                text,
                CONTRACTOR_TERMS,
            )
        )

        competitor_score, competitor_hits = (
            weighted_terms(
                text,
                COMPETITOR_TERMS,
            )
        )

        if candidate.company:
            contractor_score = clamp01(
                contractor_score
                + 0.08
            )

        raw = {
            ActorType.HOMEOWNER:
                0.18
                + homeowner_score,
            ActorType.GENERAL_CONTRACTOR:
                0.10
                + contractor_score,
            ActorType.COMPETITOR:
                0.06
                + competitor_score,
        }

        total = sum(
            raw.values()
        ) or 1.0

        evidence = {
            ActorType.HOMEOWNER:
                homeowner_hits,
            ActorType.GENERAL_CONTRACTOR:
                contractor_hits,
            ActorType.COMPETITOR:
                competitor_hits,
        }

        hypotheses = [
            Hypothesis(
                label=actor.value,
                probability=(
                    value / total
                ),
                evidence=(
                    evidence[
                        actor
                    ]
                ),
            )
            for actor, value
            in raw.items()
        ]

        hypotheses.sort(
            key=lambda item:
                item.probability,
            reverse=True,
        )

        return tuple(
            hypotheses
        )

    def actor_type(
        self,
        candidate: LeadCandidate,
    ) -> ActorType:
        hypotheses = (
            self.actor_hypotheses(
                candidate
            )
        )

        if (
            not hypotheses
            or hypotheses[0]
            .probability
            < 0.38
        ):
            return ActorType.UNKNOWN

        return ActorType(
            hypotheses[
                0
            ].label
        )

    def project_hypotheses(
        self,
        candidate: LeadCandidate,
    ) -> tuple[
        Hypothesis,
        ...
    ]:
        text = normalize_text(
            candidate.raw_text
        ).lower()

        result = []

        for project_type, terms in (
            PROJECT_TERMS.items()
        ):
            hits = tuple(
                term
                for term in terms
                if term in text
            )

            if not hits:
                continue

            probability = clamp01(
                0.50
                + 0.15
                * len(
                    hits
                )
            )

            result.append(
                Hypothesis(
                    label=(
                        project_type.value
                    ),
                    probability=(
                        probability
                    ),
                    evidence=hits,
                )
            )

        if not result:
            return (
                Hypothesis(
                    label=(
                        ProjectType
                        .UNKNOWN
                        .value
                    ),
                    probability=1.0,
                ),
            )

        result.sort(
            key=lambda item: (
                item.probability,
                item.label,
            ),
            reverse=True,
        )

        return tuple(
            result
        )

    def project_type(
        self,
        candidate: LeadCandidate,
    ) -> ProjectType:
        return ProjectType(
            self.project_hypotheses(
                candidate
            )[0].label
        )
