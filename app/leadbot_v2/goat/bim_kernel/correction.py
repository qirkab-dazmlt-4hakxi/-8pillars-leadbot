from __future__ import annotations

from dataclasses import replace

from .canonical import stable_hash

from .geometry import (
    aabb_distance,
    translate,
)

from .models import (
    CorrectionAlternative,
    Vec3,
)


class ClashCorrectionEngine:
    """
    Deterministic correction-proposal engine.

    It NEVER silently mutates the live model.
    Every result remains a candidate requiring explicit acceptance,
    downstream clash checking, engineering re-analysis, and professional
    review where applicable.
    """

    @staticmethod
    def _translation_candidates(
        fixed,
        movable,
        clearance,
    ):
        a = fixed.bounds
        b = movable.bounds

        return (
            (
                "positive_x",
                Vec3(
                    (
                        a.maximum.x
                        - b.minimum.x
                        + clearance
                    ),
                    0.0,
                    0.0,
                ),
            ),
            (
                "negative_x",
                Vec3(
                    -(
                        b.maximum.x
                        - a.minimum.x
                        + clearance
                    ),
                    0.0,
                    0.0,
                ),
            ),
            (
                "positive_y",
                Vec3(
                    0.0,
                    (
                        a.maximum.y
                        - b.minimum.y
                        + clearance
                    ),
                    0.0,
                ),
            ),
            (
                "negative_y",
                Vec3(
                    0.0,
                    -(
                        b.maximum.y
                        - a.minimum.y
                        + clearance
                    ),
                    0.0,
                ),
            ),
            (
                "positive_z",
                Vec3(
                    0.0,
                    0.0,
                    (
                        a.maximum.z
                        - b.minimum.z
                        + clearance
                    ),
                ),
            ),
            (
                "negative_z",
                Vec3(
                    0.0,
                    0.0,
                    -(
                        b.maximum.z
                        - a.minimum.z
                        + clearance
                    ),
                ),
            ),
        )

    @staticmethod
    def _movement(delta):
        return (
            abs(delta.x)
            + abs(delta.y)
            + abs(delta.z)
        )

    def propose(
        self,
        *,
        clash,
        fixed,
        movable,
        minimum_clearance_ft=None,
        max_alternatives=4,
    ):
        clearance = (
            clash.required_clearance_ft
            if minimum_clearance_ft
            is None
            else max(
                clash.required_clearance_ft,
                minimum_clearance_ft,
            )
        )

        alternatives = []

        for (
            direction,
            delta,
        ) in self._translation_candidates(
            fixed,
            movable,
            clearance,
        ):
            proposed_bounds = translate(
                movable.bounds,
                delta,
            )

            resulting_clearance = (
                aabb_distance(
                    fixed.bounds,
                    proposed_bounds,
                )
            )

            movement = self._movement(
                delta
            )

            score = (
                1.0
                / (
                    1.0 + movement
                )
            )

            alternative_id = stable_hash(
                {
                    "clash_id":
                        clash.clash_id,
                    "element_id":
                        movable.element_id,
                    "direction":
                        direction,
                    "translation":
                        delta,
                    "clearance":
                        clearance,
                }
            )[:32]

            alternatives.append(
                CorrectionAlternative(
                    alternative_id=(
                        alternative_id
                    ),
                    clash_id=(
                        clash.clash_id
                    ),
                    element_id=(
                        movable.element_id
                    ),
                    translation=delta,
                    score=score,
                    rationale=(
                        f"translate {movable.element_id} "
                        f"{direction} to remove clash "
                        f"and preserve requested clearance"
                    ),
                    resulting_clearance_ft=(
                        resulting_clearance
                    ),
                    requires_reanalysis=True,
                    professional_review_required=True,
                )
            )

        alternatives.sort(
            key=lambda alternative: (
                -alternative.score,
                alternative.alternative_id,
            )
        )

        return tuple(
            alternatives[
                :max(
                    0,
                    int(
                        max_alternatives
                    ),
                )
            ]
        )

    def preview(
        self,
        element,
        alternative,
    ):
        if (
            alternative.element_id
            != element.element_id
        ):
            raise ValueError(
                "correction alternative "
                "targets different element"
            )

        return replace(
            element,
            bounds=translate(
                element.bounds,
                alternative.translation,
            ),
            metadata={
                **element.metadata,
                "goat_preview_correction":
                    alternative
                    .alternative_id,
            },
        )
