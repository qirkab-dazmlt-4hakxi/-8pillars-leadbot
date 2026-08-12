from __future__ import annotations

from dataclasses import dataclass
import re

from leadbot_v2.intelligence.intent_ensemble import (
    IntentEvidence,
    IntentLabel,
)


@dataclass(frozen=True)
class RuleSpec:
    label: IntentLabel
    pattern: str
    confidence: float
    polarity: int = 1


RULES = (
    # High-confidence homeowner acquisition intent
    RuleSpec(
        IntentLabel.HOMEOWNER_READY_BUYER,
        r"\blooking for (?:someone|a contractor|a concrete contractor)\b",
        0.94,
    ),
    RuleSpec(
        IntentLabel.HOMEOWNER_READY_BUYER,
        r"\bneed (?:someone|a contractor|a concrete contractor)\b",
        0.94,
    ),
    RuleSpec(
        IntentLabel.HOMEOWNER_READY_BUYER,
        r"\b(?:need|get|getting) (?:a |an )?(?:quote|estimate|bid)\b",
        0.91,
    ),

    # Recommendation intent
    RuleSpec(
        IntentLabel.RECOMMENDATION_REQUEST,
        r"\b(?:anyone|does anybody) know (?:a |any )?(?:good )?(?:concrete )?(?:guy|contractor|company)\b",
        0.93,
    ),
    RuleSpec(
        IntentLabel.RECOMMENDATION_REQUEST,
        r"\b(?:recommend|recommendation for) (?:a |any )?(?:concrete )?(?:contractor|company|crew)\b",
        0.92,
    ),

    # Commercial / subcontract acquisition
    RuleSpec(
        IntentLabel.SUBCONTRACT_REQUEST,
        r"\bconcrete (?:sub|subcontractor|crew) needed\b",
        0.97,
    ),
    RuleSpec(
        IntentLabel.GC_BID_REQUEST,
        r"\b(?:need|requesting|send) concrete (?:pricing|bid|proposal)\b",
        0.95,
    ),

    # Seller fingerprints
    RuleSpec(
        IntentLabel.CONTRACTOR_AD,
        r"\b(?:we|our company|our team) (?:provide|offer|specialize|install|serve)\b",
        0.94,
    ),
    RuleSpec(
        IntentLabel.CONTRACTOR_AD,
        r"\b(?:free estimate|call us today|contact us today|licensed and insured)\b",
        0.96,
    ),

    # Non-buyer informational intent
    RuleSpec(
        IntentLabel.DIY_INFORMATION,
        r"\b(?:how do i|can i pour|what mix|how thick|how much rebar)\b",
        0.90,
    ),

    # Cleanup-only work
    RuleSpec(
        IntentLabel.CLEANUP_ONLY,
        r"\b(?:junk removal|trash removal|haul away|yard cleanup)\b",
        0.96,
    ),
)


class DeterministicIntentLayer:
    name = "deterministic_rules"

    def evaluate(self, text: str) -> list[IntentEvidence]:
        evidence: list[IntentEvidence] = []

        for rule in RULES:
            for match in re.finditer(
                rule.pattern,
                text,
                flags=re.IGNORECASE,
            ):
                evidence.append(
                    IntentEvidence(
                        label=rule.label,
                        confidence=rule.confidence,
                        evidence_text=match.group(0),
                        source=self.name,
                        polarity=rule.polarity,
                    )
                )

        return evidence
