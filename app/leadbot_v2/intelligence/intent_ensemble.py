from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IntentLabel(str, Enum):
    HOMEOWNER_READY_BUYER = "homeowner_ready_buyer"
    HOMEOWNER_RESEARCHING = "homeowner_researching"
    RECOMMENDATION_REQUEST = "recommendation_request"

    COMMERCIAL_BUYER = "commercial_buyer"
    GC_BID_REQUEST = "gc_bid_request"
    SUBCONTRACT_REQUEST = "subcontract_request"
    PROPERTY_MANAGER_REQUEST = "property_manager_request"
    DEVELOPER_REQUEST = "developer_request"

    CONTRACTOR_AD = "contractor_ad"
    DIRECTORY = "directory"
    LEAD_RESELLER = "lead_reseller"
    MARKETING_CONTENT = "marketing_content"

    DIY_INFORMATION = "diy_information"
    CLEANUP_ONLY = "cleanup_only"
    DEMOLITION_ONLY = "demolition_only"
    NON_CONCRETE = "non_concrete"

    STALE_REQUEST = "stale_request"
    LOCATION_CONFLICT = "location_conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentEvidence:
    label: IntentLabel
    confidence: float
    evidence_text: str
    source: str
    polarity: int = 1


@dataclass
class IntentAssessment:
    labels: dict[IntentLabel, float] = field(default_factory=dict)
    evidence: list[IntentEvidence] = field(default_factory=list)

    buyer_probability: float = 0.0
    seller_probability: float = 0.0
    ambiguity: float = 1.0

    contradiction: bool = False
    contradiction_reason: str | None = None

    final_label: IntentLabel = IntentLabel.UNKNOWN
    decision_confidence: float = 0.0


BUYER_LABELS = {
    IntentLabel.HOMEOWNER_READY_BUYER,
    IntentLabel.HOMEOWNER_RESEARCHING,
    IntentLabel.RECOMMENDATION_REQUEST,
    IntentLabel.COMMERCIAL_BUYER,
    IntentLabel.GC_BID_REQUEST,
    IntentLabel.SUBCONTRACT_REQUEST,
    IntentLabel.PROPERTY_MANAGER_REQUEST,
    IntentLabel.DEVELOPER_REQUEST,
}

SELLER_LABELS = {
    IntentLabel.CONTRACTOR_AD,
    IntentLabel.DIRECTORY,
    IntentLabel.LEAD_RESELLER,
    IntentLabel.MARKETING_CONTENT,
}

BLOCKING_LABELS = {
    IntentLabel.CLEANUP_ONLY,
    IntentLabel.DIY_INFORMATION,
    IntentLabel.NON_CONCRETE,
    IntentLabel.STALE_REQUEST,
    IntentLabel.LOCATION_CONFLICT,
}


class IntentEnsemble:
    def assess(
        self,
        evidence: list[IntentEvidence],
    ) -> IntentAssessment:
        result = IntentAssessment(evidence=list(evidence))
        scores: dict[IntentLabel, float] = {}

        for item in evidence:
            current = scores.get(item.label, 0.0)

            contribution = item.confidence * item.polarity

            scores[item.label] = max(
                0.0,
                min(
                    1.0,
                    current + contribution * (1.0 - current),
                ),
            )

        result.labels = scores

        buyer = max(
            (scores.get(label, 0.0) for label in BUYER_LABELS),
            default=0.0,
        )

        seller = max(
            (scores.get(label, 0.0) for label in SELLER_LABELS),
            default=0.0,
        )

        result.buyer_probability = buyer
        result.seller_probability = seller

        blocking_scores = {
            label: scores.get(label, 0.0)
            for label in BLOCKING_LABELS
        }

        blocking_label = max(
            blocking_scores,
            key=blocking_scores.get,
        )

        blocking_score = blocking_scores[blocking_label]

        # Strong exclusion evidence overrides generic language such as
        # "need someone" when the actual scope is cleanup, DIY, stale,
        # non-concrete, or geographically invalid.
        if blocking_score >= 0.85:
            result.final_label = blocking_label
            result.decision_confidence = blocking_score
            result.ambiguity = 0.0
            return result

        if buyer >= 0.70 and seller >= 0.70:
            result.contradiction = True
            result.contradiction_reason = (
                f"strong buyer evidence ({buyer:.2f}) conflicts with "
                f"strong seller evidence ({seller:.2f})"
            )

        separation = abs(buyer - seller)
        strength = max(buyer, seller)

        result.ambiguity = max(
            0.0,
            min(
                1.0,
                1.0 - (0.65 * separation + 0.35 * strength),
            ),
        )

        if result.contradiction:
            result.final_label = IntentLabel.UNKNOWN
            result.decision_confidence = min(buyer, seller)
            return result

        if buyer > seller and buyer >= 0.60:
            candidates = {
                label: scores.get(label, 0.0)
                for label in BUYER_LABELS
            }

            result.final_label = max(
                candidates,
                key=candidates.get,
            )
            result.decision_confidence = buyer
            return result

        if seller > buyer and seller >= 0.60:
            candidates = {
                label: scores.get(label, 0.0)
                for label in SELLER_LABELS
            }

            result.final_label = max(
                candidates,
                key=candidates.get,
            )
            result.decision_confidence = seller
            return result

        other_scores = {
            label: score
            for label, score in scores.items()
            if label not in BUYER_LABELS
            and label not in SELLER_LABELS
        }

        if other_scores:
            label = max(other_scores, key=other_scores.get)
            score = other_scores[label]

            if score >= 0.70:
                result.final_label = label
                result.decision_confidence = score
                return result

        result.final_label = IntentLabel.UNKNOWN
        result.decision_confidence = max(
            scores.values(),
            default=0.0,
        )

        return result
