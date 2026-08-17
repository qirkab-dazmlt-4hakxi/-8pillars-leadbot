from __future__ import annotations

import unittest

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

from leadbot_v2.goat.bim_kernel import (
    BIMDiscipline,
    BIMKernelService,
    BIMRepository,
    ClashSeverity,
    ClashType,
    ConstraintDisposition,
    DependencyError,
    ElementCategory,
    EngineeringOverlayDisposition,
    Level,
    ModelIntegrityError,
    NumericConstraint,
    Vec3,
    aabb_distance,
    box_from_center,
    cross,
    dot,
    hard_intersects,
    normalize,
    overlap_volume,
    translate,
)


class FakeStore:
    def __init__(self):
        self.entities = {}

    def get_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        include_deleted=False,
    ):
        return deepcopy(
            self.entities.get(
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                )
            )
        )

    def put_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        payload,
        actor_id,
        expected_version=None,
    ):
        key = (
            tenant_id,
            entity_type,
            entity_id,
        )

        current = (
            self.entities.get(
                key
            )
        )

        if current is None:
            if expected_version is not None:
                raise RuntimeError(
                    "version conflict"
                )

            version = 1

        else:
            if (
                current.version
                != expected_version
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = (
                current.version
                + 1
            )

        record = SimpleNamespace(
            version=version,
            payload=deepcopy(
                payload
            ),
        )

        self.entities[
            key
        ] = record

        return deepcopy(
            record
        )


class ImportContractTests(
    unittest.TestCase
):
    def test_exports(self):
        import leadbot_v2.goat.bim_kernel as bim

        required = (
            "BIMKernelService",
            "BIMElementFactory",
            "SpatialHash3D",
            "ClashDetector",
            "ClashCorrectionEngine",
            "ModelRevisionLedger",
            "ModelDependencyGraph",
            "EngineeringOverlayEngine",
            "ModelConstraintEngine",
            "BIMRepository",
            "Vec3",
            "AABB",
        )

        for name in required:
            self.assertTrue(
                hasattr(
                    bim,
                    name,
                ),
                name,
            )


class GeometryTests(
    unittest.TestCase
):
    def test_vector_math(self):
        x = Vec3(
            1,
            0,
            0,
        )

        y = Vec3(
            0,
            1,
            0,
        )

        self.assertEqual(
            cross(
                x,
                y,
            ),
            Vec3(
                0,
                0,
                1,
            ),
        )

        self.assertEqual(
            dot(
                x,
                y,
            ),
            0,
        )

        self.assertEqual(
            normalize(
                Vec3(
                    2,
                    0,
                    0,
                )
            ),
            Vec3(
                1,
                0,
                0,
            ),
        )

    def test_intersection_and_distance(
        self,
    ):
        a = box_from_center(
            Vec3(
                0,
                0,
                0,
            ),
            2,
            2,
            2,
        )

        b = box_from_center(
            Vec3(
                0.5,
                0,
                0,
            ),
            2,
            2,
            2,
        )

        c = box_from_center(
            Vec3(
                4,
                0,
                0,
            ),
            2,
            2,
            2,
        )

        self.assertTrue(
            hard_intersects(
                a,
                b,
            )
        )

        self.assertGreater(
            overlap_volume(
                a,
                b,
            ),
            0,
        )

        self.assertAlmostEqual(
            aabb_distance(
                a,
                c,
            ),
            2.0,
        )


class ModelTests(
    unittest.TestCase
):
    def service(self):
        service = BIMKernelService(
            model_id="model",
            spatial_cell_size_ft=5.0,
        )

        service.add_level(
            Level(
                level_id="L1",
                name="Level 1",
                elevation_ft=0.0,
            )
        )

        return service

    def test_disciplines(self):
        service = self.service()

        pipe = service.factory.pipe(
            element_id="pipe",
            start=Vec3(
                0,
                0,
                0,
            ),
            end=Vec3(
                10,
                0,
                0,
            ),
            diameter_ft=0.5,
            level_id="L1",
        )

        beam = service.factory.beam(
            element_id="beam",
            start=Vec3(
                0,
                0,
                0,
            ),
            end=Vec3(
                10,
                0,
                0,
            ),
            width_ft=1.0,
            depth_ft=2.0,
            level_id="L1",
        )

        self.assertEqual(
            pipe.discipline,
            BIMDiscipline.PLUMBING,
        )

        self.assertEqual(
            beam.discipline,
            BIMDiscipline.STRUCTURAL,
        )

    def test_hard_clash(self):
        service = self.service()

        beam = service.factory.beam(
            element_id="beam",
            start=Vec3(
                -5,
                0,
                0,
            ),
            end=Vec3(
                5,
                0,
                0,
            ),
            width_ft=1.0,
            depth_ft=1.0,
            level_id="L1",
        )

        pipe = service.factory.pipe(
            element_id="pipe",
            start=Vec3(
                0,
                -5,
                0,
            ),
            end=Vec3(
                0,
                5,
                0,
            ),
            diameter_ft=0.5,
            level_id="L1",
        )

        service.add_element(
            beam
        )

        service.add_element(
            pipe
        )

        clashes = (
            service.detect_clashes()
        )

        self.assertEqual(
            len(clashes),
            1,
        )

        self.assertEqual(
            clashes[0].clash_type,
            ClashType.HARD,
        )

    def test_clearance_clash(self):
        service = self.service()

        equipment = (
            service.factory
            .generic_box(
                element_id="equipment",
                category=(
                    ElementCategory.EQUIPMENT
                ),
                discipline=(
                    BIMDiscipline.MECHANICAL
                ),
                center=Vec3(
                    0,
                    0,
                    0,
                ),
                size_x=2,
                size_y=2,
                size_z=2,
                level_id="L1",
                clearance_ft=2.0,
            )
        )

        wall = (
            service.factory
            .generic_box(
                element_id="wall",
                category=(
                    ElementCategory.WALL
                ),
                discipline=(
                    BIMDiscipline.ARCHITECTURAL
                ),
                center=Vec3(
                    3,
                    0,
                    0,
                ),
                size_x=2,
                size_y=2,
                size_z=2,
                level_id="L1",
            )
        )

        service.add_element(
            equipment
        )

        service.add_element(
            wall
        )

        clashes = (
            service.detect_clashes()
        )

        self.assertEqual(
            clashes[0].clash_type,
            ClashType.CLEARANCE,
        )

    def test_dependency_and_cycle(
        self,
    ):
        service = self.service()

        service.add_dependency(
            "grid",
            "column",
        )

        service.add_dependency(
            "column",
            "beam",
        )

        service.add_dependency(
            "beam",
            "duct",
        )

        self.assertEqual(
            service.impacted_by_change(
                (
                    "grid",
                )
            ),
            (
                "column",
                "beam",
                "duct",
            ),
        )

        with self.assertRaises(
            DependencyError
        ):
            service.add_dependency(
                "duct",
                "grid",
            )

    def test_constraint_and_overlay(
        self,
    ):
        service = self.service()

        beam = (
            service.factory
            .generic_box(
                element_id="beam",
                category=(
                    ElementCategory.BEAM
                ),
                discipline=(
                    BIMDiscipline.STRUCTURAL
                ),
                center=Vec3(
                    0,
                    0,
                    0,
                ),
                size_x=10,
                size_y=1,
                size_z=1,
                level_id="L1",
                professional_review_required=True,
            )
        )

        constraint = NumericConstraint(
            constraint_id="depth",
            name="minimum depth",
            field_name="depth_ft",
            operator="gte",
            expected=2.0,
            severity=(
                ClashSeverity.HIGH
            ),
            applicable_categories=(
                ElementCategory.BEAM,
            ),
            source_fact_id="rule",
            professional_review_required=True,
        )

        finding = (
            service.evaluate_constraints(
                element=beam,
                constraints=(
                    constraint,
                ),
                values={
                    "depth_ft":
                        1.0
                },
            )[0]
        )

        self.assertEqual(
            finding.disposition,
            ConstraintDisposition.FAIL,
        )

        overlay = service.add_overlay(
            element_id="beam",
            metric="moment",
            value=125.0,
            limit=100.0,
            source_analysis_id="analysis",
            source_fact_ids=(
                "rule",
            ),
        )

        self.assertEqual(
            overlay.disposition,
            EngineeringOverlayDisposition.FAIL,
        )

    def test_correction_preview(self):
        service = self.service()

        fixed = (
            service.factory
            .generic_box(
                element_id="beam",
                category=(
                    ElementCategory.BEAM
                ),
                discipline=(
                    BIMDiscipline.STRUCTURAL
                ),
                center=Vec3(
                    0,
                    0,
                    0,
                ),
                size_x=4,
                size_y=4,
                size_z=4,
                level_id="L1",
            )
        )

        movable = (
            service.factory
            .generic_box(
                element_id="duct",
                category=(
                    ElementCategory.DUCT
                ),
                discipline=(
                    BIMDiscipline.MECHANICAL
                ),
                center=Vec3(
                    0,
                    0,
                    0,
                ),
                size_x=2,
                size_y=2,
                size_z=2,
                level_id="L1",
                clearance_ft=0.5,
            )
        )

        service.add_element(
            fixed
        )

        service.add_element(
            movable
        )

        clash = (
            service.detect_clashes()[0]
        )

        alternatives = (
            service
            .correction_alternatives(
                clash=clash,
                fixed_element_id="beam",
                movable_element_id="duct",
                max_alternatives=3,
            )
        )

        self.assertEqual(
            len(alternatives),
            3,
        )

        preview = (
            service.corrections.preview(
                movable,
                alternatives[0],
            )
        )

        self.assertGreaterEqual(
            aabb_distance(
                fixed.bounds,
                preview.bounds,
            ),
            clash.required_clearance_ft
            - 1.0e-8,
        )

        self.assertTrue(
            alternatives[0]
            .professional_review_required
        )

        self.assertTrue(
            alternatives[0]
            .requires_reanalysis
        )

    def test_revision_integrity(self):
        service = self.service()

        element = (
            service.factory
            .generic_box(
                element_id="a",
                category=(
                    ElementCategory.EQUIPMENT
                ),
                discipline=(
                    BIMDiscipline.MECHANICAL
                ),
                center=Vec3(
                    0,
                    0,
                    0,
                ),
                size_x=2,
                size_y=2,
                size_z=2,
                level_id="L1",
            )
        )

        service.add_element(
            element
        )

        service.create_revision(
            changed_element_ids=(
                "a",
            ),
            author_id="engineer",
        )

        service.update_element(
            replace(
                service.element(
                    "a"
                ),
                bounds=translate(
                    service.element(
                        "a"
                    ).bounds,
                    Vec3(
                        1,
                        0,
                        0,
                    ),
                ),
            )
        )

        revision = (
            service.create_revision(
                changed_element_ids=(
                    "a",
                ),
                author_id="engineer",
            )
        )

        self.assertTrue(
            service.revisions.verify()
        )

        tampered = replace(
            revision,
            author_id="tampered",
        )

        with self.assertRaises(
            ModelIntegrityError
        ):
            service.revisions.verify_revision(
                tampered
            )

    def test_persistence(self):
        store = FakeStore()

        repository = BIMRepository(
            store,
            tenant_id="tenant",
        )

        service = BIMKernelService(
            model_id="model",
            repository=repository,
        )

        structural = (
            service.factory
            .generic_box(
                element_id="column",
                category=(
                    ElementCategory.COLUMN
                ),
                discipline=(
                    BIMDiscipline.STRUCTURAL
                ),
                center=Vec3(
                    0,
                    0,
                    0,
                ),
                size_x=2,
                size_y=2,
                size_z=2,
            )
        )

        pipe = (
            service.factory
            .generic_box(
                element_id="pipe",
                category=(
                    ElementCategory.PIPE
                ),
                discipline=(
                    BIMDiscipline.PLUMBING
                ),
                center=Vec3(
                    0,
                    0,
                    0,
                ),
                size_x=1,
                size_y=1,
                size_z=1,
            )
        )

        service.add_element(
            structural
        )

        service.add_element(
            pipe
        )

        service.detect_clashes()

        entity_types = {
            key[1]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.bim.element",
            entity_types,
        )

        self.assertIn(
            "goat.bim.clash",
            entity_types,
        )

    def test_large_spatial_reduction(
        self,
    ):
        service = BIMKernelService(
            model_id="stress",
            spatial_cell_size_ft=5.0,
        )

        for index in range(
            2000
        ):
            x = (
                index % 100
            ) * 10.0

            y = (
                index // 100
            ) * 10.0

            service.add_element(
                service.factory
                .generic_box(
                    element_id=(
                        f"element-{index}"
                    ),
                    category=(
                        ElementCategory.EQUIPMENT
                    ),
                    discipline=(
                        BIMDiscipline.MECHANICAL
                    ),
                    center=Vec3(
                        x,
                        y,
                        0,
                    ),
                    size_x=1,
                    size_y=1,
                    size_z=1,
                )
            )

        self.assertLess(
            len(
                service.spatial
                .candidate_pairs()
            ),
            1000,
        )


if __name__ == "__main__":
    unittest.main()
