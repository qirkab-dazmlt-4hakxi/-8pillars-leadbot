from __future__ import annotations

from leadbot_v2.intelligence.intent_ensemble import (
    IntentEvidence,
    IntentLabel,
)


FIRST_PERSON = (
    "my driveway",
    "our driveway",
    "my patio",
    "our patio",
    "my property",
    "our property",
    "my backyard",
    "our backyard",
)

PROJECT_ACTIONS = (
    "replace",
    "replacement",
    "extend",
    "extension",
    "repair",
    "pour",
    "install",
    "demo",
    "demolish",
    "remove and replace",
    "add concrete",
)

LIFECYCLE = (
    "contractor backed out",
    "contractor ghosted",
    "need another contractor",
    "ready to pour",
    "ready for concrete",
    "forms are ready",
    "inspection passed",
    "permit approved",
    "ready to start",
)

SELLER_PRESSURE = (
    "free estimate",
    "call us today",
    "contact us today",
    "licensed and insured",
    "our services",
    "our crews",
    "we specialize",
    "we provide",
)

COMMERCIAL = (
    "general contractor",
    "project manager",
    "property manager",
    "developer",
    "bid package",
    "subcontractor",
    "scope of work",
    "send pricing",
)


class ContextIntentLayer:
    name = "context_reasoning"

    def evaluate(self, text: str) -> list[IntentEvidence]:
        t = text.lower()
        evidence: list[IntentEvidence] = []

        first = [x for x in FIRST_PERSON if x in t]
        actions = [x for x in PROJECT_ACTIONS if x in t]
        lifecycle = [x for x in LIFECYCLE if x in t]
        seller = [x for x in SELLER_PRESSURE if x in t]
        commercial = [x for x in COMMERCIAL if x in t]

        if first and actions:
            evidence.append(
                IntentEvidence(
                    label=IntentLabel.HOMEOWNER_READY_BUYER,
                    confidence=0.94,
                    evidence_text=f"{first[0]} + {actions[0]}",
                    source=self.name,
                )
            )

        if lifecycle:
            evidence.append(
                IntentEvidence(
                    label=IntentLabel.HOMEOWNER_READY_BUYER,
                    confidence=min(0.91 + 0.02 * len(lifecycle), 0.99),
                    evidence_text="lifecycle: " + ", ".join(lifecycle[:3]),
                    source=self.name,
                )
            )

        if commercial:
            evidence.append(
                IntentEvidence(
                    label=IntentLabel.COMMERCIAL_BUYER,
                    confidence=min(0.80 + 0.04 * len(commercial), 0.97),
                    evidence_text="commercial: " + ", ".join(commercial[:3]),
                    source=self.name,
                )
            )

        if len(seller) >= 2:
            evidence.append(
                IntentEvidence(
                    label=IntentLabel.CONTRACTOR_AD,
                    confidence=min(0.90 + 0.025 * len(seller), 0.99),
                    evidence_text="seller pressure: " + ", ".join(seller[:4]),
                    source=self.name,
                )
            )

        return evidence
