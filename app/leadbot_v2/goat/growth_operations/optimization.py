from __future__ import annotations

from leadbot_v2.goat.growth_intelligence import (
    stable_hash,
)

from .models import (
    OptimizationKind,
    OptimizationProposal,
)


class GrowthOptimizationEngine:
    def propose_from_seo(
        self,
        audit,
    ):
        if audit.score >= 90:
            return None

        severity = max(
            (
                finding.score_impact
                for finding
                in audit.findings
            ),
            default=0.0,
        )

        expected_value = min(
            1.0,
            (
                100.0
                - audit.score
            )
            / 100.0,
        )

        confidence = min(
            0.98,
            0.65
            + len(
                audit.findings
            )
            * 0.03,
        )

        proposal_id = stable_hash(
            {
                "kind": "seo_fix",
                "page_id": audit.page_id,
                "score": audit.score,
                "findings": tuple(
                    finding.finding_id
                    for finding
                    in audit.findings
                ),
            }
        )[:24]

        return OptimizationProposal(
            proposal_id=proposal_id,
            kind=(
                OptimizationKind.SEO_FIX
            ),
            title=(
                f"Improve SEO health for "
                f"{audit.page_id}"
            ),
            expected_value=(
                expected_value
            ),
            confidence=confidence,
            risk=min(
                1.0,
                severity / 20.0,
            ),
            requires_human_approval=True,
            evidence_refs=tuple(
                finding.finding_id
                for finding
                in audit.findings
            ),
            reason=(
                "technical SEO findings indicate "
                "measurable optimization opportunity"
            ),
        )

    def propose_from_economics(
        self,
        economics,
    ):
        contribution_roas = (
            economics.contribution_roas
        )

        if (
            contribution_roas is None
            or contribution_roas >= 1.5
        ):
            return None

        expected_value = min(
            1.0,
            max(
                0.0,
                1.5
                - contribution_roas,
            )
            / 1.5,
        )

        proposal_id = stable_hash(
            {
                "kind": "campaign",
                "campaign_id":
                    economics.campaign_id,
                "contribution_roas":
                    contribution_roas,
            }
        )[:24]

        return OptimizationProposal(
            proposal_id=proposal_id,
            kind=(
                OptimizationKind.CAMPAIGN
            ),
            title=(
                f"Correct campaign economics: "
                f"{economics.campaign_id}"
            ),
            expected_value=(
                expected_value
            ),
            confidence=0.92,
            risk=0.60,
            requires_human_approval=True,
            evidence_refs=(
                economics.campaign_id,
            ),
            reason=(
                "contribution-adjusted return is "
                "below configured growth threshold"
            ),
        )
