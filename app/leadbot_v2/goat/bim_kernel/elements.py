from __future__ import annotations

from .geometry import (
    box_from_center,
    segment_bounds,
)

from .models import (
    BIMDiscipline,
    ElementCategory,
    ModelElement,
)


class BIMElementFactory:
    def wall(
        self,
        *,
        element_id,
        center,
        length_ft,
        thickness_ft,
        height_ft,
        level_id=None,
        material=None,
        clearance_ft=0.0,
        source_fact_ids=(),
        metadata=None,
    ):
        return ModelElement(
            element_id=element_id,
            category=ElementCategory.WALL,
            discipline=BIMDiscipline.ARCHITECTURAL,
            bounds=box_from_center(
                center,
                length_ft,
                thickness_ft,
                height_ft,
            ),
            level_id=level_id,
            material=material,
            clearance_ft=clearance_ft,
            geometry_kind="box",
            source_fact_ids=tuple(
                source_fact_ids
            ),
            metadata=dict(
                metadata or {}
            ),
        )

    def slab(
        self,
        *,
        element_id,
        center,
        length_ft,
        width_ft,
        thickness_ft,
        level_id=None,
        material="concrete",
        clearance_ft=0.0,
        source_fact_ids=(),
        metadata=None,
    ):
        return ModelElement(
            element_id=element_id,
            category=ElementCategory.SLAB,
            discipline=BIMDiscipline.STRUCTURAL,
            bounds=box_from_center(
                center,
                length_ft,
                width_ft,
                thickness_ft,
            ),
            level_id=level_id,
            material=material,
            clearance_ft=clearance_ft,
            geometry_kind="box",
            source_fact_ids=tuple(
                source_fact_ids
            ),
            professional_review_required=True,
            metadata=dict(
                metadata or {}
            ),
        )

    def beam(
        self,
        *,
        element_id,
        start,
        end,
        width_ft,
        depth_ft,
        level_id=None,
        material="steel",
        clearance_ft=0.0,
        source_fact_ids=(),
        metadata=None,
    ):
        radius = max(
            width_ft,
            depth_ft,
        ) / 2.0

        return ModelElement(
            element_id=element_id,
            category=ElementCategory.BEAM,
            discipline=BIMDiscipline.STRUCTURAL,
            bounds=segment_bounds(
                start,
                end,
                radius_ft=radius,
            ),
            level_id=level_id,
            material=material,
            clearance_ft=clearance_ft,
            geometry_kind="linear_member",
            source_fact_ids=tuple(
                source_fact_ids
            ),
            professional_review_required=True,
            metadata={
                **dict(metadata or {}),
                "start": start,
                "end": end,
                "width_ft": width_ft,
                "depth_ft": depth_ft,
            },
        )

    def column(
        self,
        *,
        element_id,
        center,
        width_ft,
        depth_ft,
        height_ft,
        level_id=None,
        material="steel",
        clearance_ft=0.0,
        source_fact_ids=(),
        metadata=None,
    ):
        return ModelElement(
            element_id=element_id,
            category=ElementCategory.COLUMN,
            discipline=BIMDiscipline.STRUCTURAL,
            bounds=box_from_center(
                center,
                width_ft,
                depth_ft,
                height_ft,
            ),
            level_id=level_id,
            material=material,
            clearance_ft=clearance_ft,
            source_fact_ids=tuple(
                source_fact_ids
            ),
            professional_review_required=True,
            metadata=dict(
                metadata or {}
            ),
        )

    def footing(
        self,
        *,
        element_id,
        center,
        length_ft,
        width_ft,
        depth_ft,
        level_id=None,
        material="concrete",
        clearance_ft=0.0,
        source_fact_ids=(),
        metadata=None,
    ):
        return ModelElement(
            element_id=element_id,
            category=ElementCategory.FOOTING,
            discipline=BIMDiscipline.STRUCTURAL,
            bounds=box_from_center(
                center,
                length_ft,
                width_ft,
                depth_ft,
            ),
            level_id=level_id,
            material=material,
            clearance_ft=clearance_ft,
            source_fact_ids=tuple(
                source_fact_ids
            ),
            professional_review_required=True,
            metadata=dict(
                metadata or {}
            ),
        )

    def pipe(
        self,
        *,
        element_id,
        start,
        end,
        diameter_ft,
        level_id=None,
        system_id=None,
        clearance_ft=0.0,
        source_fact_ids=(),
        metadata=None,
    ):
        return ModelElement(
            element_id=element_id,
            category=ElementCategory.PIPE,
            discipline=BIMDiscipline.PLUMBING,
            bounds=segment_bounds(
                start,
                end,
                radius_ft=(
                    diameter_ft / 2.0
                ),
            ),
            level_id=level_id,
            system_id=system_id,
            clearance_ft=clearance_ft,
            geometry_kind="pipe_segment",
            source_fact_ids=tuple(
                source_fact_ids
            ),
            professional_review_required=True,
            metadata={
                **dict(metadata or {}),
                "diameter_ft": diameter_ft,
                "start": start,
                "end": end,
            },
        )

    def duct(
        self,
        *,
        element_id,
        start,
        end,
        width_ft,
        height_ft,
        level_id=None,
        system_id=None,
        clearance_ft=0.0,
        source_fact_ids=(),
        metadata=None,
    ):
        radius = max(
            width_ft,
            height_ft,
        ) / 2.0

        return ModelElement(
            element_id=element_id,
            category=ElementCategory.DUCT,
            discipline=BIMDiscipline.MECHANICAL,
            bounds=segment_bounds(
                start,
                end,
                radius_ft=radius,
            ),
            level_id=level_id,
            system_id=system_id,
            clearance_ft=clearance_ft,
            geometry_kind="duct_segment",
            source_fact_ids=tuple(
                source_fact_ids
            ),
            professional_review_required=True,
            metadata={
                **dict(metadata or {}),
                "width_ft": width_ft,
                "height_ft": height_ft,
                "start": start,
                "end": end,
            },
        )

    def generic_box(
        self,
        *,
        element_id,
        category,
        discipline,
        center,
        size_x,
        size_y,
        size_z,
        level_id=None,
        system_id=None,
        material=None,
        clearance_ft=0.0,
        professional_review_required=False,
        metadata=None,
    ):
        return ModelElement(
            element_id=element_id,
            category=category,
            discipline=discipline,
            bounds=box_from_center(
                center,
                size_x,
                size_y,
                size_z,
            ),
            level_id=level_id,
            system_id=system_id,
            material=material,
            clearance_ft=clearance_ft,
            professional_review_required=(
                professional_review_required
            ),
            metadata=dict(
                metadata or {}
            ),
        )
