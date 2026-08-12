from __future__ import annotations

from dataclasses import dataclass, field

from leadbot_v2.core import EvidenceType, LeadIntelligenceRecord


@dataclass
class EvidenceSummary:
    buyer_intent: float = 0.0
    concrete_scope: float = 0.0
    location: float = 0.0
    contact: float = 0.0
    urgency: float = 0.0
    freshness: float = 0.0
    negatives: float = 0.0
    reasons: list[str] = field(default_factory=list)


class EvidenceEngine:
    def summarize(
        self,
        lead: LeadIntelligenceRecord,
    ) -> EvidenceSummary:
        summary = EvidenceSummary()

        for item in lead.evidence:
            if item.kind == EvidenceType.BUYER_INTENT:
                summary.buyer_intent = max(
                    summary.buyer_intent,
                    item.confidence,
                )

            elif item.kind == EvidenceType.CONCRETE_SCOPE:
                summary.concrete_scope = max(
                    summary.concrete_scope,
                    item.confidence,
                )

            elif item.kind == EvidenceType.LOCATION:
                summary.location = max(
                    summary.location,
                    item.confidence,
                )

            elif item.kind == EvidenceType.CONTACT:
                summary.contact = max(
                    summary.contact,
                    item.confidence,
                )

            elif item.kind == EvidenceType.URGENCY:
                summary.urgency = max(
                    summary.urgency,
                    item.confidence,
                )

            elif item.kind == EvidenceType.FRESHNESS:
                summary.freshness = max(
                    summary.freshness,
                    item.confidence,
                )

            elif item.kind == EvidenceType.NEGATIVE:
                summary.negatives = max(
                    summary.negatives,
                    item.confidence,
                )

        return summary


    def qualify(
        self,
        lead: LeadIntelligenceRecord,
    ) -> bool:
        summary = self.summarize(lead)

        lead.scores.buyer_intent = summary.buyer_intent
        lead.scores.concrete_scope = summary.concrete_scope
        lead.scores.location = summary.location
        lead.scores.contactability = summary.contact
        lead.scores.urgency = summary.urgency
        lead.scores.freshness = summary.freshness

        failures = []

        if summary.buyer_intent < 0.70:
            failures.append("buyer intent not proven")

        if summary.concrete_scope < 0.70:
            failures.append("concrete scope not proven")

        if summary.location < 0.70:
            failures.append("target location not proven")

        if summary.contact < 0.70:
            failures.append("actionable contact not proven")

        if summary.negatives >= 0.80:
            failures.append("strong negative/seller evidence")

        if failures:
            lead.rejection_reason = "; ".join(failures)
            lead.qualification_reason = None
            return False

        lead.rejection_reason = None
        lead.qualification_reason = (
            "verified buyer + concrete scope + actionable contact"
        )

        return True
