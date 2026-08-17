from __future__ import annotations

from .clash import (
    ClashDetector,
    ClashPolicy,
)

from .constraints import (
    ModelConstraintEngine,
)

from .correction import (
    ClashCorrectionEngine,
)

from .dependency import (
    ModelDependencyGraph,
)

from .elements import (
    BIMElementFactory,
)

from .models import ModelHealth

from .overlays import (
    EngineeringOverlayEngine,
)

from .revisions import (
    ModelRevisionLedger,
)

from .spatial import SpatialHash3D


class BIMKernelService:
    def __init__(
        self,
        *,
        model_id,
        repository=None,
        spatial_cell_size_ft=10.0,
        clash_policy=None,
    ):
        self.model_id = model_id
        self.repository = repository

        self.factory = BIMElementFactory()

        self.spatial = SpatialHash3D(
            cell_size_ft=(
                spatial_cell_size_ft
            )
        )

        self.clash_detector = ClashDetector(
            spatial_index=self.spatial,
            policy=(
                clash_policy
                or ClashPolicy()
            ),
        )

        self.dependencies = (
            ModelDependencyGraph()
        )

        self.constraints = (
            ModelConstraintEngine()
        )

        self.overlays = (
            EngineeringOverlayEngine()
        )

        self.corrections = (
            ClashCorrectionEngine()
        )

        self.revisions = (
            ModelRevisionLedger()
        )

        self._levels = {}
        self._last_clashes = ()

    def add_level(
        self,
        level,
    ):
        if (
            level.level_id
            in self._levels
        ):
            raise ValueError(
                "duplicate level"
            )

        self._levels[
            level.level_id
        ] = level

        return level

    def levels(self):
        return tuple(
            self._levels[key]
            for key
            in sorted(self._levels)
        )

    def _check_level(
        self,
        element,
    ):
        if (
            element.level_id
            is not None
            and element.level_id
            not in self._levels
        ):
            raise ValueError(
                f"unknown level: "
                f"{element.level_id}"
            )

    def add_element(
        self,
        element,
    ):
        self._check_level(
            element
        )

        self.spatial.insert(
            element
        )

        if self.repository:
            self.repository.save_element(
                element
            )

        return element

    def update_element(
        self,
        element,
    ):
        self._check_level(
            element
        )

        self.spatial.update(
            element
        )

        if self.repository:
            self.repository.save_element(
                element
            )

        return element

    def element(
        self,
        element_id,
    ):
        return self.spatial.get(
            element_id
        )

    def elements(self):
        return tuple(
            sorted(
                self.spatial.elements(),
                key=lambda element:
                    element.element_id,
            )
        )

    def detect_clashes(self):
        clashes = (
            self.clash_detector
            .detect_all()
        )

        self._last_clashes = (
            clashes
        )

        if self.repository:
            for clash in clashes:
                self.repository.save_clash(
                    clash
                )

        return clashes

    def add_dependency(
        self,
        source_id,
        dependent_id,
        *,
        relationship="depends_on",
    ):
        return self.dependencies.add(
            source_id,
            dependent_id,
            relationship=relationship,
        )

    def impacted_by_change(
        self,
        changed_ids,
    ):
        return self.dependencies.impacted(
            changed_ids
        )

    def create_revision(
        self,
        *,
        changed_element_ids,
        author_id,
        created_at=None,
    ):
        snapshot = {
            element.element_id:
                element
            for element
            in self.elements()
        }

        revision = self.revisions.append(
            model_id=self.model_id,
            snapshot=snapshot,
            changed_element_ids=(
                changed_element_ids
            ),
            author_id=author_id,
            created_at=created_at,
        )

        if self.repository:
            self.repository.save_revision(
                revision
            )

        return revision

    def add_overlay(
        self,
        **kwargs,
    ):
        overlay = (
            self.overlays
            .utilization(
                **kwargs
            )
        )

        if self.repository:
            self.repository.save_overlay(
                overlay
            )

        return overlay

    def evaluate_constraints(
        self,
        *,
        element,
        constraints,
        values,
    ):
        findings = (
            self.constraints
            .evaluate(
                element=element,
                constraints=constraints,
                values=values,
            )
        )

        if self.repository:
            for finding in findings:
                self.repository.save_constraint_finding(
                    finding
                )

        return findings

    def correction_alternatives(
        self,
        *,
        clash,
        fixed_element_id,
        movable_element_id,
        minimum_clearance_ft=None,
        max_alternatives=4,
    ):
        fixed = self.element(
            fixed_element_id
        )

        movable = self.element(
            movable_element_id
        )

        if (
            fixed is None
            or movable is None
        ):
            raise ValueError(
                "unknown clash correction element"
            )

        alternatives = (
            self.corrections.propose(
                clash=clash,
                fixed=fixed,
                movable=movable,
                minimum_clearance_ft=(
                    minimum_clearance_ft
                ),
                max_alternatives=(
                    max_alternatives
                ),
            )
        )

        if self.repository:
            for alternative in alternatives:
                self.repository.save_correction(
                    alternative
                )

        return alternatives

    def health(self):
        hard = sum(
            1
            for clash
            in self._last_clashes
            if clash.clash_type.value
            == "hard"
        )

        clearance = (
            len(
                self._last_clashes
            )
            - hard
        )

        integrity = (
            self.revisions.verify()
            if self.revisions.revisions()
            else True
        )

        return ModelHealth(
            element_count=len(
                self.spatial.elements()
            ),
            level_count=len(
                self._levels
            ),
            clash_count=len(
                self._last_clashes
            ),
            hard_clash_count=hard,
            clearance_clash_count=(
                clearance
            ),
            dependency_count=len(
                self.dependencies.edges()
            ),
            revision_count=len(
                self.revisions.revisions()
            ),
            integrity_ok=integrity,
        )
