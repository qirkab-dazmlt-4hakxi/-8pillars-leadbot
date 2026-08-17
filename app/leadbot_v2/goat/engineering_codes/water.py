from __future__ import annotations

from .models import (
    WaterIntrusionAssessment,
    WaterRiskLevel,
)


PSI_PER_FOOT_WATER = (
    62.4 / 144.0
)


def clamp(
    value,
):
    return max(
        0.0,
        min(
            1.0,
            float(value),
        ),
    )


class WaterIntrusionEngine:
    """
    Deterministic below-grade hydrostatic/intrusion screening.

    This is a design-assistance calculation, not a substitute for a sealed
    geotechnical, structural, civil, waterproofing, or floodplain design.
    """

    def assess(
        self,
        inputs,
    ):
        elevations = [
            elevation
            for elevation
            in (
                inputs.groundwater_elevation_ft,
                inputs.design_flood_elevation_ft,
            )
            if elevation is not None
        ]

        governing = (
            max(elevations)
            if elevations
            else None
        )

        head = (
            max(
                0.0,
                governing
                - inputs
                .lowest_structural_elevation_ft,
            )
            if governing is not None
            else 0.0
        )

        pressure_psi = (
            head
            * PSI_PER_FOOT_WATER
        )

        uplift_lbs = (
            pressure_psi
            * max(
                0.0,
                inputs.slab_area_sf
            )
            * 144.0
        )

        uplift_kips = (
            uplift_lbs
            / 1000.0
        )

        soil = clamp(
            inputs.soil_permeability_index
        )

        waterproofing = clamp(
            inputs.waterproofing_reliability
        )

        drainage = clamp(
            inputs.drainage_reliability
        )

        sump = clamp(
            inputs.sump_reliability
        )

        redundancy = min(
            0.20,
            max(
                0,
                int(
                    inputs.redundancy_count
                )
            )
            * 0.05,
        )

        hydrostatic_component = min(
            1.0,
            head / max(
                1.0,
                inputs
                .below_grade_wall_height_ft,
            ),
        )

        intrusion_index = (
            hydrostatic_component
            * 0.40
            + soil
            * 0.20
            + (
                1.0
                - waterproofing
            )
            * 0.20
            + (
                1.0
                - drainage
            )
            * 0.10
            + (
                1.0
                - sump
            )
            * 0.10
            - redundancy
        )

        intrusion_index = clamp(
            intrusion_index
        )

        if (
            head >= 12.0
            or intrusion_index >= 0.80
        ):
            risk = (
                WaterRiskLevel.CRITICAL
            )

        elif (
            head >= 6.0
            or intrusion_index >= 0.60
        ):
            risk = (
                WaterRiskLevel.HIGH
            )

        elif (
            head > 0.0
            or intrusion_index >= 0.35
        ):
            risk = (
                WaterRiskLevel.MODERATE
            )

        else:
            risk = (
                WaterRiskLevel.LOW
            )

        notes = []

        if governing is None:
            notes.append(
                "No groundwater/flood elevation supplied; "
                "hydrostatic head defaults to zero and field/official "
                "data should be obtained."
            )

        if head > 0:
            notes.append(
                "Water elevation is above the lowest structural elevation."
            )

        if waterproofing < 0.70:
            notes.append(
                "Waterproofing reliability is below preferred screening band."
            )

        if drainage < 0.70:
            notes.append(
                "Drainage reliability is below preferred screening band."
            )

        if sump < 0.70:
            notes.append(
                "Sump/dewatering reliability is below preferred screening band."
            )

        return WaterIntrusionAssessment(
            governing_water_elevation_ft=(
                governing
            ),
            hydrostatic_head_ft=(
                head
            ),
            base_pressure_psi=(
                pressure_psi
            ),
            estimated_uplift_kips=(
                uplift_kips
            ),
            intrusion_probability_index=(
                intrusion_index
            ),
            risk_level=risk,
            drainage_credit=(
                drainage
            ),
            waterproofing_credit=(
                waterproofing
            ),
            notes=tuple(
                notes
            ),
            professional_review_required=True,
        )
