from __future__ import annotations

from .models import (
    ConcreteSectionResult,
    EngineeringModelError,
    SteelYieldResult,
)


class ConcreteSectionEngine:
    """
    Rectangular singly-reinforced flexural mechanics.

    Governing coefficients and resistance factors are explicit inputs from
    the code-intelligence layer rather than hidden universal assumptions.
    """

    def rectangular_flexure(
        self,
        inputs,
    ):
        positive = (
            inputs.width_in,
            inputs.effective_depth_in,
            inputs.reinforcement_area_in2,
            inputs.concrete_strength_psi,
            inputs.steel_yield_strength_psi,
            inputs.compression_stress_factor,
            inputs.compression_block_factor,
            inputs.resistance_factor,
        )

        if any(
            value <= 0
            for value in positive
        ):
            raise EngineeringModelError(
                "concrete inputs must be positive"
            )

        if (
            inputs.resistance_factor
            > 1.0
        ):
            raise EngineeringModelError(
                "resistance factor cannot exceed one"
            )

        a = (
            inputs.reinforcement_area_in2
            * inputs.steel_yield_strength_psi
            / (
                inputs.compression_stress_factor
                * inputs.concrete_strength_psi
                * inputs.width_in
            )
        )

        if (
            a
            >= inputs.effective_depth_in
        ):
            raise EngineeringModelError(
                "compression block exceeds effective depth; "
                "model assumptions require review"
            )

        nominal_lb_in = (
            inputs.reinforcement_area_in2
            * inputs.steel_yield_strength_psi
            * (
                inputs.effective_depth_in
                - a / 2.0
            )
        )

        nominal_kip_ft = (
            nominal_lb_in
            / 12000.0
        )

        design_kip_ft = (
            nominal_kip_ft
            * inputs.resistance_factor
        )

        return ConcreteSectionResult(
            compression_block_depth_in=a,
            nominal_moment_kip_ft=(
                nominal_kip_ft
            ),
            design_moment_kip_ft=(
                design_kip_ft
            ),
            professional_review_required=True,
        )


class SteelYieldEngine:
    """
    Gross-section yield screening.

    This is not a complete steel member design. Stability, slenderness,
    buckling, fatigue, connections and other limit states remain explicit.
    """

    def gross_section(
        self,
        inputs,
    ):
        if (
            inputs.area_in2 <= 0
            or inputs.section_modulus_in3 <= 0
            or inputs.yield_strength_ksi <= 0
        ):
            raise EngineeringModelError(
                "steel inputs must be positive"
            )

        if not (
            0.0
            < inputs.axial_resistance_factor
            <= 1.0
        ):
            raise EngineeringModelError(
                "invalid axial resistance factor"
            )

        if not (
            0.0
            < inputs.flexural_resistance_factor
            <= 1.0
        ):
            raise EngineeringModelError(
                "invalid flexural resistance factor"
            )

        nominal_axial = (
            inputs.yield_strength_ksi
            * inputs.area_in2
        )

        nominal_flexural_kip_ft = (
            inputs.yield_strength_ksi
            * inputs.section_modulus_in3
            / 12.0
        )

        return SteelYieldResult(
            nominal_axial_capacity_kips=(
                nominal_axial
            ),
            design_axial_capacity_kips=(
                nominal_axial
                * inputs
                .axial_resistance_factor
            ),
            nominal_flexural_capacity_kip_ft=(
                nominal_flexural_kip_ft
            ),
            design_flexural_capacity_kip_ft=(
                nominal_flexural_kip_ft
                * inputs
                .flexural_resistance_factor
            ),
            stability_check_required=True,
            professional_review_required=True,
        )
