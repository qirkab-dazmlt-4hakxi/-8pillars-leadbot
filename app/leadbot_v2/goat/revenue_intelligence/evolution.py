from __future__ import annotations

from .canonical import (
    stable_hash,
)

from .models import (
    LearningSignal,
    StrategyProposal,
    ensure_utc,
)


class StrategyEvolutionGovernor:
    """
    Generates bounded proposals.

    It does NOT edit production code, bypass approvals or silently
    promote strategies.
    """

    def propose(
        self,
        signal: LearningSignal,
        *,
        parameter: str,
        current_value: float,
        now=None,
    ) -> StrategyProposal | None:
        if signal.sample_size < 30:
            return None

        delta = (
            signal.posterior_mean
            - 0.50
        )

        if abs(
            delta
        ) < 0.08:
            return None

        max_change = 0.10

        proposed = (
            current_value
            + max(
                -max_change,
                min(
                    max_change,
                    delta * 0.20,
                ),
            )
        )

        proposed = max(
            0.05,
            min(
                0.95,
                proposed,
            ),
        )

        evidence_strength = (
            signal.sample_size
            / (
                signal.sample_size
                + 40.0
            )
        )

        confidence = min(
            0.99,
            evidence_strength
            * (
                1.0
                - 0.55
                * signal.drift_score
            ),
        )

        expected_uplift = abs(
            proposed
            - current_value
        )

        timestamp = ensure_utc(
            now
        )

        proposal_id = stable_hash(
            {
                "parameter":
                    parameter,
                "current":
                    current_value,
                "proposed":
                    proposed,
                "sample":
                    signal.sample_size,
                "posterior":
                    signal.posterior_mean,
                "drift":
                    signal.drift_score,
                "created_at":
                    timestamp,
            }
        )[:32]

        return StrategyProposal(
            proposal_id=proposal_id,
            parameter=parameter,
            current_value=(
                current_value
            ),
            proposed_value=(
                proposed
            ),
            confidence=confidence,
            expected_uplift=(
                expected_uplift
            ),
            sample_size=int(
                signal.sample_size
            ),
            shadow_required=True,
            canary_required=True,
            created_at=timestamp,
            reason=(
                "bounded champion/challenger "
                "proposal from posterior evidence"
            ),
        )
