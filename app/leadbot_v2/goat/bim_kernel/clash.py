from __future__ import annotations

from .canonical import stable_hash

from .geometry import (
    aabb_distance,
    hard_intersects,
    overlap_depths,
    overlap_volume,
)

from .models import (
    Clash,
    ClashSeverity,
    ClashType,
)


class ClashPolicy:
    def __init__(
        self,
        *,
        extra_clearance_ft=0.0,
        ignored_pairs=(),
    ):
        self.extra_clearance_ft = max(
            0.0,
            float(extra_clearance_ft),
        )

        self.ignored_pairs = {
            frozenset(pair)
            for pair
            in ignored_pairs
        }

    def ignored(
        self,
        a,
        b,
    ):
        return frozenset(
            (
                a.category,
                b.category,
            )
        ) in self.ignored_pairs


class ClashDetector:
    def __init__(
        self,
        *,
        spatial_index,
        policy=None,
    ):
        self.spatial_index = spatial_index

        self.policy = (
            policy
            or ClashPolicy()
        )

    @staticmethod
    def _hard_severity(
        a,
        b,
        volume,
    ):
        structural = (
            a.discipline.value
            == "structural"
            or b.discipline.value
            == "structural"
        )

        life_system = (
            a.discipline.value
            in {
                "fire",
                "electrical",
            }
            or b.discipline.value
            in {
                "fire",
                "electrical",
            }
        )

        if (
            structural
            and volume > 0.01
        ):
            return ClashSeverity.CRITICAL

        if life_system:
            return ClashSeverity.HIGH

        if volume >= 1.0:
            return ClashSeverity.HIGH

        return ClashSeverity.MEDIUM

    @staticmethod
    def _clearance_severity(
        required,
        actual,
    ):
        if required <= 0:
            return ClashSeverity.LOW

        ratio = (
            max(
                0.0,
                required - actual,
            )
            / required
        )

        if ratio >= 0.75:
            return ClashSeverity.HIGH

        if ratio >= 0.35:
            return ClashSeverity.MEDIUM

        return ClashSeverity.LOW

    def evaluate_pair(
        self,
        a,
        b,
    ):
        if (
            a.element_id
            == b.element_id
        ):
            return None

        if self.policy.ignored(
            a,
            b,
        ):
            return None

        pair_ids = tuple(
            sorted(
                (
                    a.element_id,
                    b.element_id,
                )
            )
        )

        dx, dy, dz = overlap_depths(
            a.bounds,
            b.bounds,
        )

        hard = hard_intersects(
            a.bounds,
            b.bounds,
        )

        required_clearance = (
            max(
                0.0,
                a.clearance_ft,
            )
            + max(
                0.0,
                b.clearance_ft,
            )
            + self.policy.extra_clearance_ft
        )

        actual_distance = aabb_distance(
            a.bounds,
            b.bounds,
        )

        if hard:
            overlap_cf = overlap_volume(
                a.bounds,
                b.bounds,
            )

            severity = self._hard_severity(
                a,
                b,
                overlap_cf,
            )

            clash_type = ClashType.HARD

            message = (
                f"hard geometric intersection between "
                f"{pair_ids[0]} and {pair_ids[1]}"
            )

        elif (
            required_clearance > 0
            and actual_distance
            < required_clearance
        ):
            overlap_cf = 0.0

            severity = (
                self._clearance_severity(
                    required_clearance,
                    actual_distance,
                )
            )

            clash_type = ClashType.CLEARANCE

            message = (
                f"required clearance not satisfied between "
                f"{pair_ids[0]} and {pair_ids[1]}"
            )

        else:
            return None

        clash_id = stable_hash(
            {
                "element_a": pair_ids[0],
                "element_b": pair_ids[1],
                "clash_type": clash_type,
                "required_clearance":
                    required_clearance,
                "distance":
                    actual_distance,
                "overlap":
                    (
                        dx,
                        dy,
                        dz,
                    ),
            }
        )[:32]

        return Clash(
            clash_id=clash_id,
            element_a=pair_ids[0],
            element_b=pair_ids[1],
            clash_type=clash_type,
            severity=severity,
            distance_ft=actual_distance,
            overlap_x_ft=max(
                0.0,
                dx,
            ),
            overlap_y_ft=max(
                0.0,
                dy,
            ),
            overlap_z_ft=max(
                0.0,
                dz,
            ),
            overlap_volume_cf=overlap_cf,
            required_clearance_ft=(
                required_clearance
            ),
            message=message,
            professional_review_required=True,
        )

    def detect_all(self):
        clashes = []

        for (
            element_a,
            element_b,
        ) in self.spatial_index.candidate_pairs():
            a = self.spatial_index.get(
                element_a
            )

            b = self.spatial_index.get(
                element_b
            )

            if (
                a is None
                or b is None
            ):
                continue

            clash = self.evaluate_pair(
                a,
                b,
            )

            if clash is not None:
                clashes.append(
                    clash
                )

        return tuple(
            sorted(
                clashes,
                key=lambda clash: (
                    clash.clash_type.value,
                    clash.clash_id,
                ),
            )
        )
