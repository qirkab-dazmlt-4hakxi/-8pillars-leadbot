from __future__ import annotations

import unittest

from leadbot_v2.goat.superintelligence import (
    AutonomyLevel,
    CognitiveKernel,
    ConsensusEngine,
    ExpertOpinion,
    RiskLevel,
)


class ConsensusSafetyRegressionTests(
    unittest.TestCase
):
    def test_high_risk_warning_is_not_discounted_out_of_consensus(
        self,
    ):
        opinions = (
            ExpertOpinion(
                expert_id="liquidity",
                answer="corrective_action",
                confidence=0.96,
                risk=RiskLevel.HIGH,
                reasoning_summary=(
                    "cash runway below 30 days"
                ),
            ),

            ExpertOpinion(
                expert_id="margin",
                answer="corrective_action",
                confidence=0.97,
                risk=RiskLevel.HIGH,
                reasoning_summary=(
                    "material margin erosion"
                ),
            ),

            ExpertOpinion(
                expert_id="controls",
                answer="continue",
                confidence=0.80,
                risk=RiskLevel.LOW,
                reasoning_summary=(
                    "controls backlog acceptable"
                ),
            ),
        )

        recommendation, confidence, alternatives = (
            ConsensusEngine().decide(
                opinions,
                weights={
                    "liquidity":
                        1.20,
                    "margin":
                        1.20,
                    "controls":
                        1.00,
                },
            )
        )

        self.assertEqual(
            recommendation,
            "corrective_action",
        )

        self.assertGreater(
            confidence,
            0.75,
        )

        self.assertIn(
            "continue",
            alternatives,
        )

    def test_risk_still_tightens_autonomy_after_consensus(
        self,
    ):
        kernel = CognitiveKernel()

        kernel.register_expert(
            expert_id="risk-a",
            domain="safety-regression",
            weight=1.2,
            handler=lambda context: {
                "answer":
                    "stop",
                "confidence":
                    0.96,
                "risk":
                    "high",
                "reasoning_summary":
                    "serious condition",
            },
        )

        kernel.register_expert(
            expert_id="risk-b",
            domain="safety-regression",
            weight=1.2,
            handler=lambda context: {
                "answer":
                    "stop",
                "confidence":
                    0.94,
                "risk":
                    "high",
                "reasoning_summary":
                    "independent confirmation",
            },
        )

        kernel.register_expert(
            expert_id="normal",
            domain="safety-regression",
            handler=lambda context: {
                "answer":
                    "continue",
                "confidence":
                    0.75,
                "risk":
                    "low",
                "reasoning_summary":
                    "minority opinion",
            },
        )

        decision = kernel.reason(
            domain="safety-regression",
            question=(
                "continue operation?"
            ),
            context={},
            evidence=(
                "evidence-a",
                "evidence-b",
            ),
            requested_autonomy=(
                AutonomyLevel
                .EXECUTE_BOUNDED
            ),
        )

        self.assertEqual(
            decision.recommendation,
            "stop",
        )

        self.assertTrue(
            decision
            .requires_human_approval
        )

        self.assertLessEqual(
            decision.autonomy_level,
            AutonomyLevel.PREPARE,
        )

    def test_single_high_confidence_expert_remains_deterministic(
        self,
    ):
        opinion = ExpertOpinion(
            expert_id="single",
            answer="hold",
            confidence=0.93,
            risk=RiskLevel.CRITICAL,
            reasoning_summary=(
                "critical but well-supported conclusion"
            ),
        )

        first = (
            ConsensusEngine()
            .decide(
                (
                    opinion,
                )
            )
        )

        second = (
            ConsensusEngine()
            .decide(
                (
                    opinion,
                )
            )
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            first[
                0
            ],
            "hold",
        )


if __name__ == "__main__":
    unittest.main()
