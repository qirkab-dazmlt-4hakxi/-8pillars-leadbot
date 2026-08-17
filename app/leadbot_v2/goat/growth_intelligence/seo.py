from __future__ import annotations

from .models import (
    BrandRisk,
    KeywordOpportunity,
    SEOAudit,
    SEOFinding,
    SearchIntent,
)


INTENT_WEIGHT = {
    SearchIntent.INFORMATIONAL:
        0.45,

    SearchIntent.COMMERCIAL:
        0.75,

    SearchIntent.TRANSACTIONAL:
        1.00,

    SearchIntent.NAVIGATIONAL:
        0.50,

    SearchIntent.LOCAL:
        0.95,
}


class TechnicalSEOAuditor:
    def audit(
        self,
        page,
    ) -> SEOAudit:
        findings = []

        def add(
            finding_id,
            severity,
            message,
            impact,
        ):
            findings.append(
                SEOFinding(
                    finding_id=(
                        finding_id
                    ),
                    severity=severity,
                    page_id=(
                        page.page_id
                    ),
                    message=message,
                    score_impact=float(
                        impact
                    ),
                )
            )

        if not page.url.lower().startswith(
            "https://"
        ):
            add(
                "https",
                BrandRisk.HIGH,
                "page is not HTTPS",
                12,
            )

        if page.response_status != 200:
            add(
                "status",
                BrandRisk.HIGH,
                f"page returned HTTP "
                f"{page.response_status}",
                20,
            )

        title_length = len(
            page.title.strip()
        )

        if title_length < 20:
            add(
                "title-short",
                BrandRisk.MODERATE,
                "title is unusually short",
                5,
            )

        elif title_length > 65:
            add(
                "title-long",
                BrandRisk.MODERATE,
                "title may truncate in search results",
                4,
            )

        meta_length = len(
            page.meta_description.strip()
        )

        if meta_length < 70:
            add(
                "meta-short",
                BrandRisk.LOW,
                "meta description is thin",
                3,
            )

        elif meta_length > 170:
            add(
                "meta-long",
                BrandRisk.LOW,
                "meta description may truncate",
                2,
            )

        if not page.canonical_url:
            add(
                "canonical",
                BrandRisk.MODERATE,
                "canonical URL missing",
                5,
            )

        if page.h1_count != 1:
            add(
                "h1",
                BrandRisk.MODERATE,
                "page should have one clear primary H1",
                5,
            )

        if not page.indexable:
            add(
                "indexability",
                BrandRisk.HIGH,
                "page is not indexable",
                20,
            )

        if page.word_count < 300:
            add(
                "thin-content",
                BrandRisk.MODERATE,
                "page has limited substantive text",
                7,
            )

        if page.internal_link_count < 2:
            add(
                "internal-links",
                BrandRisk.LOW,
                "page has weak internal linking",
                3,
            )

        if page.images_without_alt > 0:
            add(
                "image-alt",
                BrandRisk.MODERATE,
                (
                    f"{page.images_without_alt} image(s) "
                    f"lack alternative text"
                ),
                min(
                    8,
                    page.images_without_alt
                    * 2,
                ),
            )

        if page.load_time_ms > 2500:
            add(
                "performance",
                BrandRisk.MODERATE,
                "page load time exceeds configured target",
                8,
            )

        score = max(
            0.0,
            100.0
            - sum(
                finding.score_impact
                for finding
                in findings
            ),
        )

        return SEOAudit(
            page_id=(
                page.page_id
            ),
            score=score,
            findings=tuple(
                findings
            ),
        )


class KeywordOpportunityEngine:
    def score(
        self,
        *,
        keyword: str,
        intent: SearchIntent,
        estimated_demand: float,
        business_value: float,
        competition: float,
        current_visibility: float,
        local_relevance: float,
    ) -> KeywordOpportunity:
        demand = _clamp(
            estimated_demand
        )

        value = _clamp(
            business_value
        )

        competition = _clamp(
            competition
        )

        visibility = _clamp(
            current_visibility
        )

        local = _clamp(
            local_relevance
        )

        intent_value = (
            INTENT_WEIGHT[
                intent
            ]
        )

        opportunity_gap = (
            1.0
            - visibility
        )

        competition_advantage = (
            1.0
            - competition
        )

        score = (
            demand
            * 0.20
            + value
            * 0.25
            + intent_value
            * 0.20
            + local
            * 0.15
            + opportunity_gap
            * 0.10
            + competition_advantage
            * 0.10
        )

        return KeywordOpportunity(
            keyword=keyword,
            intent=intent,
            estimated_demand=demand,
            business_value=value,
            competition=competition,
            current_visibility=visibility,
            local_relevance=local,
            score=_clamp(
                score
            ),
        )

    def rank(
        self,
        opportunities,
    ):
        return tuple(
            sorted(
                opportunities,
                key=lambda item: (
                    item.score,
                    item.keyword,
                ),
                reverse=True,
            )
        )


def _clamp(
    value,
):
    return max(
        0.0,
        min(
            1.0,
            float(
                value
            ),
        ),
    )
