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

    # Explicit acquisition / hiring intent.
    # These expressions distinguish a customer hiring a contractor from
    # a contractor advertising services.
    RuleSpec(
        IntentLabel.HOMEOWNER_READY_BUYER,
        r"\b(?:i|we)\s+(?:want|need|would like)\s+to\s+hire\s+(?:another\s+|a\s+)?(?:professional\s+)?(?:concrete\s+)?contractor\b",
        0.98,
    ),
    RuleSpec(
        IntentLabel.HOMEOWNER_READY_BUYER,
        r"\b(?:i(?:'m| am)|we(?:'re| are))\s+(?:still\s+)?looking\s+to\s+hire\s+(?:another\s+|a\s+)?(?:concrete\s+)?contractor\b",
        0.97,
    ),
    RuleSpec(
        IntentLabel.HOMEOWNER_READY_BUYER,
        r"\b(?:i|we)\s+(?:still\s+)?need\s+(?:my|our|the)\b.{0,80}\b(?:driveway|patio|slab|sidewalk|foundation|concrete)\b.{0,80}\b(?:replaced|poured|installed|repaired|demolished|formed|finished)\b",
        0.97,
    ),
    RuleSpec(
        IntentLabel.HOMEOWNER_READY_BUYER,
        r"\bneed\s+(?:someone\s+to\s+)?(?:demo|demolish|replace|pour|form|finish|install)\b.{0,80}\b(?:driveway|patio|slab|sidewalk|foundation|concrete)\b",
        0.96,
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
        r"\b(?:call us today|contact us today|licensed and insured)\b",
        0.96,
    ),

    # High-precision contractor / seller fingerprints.
    # These intentionally require business-side language rather than
    # generic mentions of contractors.
    RuleSpec(
        IntentLabel.CONTRACTOR_AD,
        r"\bwe\s+(?:also\s+)?(?:provide|offer|install|serve|specialize(?:\s+in)?)\b",
        0.97,
    ),
    RuleSpec(
        IntentLabel.CONTRACTOR_AD,
        r"\bwe\s+are\s+(?:a\s+|an\s+)?(?:professional\s+)?(?:concrete\s+)?contractors?\b",
        0.98,
    ),
    RuleSpec(
        IntentLabel.CONTRACTOR_AD,
        r"\b(?:call\s+(?:us\s+)?today|contact\s+(?:us\s+)?today)\b",
        0.98,
    ),
    RuleSpec(
        IntentLabel.CONTRACTOR_AD,
        r"\b(?:professional\s+concrete\s+contractors?|concrete\s+services|serving\s+(?:dfw|dallas|fort worth|north texas))\b",
        0.96,
    ),

    # Non-buyer informational intent
    RuleSpec(
        IntentLabel.DIY_INFORMATION,
        r"\b(?:how do i|can i pour|what mix|how thick|how much rebar)\b",
        0.90,
    ),

    # Explicit negation of a construction scope is stronger than
    # generic phrases such as "need someone".
    RuleSpec(
        IntentLabel.NON_CONCRETE,
        r"\bno\s+(?:concrete\s+)?(?:construction|replacement|repair|pouring|installation)(?:\s+or\s+(?:concrete\s+)?(?:construction|replacement|repair|pouring|installation))*\s+(?:needed|required|wanted)\b",
        0.99,
    ),
    RuleSpec(
        IntentLabel.NON_CONCRETE,
        r"\b(?:not\s+looking\s+for|do(?:es)?\s+not\s+need|don't\s+need|do\s+not\s+need)\s+(?:any\s+)?(?:concrete\s+)?(?:work|construction|replacement|repair|contractor)\b",
        0.99,
    ),

    # Cleanup language expressed as verbs, not only nouns such as
    # "trash removal".
    RuleSpec(
        IntentLabel.CLEANUP_ONLY,
        r"\b(?:remove|removing|haul|haul\s+away|pick\s+up|pickup|clean\s+up|clear)\s+(?:the\s+)?(?:trash|junk|debris|bags?)\b",
        0.97,
    ),
    RuleSpec(
        IntentLabel.CLEANUP_ONLY,
        r"\b(?:trash|junk|debris|bags?)\s+(?:removal|pickup|cleaning|cleanup)\b",
        0.97,
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
