from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class MultiphysicsError(RuntimeError):
    pass


class NumericalFailure(MultiphysicsError):
    pass


class SolverConvergenceError(MultiphysicsError):
    pass


class EngineeringModelError(MultiphysicsError):
    pass


class CalculationIntegrityError(MultiphysicsError):
    """Tamper, provenance, or deterministic calculation trace failure."""


class AnalysisDisposition(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    FAIL = "fail"
    NONCONVERGED = "nonconverged"


class PhysicsDomain(str, Enum):
    STRUCTURAL = "structural"
    GEOTECHNICAL = "geotechnical"
    SOIL_WATER = "soil_water"
    CONCRETE = "concrete"
    STEEL = "steel"
    HVAC = "hvac"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    THERMAL = "thermal"


@dataclass(frozen=True)
class LinearSystemResult:
    solution: tuple[float, ...]
    residual_norm: float
    relative_residual: float
    minimum_pivot: float
    maximum_pivot: float
    pivot_ratio: float
    converged: bool


@dataclass(frozen=True)
class TrussNode:
    node_id: str
    x: float
    y: float
    restrained_x: bool = False
    restrained_y: bool = False


@dataclass(frozen=True)
class TrussMember:
    member_id: str
    node_i: str
    node_j: str
    area: float
    elastic_modulus: float


@dataclass(frozen=True)
class NodalLoad:
    node_id: str
    fx: float = 0.0
    fy: float = 0.0


@dataclass(frozen=True)
class TrussMemberResult:
    member_id: str
    axial_force: float
    axial_stress: float
    axial_strain: float
    elongation: float


@dataclass(frozen=True)
class StructuralAnalysisResult:
    node_displacements: dict[str, tuple[float, float]]
    support_reactions: dict[str, tuple[float, float]]
    member_results: tuple[TrussMemberResult, ...]
    solver: LinearSystemResult
    equilibrium_error: float


@dataclass(frozen=True)
class SoilLayer:
    layer_id: str
    thickness_ft: float
    total_unit_weight_pcf: float
    saturated_unit_weight_pcf: float | None = None
    constrained_modulus_psf: float | None = None
    settlement_influence_factor: float = 1.0


@dataclass(frozen=True)
class EffectiveStressResult:
    depth_ft: float
    total_vertical_stress_psf: float
    pore_pressure_psf: float
    effective_vertical_stress_psf: float


@dataclass(frozen=True)
class FoundationBearingInputs:
    service_load_kips: float
    footing_area_sf: float
    allowable_bearing_psf: float
    footing_self_weight_kips: float = 0.0


@dataclass(frozen=True)
class FoundationBearingResult:
    gross_pressure_psf: float
    allowable_bearing_psf: float
    utilization: float
    passes_screen: bool
    professional_review_required: bool = True


@dataclass(frozen=True)
class SettlementResult:
    settlement_inches: float
    contributing_layers: tuple[tuple[str, float], ...]
    professional_review_required: bool = True


@dataclass(frozen=True)
class EarthPressureInputs:
    retained_height_ft: float
    soil_unit_weight_pcf: float
    friction_angle_deg: float
    surcharge_psf: float = 0.0
    water_height_ft: float = 0.0
    water_unit_weight_pcf: float = 62.4


@dataclass(frozen=True)
class EarthPressureResult:
    active_coefficient: float
    soil_thrust_lb_per_ft: float
    surcharge_thrust_lb_per_ft: float
    water_thrust_lb_per_ft: float
    total_thrust_lb_per_ft: float
    professional_review_required: bool = True


@dataclass(frozen=True)
class ConcreteSectionInputs:
    width_in: float
    effective_depth_in: float
    reinforcement_area_in2: float
    concrete_strength_psi: float
    steel_yield_strength_psi: float
    compression_stress_factor: float
    compression_block_factor: float
    resistance_factor: float
    source_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class ConcreteSectionResult:
    compression_block_depth_in: float
    nominal_moment_kip_ft: float
    design_moment_kip_ft: float
    professional_review_required: bool = True


@dataclass(frozen=True)
class SteelYieldInputs:
    area_in2: float
    section_modulus_in3: float
    yield_strength_ksi: float
    axial_resistance_factor: float
    flexural_resistance_factor: float
    source_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class SteelYieldResult:
    nominal_axial_capacity_kips: float
    design_axial_capacity_kips: float
    nominal_flexural_capacity_kip_ft: float
    design_flexural_capacity_kip_ft: float
    stability_check_required: bool = True
    professional_review_required: bool = True


@dataclass(frozen=True)
class HVACZoneInputs:
    zone_id: str

    opaque_area_sf: float
    opaque_u_value: float

    glazing_area_sf: float
    glazing_u_value: float

    design_delta_t_f: float

    infiltration_cfm: float
    sensible_air_coefficient: float
    latent_air_coefficient: float
    humidity_difference: float

    occupant_count: int
    sensible_btu_per_person: float
    latent_btu_per_person: float

    equipment_sensible_btu_hr: float
    solar_glazing_btu_hr: float = 0.0


@dataclass(frozen=True)
class HVACZoneResult:
    zone_id: str

    envelope_sensible_btu_hr: float

    infiltration_sensible_btu_hr: float
    infiltration_latent_btu_hr: float

    occupant_sensible_btu_hr: float
    occupant_latent_btu_hr: float

    equipment_sensible_btu_hr: float

    total_sensible_btu_hr: float
    total_latent_btu_hr: float
    total_btu_hr: float


@dataclass(frozen=True)
class ElectricalLoad:
    load_id: str
    connected_kva: float
    demand_factor: float


@dataclass(frozen=True)
class ElectricalDemandResult:
    connected_kva: float
    diversified_kva: float
    demand_ratio: float


@dataclass(frozen=True)
class AnalysisNode:
    node_id: str
    domain: PhysicsDomain
    dependencies: tuple[str, ...]
    evaluator: Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class GraphExecutionResult:
    values: dict[str, Any]
    execution_order: tuple[str, ...]


@dataclass(frozen=True)
class RandomVariable:
    name: str
    mean: float
    standard_deviation: float
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class UncertaintyResult:
    samples: int
    seed: int

    mean: float
    standard_deviation: float

    p05: float
    p50: float
    p95: float

    minimum: float
    maximum: float


@dataclass(frozen=True)
class EngineeringDiagnostic:
    diagnostic_id: str

    domain: PhysicsDomain

    disposition: AnalysisDisposition

    severity: float

    message: str

    evidence: dict[str, Any]

    professional_review_required: bool


@dataclass(frozen=True)
class AnalysisTrace:
    analysis_id: str

    engine: str
    engine_version: str

    domain: PhysicsDomain

    inputs: dict[str, Any]
    outputs: dict[str, Any]

    source_fact_ids: tuple[str, ...]

    executed_at: datetime

    content_hash: str
    previous_hash: str | None
    chain_hash: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
