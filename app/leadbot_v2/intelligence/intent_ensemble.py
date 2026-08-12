

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


class IntentEnsemble:
    def assess(
        self,
        evidence: list[IntentEvidence],
    ) -> IntentAssessment:
        result = IntentAssessment(evidence=list(evidence))

        scores: dict[IntentLabel, float] = {}

        for item in evidence:
            current = scores.get(item.label, 0.0)

            # Multiple independent pieces of evidence increase confidence,
            # but never beyond 1.0.
            contribution = item.confidence * item.polarity
            scores[item.label] = max(
                0.0,
                min(1.0, current + contribution * (1.0 - current)),
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

        # Detect strong disagreement instead of silently choosing a side.
        if buyer >= 0.70 and seller >= 0.70:
            result.contradiction = True
            result.contradiction_reason = (
                f"strong buyer evidence ({buyer:.2f}) conflicts with "
                f"strong seller evidence ({seller:.2f})"
            )

        # Ambiguity is highest when buyer/seller evidence is weak or similar.
        separation = abs(buyer - seller)
        evidence_strength = max(buyer, seller)

        result.ambiguity = max(
            0.0,
            min(
                1.0,
                1.0 - (0.65 * separation + 0.35 * evidence_strength),
            ),
        )

        if result.contradiction:
            result.final_label = IntentLabel.UNKNOWN
            result.decision_confidence = min(buyer, seller)
            return result

        if buyer > seller and buyer >= 0.60:
            buyer_scores = {
                label: scores.get(label, 0.0)
                for label in BUYER_LABELS
            }
            result.final_label = max(
                buyer_scores,
                key=buyer_scores.get,
            )
            result.decision_confidence = buyer
            return result

        if seller > buyer and seller >= 0.60:
            seller_scores = {
                label: scores.get(label, 0.0)
                for label in SELLER_LABELS
            }
            result.final_label = max(
                seller_scores,
                key=seller_scores.get,
            )
            result.decision_confidence = seller
            return result

        # Non-buyer informational classes can still win explicitly.
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
        result.decision_confidence = max(scores.values(), default=0.0)

        return result
