from __future__ import annotations

from .canonical import (
    stable_hash,
)

from .models import (
    ContentBrief,
    SearchIntent,
)


class ContentPlanner:
    def create_brief(
        self,
        *,
        primary_keyword: str,
        intent: SearchIntent,
        market_name: str | None,
        services,
        questions,
        entities,
        conversion_goal: str,
    ) -> ContentBrief:
        services = tuple(
            dict.fromkeys(
                str(
                    item
                ).strip()
                for item
                in services
                if str(
                    item
                ).strip()
            )
        )

        questions = tuple(
            dict.fromkeys(
                str(
                    item
                ).strip()
                for item
                in questions
                if str(
                    item
                ).strip()
            )
        )

        entities = tuple(
            dict.fromkeys(
                str(
                    item
                ).strip()
                for item
                in entities
                if str(
                    item
                ).strip()
            )
        )

        title = primary_keyword.strip()

        if market_name:
            title = (
                f"{title} in "
                f"{market_name.strip()}"
            )

        sections = [
            "Scope and use cases",
            "How the work is planned",
            "Materials and engineering considerations",
            "Schedule and site constraints",
            "Quality-control approach",
            "Cost drivers",
            "Frequently asked questions",
            "Next step",
        ]

        if services:
            sections.insert(
                2,
                (
                    "Services: "
                    + ", ".join(
                        services[
                            :5
                        ]
                    )
                ),
            )

        brief_id = stable_hash(
            {
                "primary_keyword":
                    primary_keyword,
                "intent":
                    intent,
                "market_name":
                    market_name,
                "services":
                    services,
                "questions":
                    questions,
                "entities":
                    entities,
                "conversion_goal":
                    conversion_goal,
            }
        )[:24]

        return ContentBrief(
            brief_id=brief_id,
            primary_keyword=(
                primary_keyword
            ),
            intent=intent,
            title=title,
            target_questions=(
                questions
            ),
            required_entities=(
                entities
            ),
            recommended_sections=(
                tuple(
                    sections
                )
            ),
            conversion_goal=(
                conversion_goal
            ),
            minimum_evidence_items=max(
                2,
                min(
                    8,
                    len(
                        entities
                    ),
                ),
            ),
        )


class ContentQualityGuard:
    def evaluate(
        self,
        *,
        text: str,
        primary_keyword: str,
        evidence_refs,
    ):
        words = [
            word
            for word
            in text.lower().split()
            if word
        ]

        keyword_tokens = [
            token
            for token
            in primary_keyword
            .lower()
            .split()
            if token
        ]

        keyword_hits = sum(
            1
            for word
            in words
            if word
            in keyword_tokens
        )

        density = (
            keyword_hits
            / max(
                1,
                len(
                    words
                ),
            )
        )

        return {
            "word_count":
                len(
                    words
                ),

            "keyword_density":
                density,

            "keyword_stuffing_risk":
                density > 0.12,

            "evidence_count":
                len(
                    tuple(
                        evidence_refs
                    )
                ),

            "substantive":
                len(
                    words
                )
                >= 150,
        }
