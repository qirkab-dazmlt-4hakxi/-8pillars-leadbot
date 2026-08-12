from __future__ import annotations

from dataclasses import dataclass

from leadbot_v2.intelligence.intent_context import ContextIntentLayer
from leadbot_v2.intelligence.intent_ensemble import (
    IntentAssessment,
    IntentEnsemble,
)
from leadbot_v2.intelligence.intent_rules import DeterministicIntentLayer


@dataclass
class FusionResult:
    assessment: IntentAssessment
    quarantined: bool
    reason: str


class IntentFusionEngine:
    def __init__(self) -> None:
        self.rules = DeterministicIntentLayer()
        self.context = ContextIntentLayer()
        self.ensemble = IntentEnsemble()

    def analyze(self, text: str) -> FusionResult:
        evidence = []

        evidence.extend(self.rules.evaluate(text))
        evidence.extend(self.context.evaluate(text))

        assessment = self.ensemble.assess(evidence)

        if assessment.contradiction:
            return FusionResult(
                assessment=assessment,
                quarantined=True,
                reason=(
                    assessment.contradiction_reason
                    or "intent contradiction detected"
                ),
            )

        if assessment.ambiguity >= 0.70:
            return FusionResult(
                assessment=assessment,
                quarantined=True,
                reason="intent confidence too ambiguous",
            )

        return FusionResult(
            assessment=assessment,
            quarantined=False,
            reason="intent evidence resolved",
        )
