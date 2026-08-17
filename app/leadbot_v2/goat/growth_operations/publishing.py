from __future__ import annotations

from .models import (
    AdapterCapability,
    ExternalPublicationState,
    PublicationExecutionError,
    PublicationReceipt,
)


class PublicationExecutor:
    def __init__(
        self,
        *,
        registry,
        growth_system,
    ) -> None:
        self.registry = registry
        self.growth_system = growth_system

    def execute(
        self,
        *,
        proposal,
        request,
        capability,
    ):
        if capability not in {
            AdapterCapability.CONTENT_PUBLISH,
            AdapterCapability.SOCIAL_PUBLISH,
        }:
            raise PublicationExecutionError(
                "invalid publishing capability"
            )

        if (
            proposal.proposal_id
            != request.proposal_id
        ):
            raise PublicationExecutionError(
                "proposal/request mismatch"
            )

        if (
            proposal.content_hash
            != request.content_hash
        ):
            raise PublicationExecutionError(
                "content hash mismatch"
            )

        if not (
            self.growth_system
            .publication
            .can_publish(
                proposal
            )
        ):
            return PublicationReceipt(
                request_id=request.request_id,
                adapter_name=request.adapter_name,
                external_id=None,
                state=(
                    ExternalPublicationState
                    .BLOCKED
                ),
                executed_at=None,
                message=(
                    "publication blocked by GOAT "
                    "approval/brand-risk policy"
                ),
            )

        return self.registry.publish(
            request=request,
            capability=capability,
        )
