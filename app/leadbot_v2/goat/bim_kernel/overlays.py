from __future__ import annotations

from .canonical import stable_hash

from .models import (
    EngineeringOverlay,
    EngineeringOverlayDisposition,
)


class EngineeringOverlayEngine:
    def utilization(
        self,
        *,
        element_id,
        metric,
        value,
        limit,
        source_analysis_id,
        source_fact_ids=(),
        review_threshold=0.90,
        professional_review_required=True,
    ):
        if limit <= 0:
            utilization = None

            disposition = (
                EngineeringOverlayDisposition.REVIEW
            )

        else:
            utilization = (
                value / limit
            )

            if utilization > 1.0:
                disposition = (
                    EngineeringOverlayDisposition.FAIL
                )

            elif (
                utilization
                >= review_threshold
            ):
                disposition = (
                    EngineeringOverlayDisposition.REVIEW
                )

            else:
                disposition = (
                    EngineeringOverlayDisposition.PASS
                )

        overlay_id = stable_hash(
            {
                "element_id":
                    element_id,
                "metric":
                    metric,
                "value":
                    value,
                "limit":
                    limit,
                "source_analysis_id":
                    source_analysis_id,
            }
        )[:32]

        return EngineeringOverlay(
            overlay_id=overlay_id,
            element_id=element_id,
            metric=metric,
            value=float(value),
            limit=float(limit),
            utilization=utilization,
            disposition=disposition,
            source_analysis_id=(
                source_analysis_id
            ),
            source_fact_ids=tuple(
                source_fact_ids
            ),
            professional_review_required=(
                professional_review_required
            ),
        )

    def release_allowed(
        self,
        overlays,
    ):
        return all(
            overlay.disposition
            is EngineeringOverlayDisposition.PASS
            and not overlay
            .professional_review_required
            for overlay
            in overlays
        )
