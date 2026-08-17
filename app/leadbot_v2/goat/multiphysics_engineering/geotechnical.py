from __future__ import annotations

import math

from .models import (
    EarthPressureResult,
    EffectiveStressResult,
    EngineeringModelError,
    FoundationBearingResult,
    SettlementResult,
)


class EffectiveStressEngine:
    def calculate(
        self,
        *,
        layers,
        depth_ft,
        groundwater_depth_ft=None,
        water_unit_weight_pcf=62.4,
    ):
        if depth_ft < 0:
            raise EngineeringModelError(
                "depth cannot be negative"
            )

        remaining = float(
            depth_ft
        )

        total_stress = 0.0
        traversed = 0.0

        for layer in layers:
            if remaining <= 0:
                break

            thickness = min(
                layer.thickness_ft,
                remaining,
            )

            if thickness <= 0:
                continue

            layer_top = traversed
            layer_bottom = (
                traversed
                + thickness
            )

            if (
                groundwater_depth_ft
                is None
                or layer_bottom
                <= groundwater_depth_ft
            ):
                total_stress += (
                    layer
                    .total_unit_weight_pcf
                    * thickness
                )

            elif (
                layer_top
                >= groundwater_depth_ft
            ):
                saturated = (
                    layer
                    .saturated_unit_weight_pcf
                    if layer
                    .saturated_unit_weight_pcf
                    is not None
                    else layer
                    .total_unit_weight_pcf
                )

                total_stress += (
                    saturated
                    * thickness
                )

            else:
                dry_thickness = (
                    groundwater_depth_ft
                    - layer_top
                )

                wet_thickness = (
                    layer_bottom
                    - groundwater_depth_ft
                )

                saturated = (
                    layer
                    .saturated_unit_weight_pcf
                    if layer
                    .saturated_unit_weight_pcf
                    is not None
                    else layer
                    .total_unit_weight_pcf
                )

                total_stress += (
                    layer
                    .total_unit_weight_pcf
                    * dry_thickness
                    + saturated
                    * wet_thickness
                )

            remaining -= thickness
            traversed += thickness

        if remaining > 1.0e-9:
            raise EngineeringModelError(
                "soil profile does not reach "
                "requested depth"
            )

        pore_pressure = 0.0

        if (
            groundwater_depth_ft
            is not None
            and depth_ft
            > groundwater_depth_ft
        ):
            pore_pressure = (
                (
                    depth_ft
                    - groundwater_depth_ft
                )
                * water_unit_weight_pcf
            )

        effective = (
            total_stress
            - pore_pressure
        )

        return EffectiveStressResult(
            depth_ft=depth_ft,
            total_vertical_stress_psf=(
                total_stress
            ),
            pore_pressure_psf=(
                pore_pressure
            ),
            effective_vertical_stress_psf=(
                effective
            ),
        )


class FoundationEngine:
    def bearing_screen(
        self,
        inputs,
    ):
        if (
            inputs.footing_area_sf
            <= 0
        ):
            raise EngineeringModelError(
                "footing area must be positive"
            )

        if (
            inputs.allowable_bearing_psf
            <= 0
        ):
            raise EngineeringModelError(
                "allowable bearing must be positive"
            )

        total_load_lb = (
            (
                inputs.service_load_kips
                + inputs
                .footing_self_weight_kips
            )
            * 1000.0
        )

        pressure = (
            total_load_lb
            / inputs.footing_area_sf
        )

        utilization = (
            pressure
            / inputs.allowable_bearing_psf
        )

        return FoundationBearingResult(
            gross_pressure_psf=(
                pressure
            ),
            allowable_bearing_psf=(
                inputs.allowable_bearing_psf
            ),
            utilization=utilization,
            passes_screen=(
                utilization <= 1.0
            ),
            professional_review_required=True,
        )

    def settlement_screen(
        self,
        *,
        net_pressure_psf,
        layers,
    ):
        if net_pressure_psf < 0:
            raise EngineeringModelError(
                "net pressure cannot be negative"
            )

        components = []
        settlement_ft = 0.0

        for layer in layers:
            modulus = (
                layer
                .constrained_modulus_psf
            )

            if (
                modulus is None
                or modulus <= 0
            ):
                raise EngineeringModelError(
                    "settlement model requires "
                    "positive constrained modulus"
                )

            component_ft = (
                net_pressure_psf
                * layer.thickness_ft
                / modulus
                * layer
                .settlement_influence_factor
            )

            settlement_ft += (
                component_ft
            )

            components.append(
                (
                    layer.layer_id,
                    component_ft
                    * 12.0,
                )
            )

        return SettlementResult(
            settlement_inches=(
                settlement_ft
                * 12.0
            ),
            contributing_layers=tuple(
                components
            ),
            professional_review_required=True,
        )


class EarthPressureEngine:
    """
    Rankine active-pressure screening model.

    Assumptions must be validated before professional use.
    """

    def active(
        self,
        inputs,
    ):
        if (
            inputs.retained_height_ft
            < 0
        ):
            raise EngineeringModelError(
                "retained height cannot be negative"
            )

        if not (
            0.0
            <= inputs.friction_angle_deg
            < 90.0
        ):
            raise EngineeringModelError(
                "invalid friction angle"
            )

        angle = math.radians(
            45.0
            - inputs.friction_angle_deg
            / 2.0
        )

        ka = (
            math.tan(angle)
            ** 2
        )

        height = (
            inputs.retained_height_ft
        )

        soil = (
            0.5
            * ka
            * inputs.soil_unit_weight_pcf
            * height
            * height
        )

        surcharge = (
            ka
            * inputs.surcharge_psf
            * height
        )

        water_height = max(
            0.0,
            min(
                height,
                inputs.water_height_ft,
            ),
        )

        water = (
            0.5
            * inputs.water_unit_weight_pcf
            * water_height
            * water_height
        )

        return EarthPressureResult(
            active_coefficient=ka,
            soil_thrust_lb_per_ft=soil,
            surcharge_thrust_lb_per_ft=(
                surcharge
            ),
            water_thrust_lb_per_ft=water,
            total_thrust_lb_per_ft=(
                soil
                + surcharge
                + water
            ),
            professional_review_required=True,
        )
