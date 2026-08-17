from __future__ import annotations

from leadbot_v2.goat.growth_intelligence import (
    PublicMention,
)


class ReviewReputationBridge:
    def __init__(
        self,
        *,
        subject,
        growth_system,
    ) -> None:
        self.subject = subject
        self.growth_system = growth_system

    def handle(
        self,
        review,
    ):
        mention = PublicMention(
            mention_id=(
                f"{review.source}:"
                f"{review.review_id}"
            ),
            subject=self.subject,
            source_name=review.source,
            source_url=(
                review.public_url or ""
            ),
            published_at=(
                review.published_at
            ),
            title=(
                f"Public review "
                f"{review.rating}/5"
                if review.rating is not None
                else "Public review"
            ),
            text=review.text,
            is_public=True,
            metadata={
                "rating":
                    review.rating,
                "location_id":
                    review.location_id,
            },
        )

        return (
            self.growth_system
            .evaluate_reputation(
                mention
            )
        )
