from __future__ import annotations

from dataclasses import replace

from .models import (
    BrandRisk,
    PublicationPolicyError,
    PublicationState,
)


class PublicationPolicy:
    def __init__(
        self,
        *,
        require_human_approval: bool = True,
    ) -> None:
        self.require_human_approval = bool(
            require_human_approval
        )

    def ready_for_review(
        self,
        proposal,
    ):
        if not proposal.content_hash:
            raise PublicationPolicyError(
                "content hash required"
            )

        if (
            proposal.claims
            and not proposal.evidence_refs
        ):
            raise PublicationPolicyError(
                "material claims require evidence references"
            )

        return replace(
            proposal,
            state=(
                PublicationState
                .READY_FOR_REVIEW
            ),
        )

    def approve(
        self,
        proposal,
        *,
        approver: str,
    ):
        if not approver.strip():
            raise PublicationPolicyError(
                "approver required"
            )

        if (
            proposal.state
            is not PublicationState
            .READY_FOR_REVIEW
        ):
            raise PublicationPolicyError(
                "proposal is not ready for review"
            )

        return replace(
            proposal,
            state=(
                PublicationState.APPROVED
            ),
            approved_by=(
                approver
            ),
        )

    def can_publish(
        self,
        proposal,
    ) -> bool:
        if (
            self.require_human_approval
            and proposal.state
            is not PublicationState.APPROVED
        ):
            return False

        if (
            proposal.brand_risk
            is BrandRisk.CRITICAL
        ):
            return False

        return True
