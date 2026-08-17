from __future__ import annotations

import time

from .calibration import (
    CalibrationMonitor,
)

from .canonical import (
    stable_hash,
)

from .consensus import (
    ConsensusEngine,
)

from .critic import (
    CriticNetwork,
)

from .evidence import (
    EvidenceLedger,
)

from .experts import (
    ExpertRegistry,
)

from .learning import (
    ExpertWeightLearner,
)

from .memory import (
    AdaptiveMemory,
)

from .models import (
    AutonomyLevel,
    Decision,
    Outcome,
    RiskLevel,
    clamp01,
    ensure_utc,
)

from .performance import (
    LatencyMonitor,
)

from .policy import (
    AutonomyPolicy,
)


class CognitiveKernel:
    def __init__(
        self,
        *,
        repository=None,
        autonomy_policy=None,
    ) -> None:
        self.repository = (
            repository
        )

        self.evidence = (
            EvidenceLedger()
        )

        self.memory = (
            AdaptiveMemory()
        )

        self.experts = (
            ExpertRegistry()
        )

        self.consensus = (
            ConsensusEngine()
        )

        self.critics = (
            CriticNetwork()
        )

        self.policy = (
            autonomy_policy
            or AutonomyPolicy()
        )

        self.calibration = (
            CalibrationMonitor()
        )

        self.learning = (
            ExpertWeightLearner()
        )

        self.latency = (
            LatencyMonitor()
        )

        self._decisions: dict[
            str,
            Decision,
        ] = {}

    def register_expert(
        self,
        *,
        expert_id: str,
        domain: str,
        handler,
        weight: float = 1.0,
    ) -> None:
        self.experts.register(
            expert_id=(
                expert_id
            ),
            domain=domain,
            handler=handler,
            weight=weight,
        )

    def reason(
        self,
        *,
        domain: str,
        question: str,
        context: dict,
        evidence=(),
        requested_autonomy: AutonomyLevel = (
            AutonomyLevel.RECOMMEND
        ),
        irreversible: bool = False,
        external_side_effect: bool = False,
        unknowns=(),
    ) -> Decision:
        started = (
            time.perf_counter_ns()
        )

        opinions = (
            self.experts
            .invoke_domain(
                domain,
                context,
            )
        )

        if not opinions:
            raise RuntimeError(
                f"no experts registered "
                f"for domain: {domain}"
            )

        weights = {
            spec.expert_id:
                spec.weight
                * self.learning.weight(
                    spec.expert_id
                )
            for spec
            in self.experts.specs(
                domain
            )
        }

        (
            recommendation,
            confidence,
            alternatives,
        ) = self.consensus.decide(
            opinions,
            weights=weights,
        )

        highest_risk = max(
            (
                opinion.risk
                for opinion
                in opinions
            ),
            key=_risk_rank,
        )

        critiques = (
            self.critics.run(
                {
                    "confidence":
                        confidence,
                    "evidence_count":
                        len(
                            tuple(
                                evidence
                            )
                        ),
                    "opinions":
                        opinions,
                    "question":
                        question,
                    "context":
                        context,
                }
            )
        )

        if any(
            critique.severity
            is RiskLevel.CRITICAL
            for critique
            in critiques
        ):
            highest_risk = (
                RiskLevel.CRITICAL
            )

        elif (
            any(
                critique.severity
                is RiskLevel.HIGH
                for critique
                in critiques
            )
            and _risk_rank(
                highest_risk
            )
            < _risk_rank(
                RiskLevel.HIGH
            )
        ):
            highest_risk = (
                RiskLevel.HIGH
            )

        (
            autonomy_level,
            human,
            policy_reasons,
        ) = self.policy.authorize(
            requested=(
                requested_autonomy
            ),
            risk=(
                highest_risk
            ),
            confidence=(
                confidence
            ),
            critiques=(
                critiques
            ),
            irreversible=(
                irreversible
            ),
            external_side_effect=(
                external_side_effect
            ),
        )

        decision_id = stable_hash(
            {
                "domain":
                    domain,
                "question":
                    question,
                "context":
                    context,
                "recommendation":
                    recommendation,
                "alternatives":
                    alternatives,
                "opinions":
                    tuple(
                        opinions
                    ),
            }
        )[:32]

        decision = Decision(
            decision_id=(
                decision_id
            ),
            recommendation=(
                recommendation
            ),
            confidence=clamp01(
                confidence
            ),
            risk=(
                highest_risk
            ),
            autonomy_level=(
                autonomy_level
            ),
            requires_human_approval=(
                human
            ),
            expert_opinions=(
                opinions
            ),
            critiques=(
                critiques
            ),
            alternatives=tuple(
                alternatives
            ),
            unknowns=tuple(
                unknowns
            ),
            metadata={
                "domain":
                    domain,
                "question":
                    question,
                "policy_reasons":
                    policy_reasons,
            },
        )

        self._decisions[
            decision_id
        ] = decision

        self.memory.remember(
            kind="decision",
            key=(
                f"{domain}:"
                f"{question}"
            ),
            value={
                "decision_id":
                    decision_id,
                "recommendation":
                    recommendation,
                "confidence":
                    confidence,
            },
            importance=0.85,
            confidence=(
                confidence
            ),
        )

        if (
            self.repository
            is not None
        ):
            self.repository.save_decision(
                decision
            )

        latency_ms = (
            time.perf_counter_ns()
            - started
        ) / 1_000_000.0

        self.latency.observe(
            "reason",
            latency_ms,
        )

        return decision

    def record_outcome(
        self,
        *,
        decision_id: str,
        success: bool,
        actual_value: float | None = None,
        expected_answer=None,
        observed_at=None,
        notes: str = "",
    ) -> Outcome:
        decision = (
            self._decisions[
                decision_id
            ]
        )

        outcome = Outcome(
            decision_id=(
                decision_id
            ),
            actual_value=(
                actual_value
            ),
            success=bool(
                success
            ),
            observed_at=(
                ensure_utc(
                    observed_at
                )
            ),
            notes=notes,
        )

        self.calibration.observe(
            decision.confidence,
            outcome.success,
        )

        self.learning.update(
            decision.expert_opinions,
            outcome,
            expected_answer=(
                expected_answer
            ),
        )

        self.memory.remember(
            kind="outcome",
            key=decision_id,
            value={
                "success":
                    outcome.success,
                "actual_value":
                    outcome
                    .actual_value,
                "notes":
                    outcome.notes,
            },
            importance=0.95,
            confidence=1.0,
            now=(
                outcome
                .observed_at
            ),
        )

        if (
            self.repository
            is not None
        ):
            self.repository.save_outcome(
                outcome
            )

        return outcome


def _risk_rank(
    risk: RiskLevel,
) -> int:
    return {
        RiskLevel.LOW:
            1,

        RiskLevel.MODERATE:
            2,

        RiskLevel.HIGH:
            3,

        RiskLevel.CRITICAL:
            4,
    }[
        risk
    ]
