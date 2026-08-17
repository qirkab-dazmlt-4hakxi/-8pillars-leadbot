from __future__ import annotations

from .models import (
    BrandRisk,
    ReputationFinding,
)


POSITIVE = {
    "excellent",
    "great",
    "professional",
    "quality",
    "recommend",
    "recommended",
    "responsive",
    "reliable",
    "impressive",
    "clean",
    "fast",
    "honest",
}

NEGATIVE = {
    "bad",
    "poor",
    "terrible",
    "fraud",
    "scam",
    "late",
    "unsafe",
    "lawsuit",
    "complaint",
    "unprofessional",
    "damage",
    "failed",
    "failure",
    "problem",
}

HIGH_RISK = {
    "fraud",
    "scam",
    "unsafe",
    "lawsuit",
    "criminal",
    "injury",
    "fatality",
}


class ReputationMonitor:
    def __init__(
        self,
        *,
        authorized_subjects,
    ) -> None:
        self.authorized_subjects = {
            subject.strip().lower()
            for subject
            in authorized_subjects
            if subject.strip()
        }

    def evaluate(
        self,
        mention,
    ) -> ReputationFinding:
        if not mention.is_public:
            raise ValueError(
                "reputation monitoring requires public-source material"
            )

        if (
            mention.subject
            .strip()
            .lower()
            not in self.authorized_subjects
        ):
            raise ValueError(
                "subject not authorized for reputation monitoring"
            )

        words = {
            token.strip(
                ".,!?;:\"'()[]{}"
            ).lower()
            for token
            in (
                mention.title
                + " "
                + mention.text
            ).split()
        }

        positive_hits = (
            words
            & POSITIVE
        )

        negative_hits = (
            words
            & NEGATIVE
        )

        high_hits = (
            words
            & HIGH_RISK
        )

        denominator = max(
            1,
            len(
                positive_hits
            )
            + len(
                negative_hits
            ),
        )

        sentiment = (
            len(
                positive_hits
            )
            - len(
                negative_hits
            )
        ) / denominator

        if high_hits:
            risk = (
                BrandRisk.HIGH
            )

        elif (
            len(
                negative_hits
            )
            >= 3
        ):
            risk = (
                BrandRisk.MODERATE
            )

        else:
            risk = (
                BrandRisk.LOW
            )

        return ReputationFinding(
            mention_id=(
                mention.mention_id
            ),
            sentiment_score=(
                max(
                    -1.0,
                    min(
                        1.0,
                        sentiment,
                    ),
                )
            ),
            risk=risk,
            issue_terms=tuple(
                sorted(
                    negative_hits
                )
            ),
            response_required=(
                risk
                in {
                    BrandRisk.MODERATE,
                    BrandRisk.HIGH,
                    BrandRisk.CRITICAL,
                }
            ),
            reason=(
                "public mention evaluated for "
                "brand/reputation risk"
            ),
        )
