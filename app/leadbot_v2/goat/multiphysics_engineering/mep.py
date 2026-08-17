from __future__ import annotations

from .models import (
    ElectricalDemandResult,
    EngineeringModelError,
    HVACZoneResult,
)


class HVACLoadEngine:
    def zone_load(
        self,
        inputs,
    ):
        nonnegative = (
            inputs.opaque_area_sf,
            inputs.opaque_u_value,
            inputs.glazing_area_sf,
            inputs.glazing_u_value,
            inputs.infiltration_cfm,
            inputs.sensible_air_coefficient,
            inputs.latent_air_coefficient,
            inputs.occupant_count,
            inputs.sensible_btu_per_person,
            inputs.latent_btu_per_person,
            inputs.equipment_sensible_btu_hr,
            inputs.solar_glazing_btu_hr,
        )

        if any(
            value < 0
            for value in nonnegative
        ):
            raise EngineeringModelError(
                "HVAC load inputs cannot be negative"
            )

        delta_t = abs(
            inputs.design_delta_t_f
        )

        envelope = (
            inputs.opaque_area_sf
            * inputs.opaque_u_value
            * delta_t
            + inputs.glazing_area_sf
            * inputs.glazing_u_value
            * delta_t
            + inputs.solar_glazing_btu_hr
        )

        infiltration_sensible = (
            inputs.sensible_air_coefficient
            * inputs.infiltration_cfm
            * delta_t
        )

        infiltration_latent = (
            inputs.latent_air_coefficient
            * inputs.infiltration_cfm
            * abs(
                inputs.humidity_difference
            )
        )

        occupant_sensible = (
            inputs.occupant_count
            * inputs.sensible_btu_per_person
        )

        occupant_latent = (
            inputs.occupant_count
            * inputs.latent_btu_per_person
        )

        total_sensible = (
            envelope
            + infiltration_sensible
            + occupant_sensible
            + inputs
            .equipment_sensible_btu_hr
        )

        total_latent = (
            infiltration_latent
            + occupant_latent
        )

        return HVACZoneResult(
            zone_id=inputs.zone_id,
            envelope_sensible_btu_hr=(
                envelope
            ),
            infiltration_sensible_btu_hr=(
                infiltration_sensible
            ),
            infiltration_latent_btu_hr=(
                infiltration_latent
            ),
            occupant_sensible_btu_hr=(
                occupant_sensible
            ),
            occupant_latent_btu_hr=(
                occupant_latent
            ),
            equipment_sensible_btu_hr=(
                inputs
                .equipment_sensible_btu_hr
            ),
            total_sensible_btu_hr=(
                total_sensible
            ),
            total_latent_btu_hr=(
                total_latent
            ),
            total_btu_hr=(
                total_sensible
                + total_latent
            ),
        )


class ElectricalDemandEngine:
    def aggregate(
        self,
        loads,
    ):
        connected = 0.0
        diversified = 0.0

        for load in loads:
            if load.connected_kva < 0:
                raise EngineeringModelError(
                    "connected load cannot be negative"
                )

            if not (
                0.0
                <= load.demand_factor
                <= 1.0
            ):
                raise EngineeringModelError(
                    "demand factor outside [0,1]"
                )

            connected += (
                load.connected_kva
            )

            diversified += (
                load.connected_kva
                * load.demand_factor
            )

        ratio = (
            diversified / connected
            if connected > 0
            else 0.0
        )

        return ElectricalDemandResult(
            connected_kva=connected,
            diversified_kva=(
                diversified
            ),
            demand_ratio=ratio,
        )
