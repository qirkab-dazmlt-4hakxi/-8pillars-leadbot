from __future__ import annotations

from dataclasses import dataclass

from leadbot_v2.core.models import LeadIntelligenceRecord


@dataclass
class RankingResult:
    overall: float
    priority: str
    expected_value: float
    reasons: list[str]


class LeadRanker:
    def rank(
        self,
        lead: LeadIntelligenceRecord,
    ) -> RankingResult:
        s = lead.scores
        reasons: list[str] = []

        confidence = (
            s.buyer_intent * 0.24
            + s.concrete_scope * 0.24
            + s.location * 0.10
            + s.contactability * 0.16
            + s.freshness * 0.10
            + s.urgency * 0.08
            + s.source_trust * 0.08
        )

        value_low = lead.project.value_low or 0.0
        value_high = lead.project.value_high or value_low
        expected_value = (value_low + value_high) / 2.0

        value_boost = min(expected_value / 50000.0, 1.0) * 0.15

        overall = min(
            1.0,
            confidence * 0.85 + value_boost,
        )

        if s.buyer_intent >= 0.90:
            reasons.append("very strong buyer intent")

        if s.concrete_scope >= 0.90:
            reasons.append("very strong concrete scope")

        if s.contactability >= 0.90:
            reasons.append("high-confidence contact route")

        if s.urgency >= 0.80:
            reasons.append("high urgency")

        if expected_value >= 25000:
            reasons.append("high-value project")

        if overall >= 0.85:
            priority = "HOT"
        elif overall >= 0.70:
            priority = "WARM"
        else:
            priority = "COLD"

        lead.scores.overall = overall
        lead.scores.estimated_conversion = overall

        return RankingResult(
            overall=overall,
            priority=priority,
            expected_value=expected_value,
            reasons=reasons,
        )


def explain_rank(result: RankingResult) -> str:
    score = round(result.overall * 100)

    reasons = ", ".join(result.reasons) if result.reasons else "baseline signals"

    return (
        f"{result.priority} {score}/100 | "
        f"Expected value ${result.expected_value:,.0f} | "
        f"{reasons}"
    )
