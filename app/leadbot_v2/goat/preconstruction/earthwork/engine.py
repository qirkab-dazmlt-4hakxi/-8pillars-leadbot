from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil
from typing import Iterable
from uuid import uuid4

from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)
from leadbot_v2.goat.preconstruction.pricing.engine import (
    CostClass,
    MarkupPolicy,
    MissingRateError,
    PriceBook,
    PricingComponent,
    PricingUnit,
    apply_bps,
    money_extension,
)


CUBIC_FEET_PER_CUBIC_YARD = 27.0


class EarthworkError(RuntimeError):
    pass


class EarthworkValidationError(ValueError):
    pass


class EarthworkActivity(str, Enum):
    MASS_EXCAVATION = "mass_excavation"
    IMPORT_FILL = "import_fill"
    EXPORT_SPOIL = "export_spoil"
    COMPACTION = "compaction"
    FINE_GRADING = "fine_grading"
    TRENCH_EXCAVATION = "trench_excavation"
    BEDDING = "bedding"
    TRENCH_BACKFILL = "trench_backfill"
    ROCK_EXCAVATION = "rock_excavation"
    STABILIZATION = "stabilization"
    DEWATERING = "dewatering"


class EarthworkSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SoilFactors:
    """
    Explicit earthwork volume transformations.

    swell_percent:
        Bank material -> loose hauled material.

    shrink_percent:
        Bank material -> compacted material.

    Example:
        20% swell:
        100 BCY becomes 120 LCY.

        10% shrink:
        100 BCY becomes 90 CCY.
    """

    swell_percent: float = 0.0
    shrink_percent: float = 0.0

    def __post_init__(self) -> None:
        if self.swell_percent < 0:
            raise EarthworkValidationError(
                "swell percent cannot be negative"
            )

        if not 0 <= self.shrink_percent < 100:
            raise EarthworkValidationError(
                "shrink percent must be >= 0 and < 100"
            )

    @property
    def swell_factor(self) -> float:
        return (
            1.0
            + self.swell_percent / 100.0
        )

    @property
    def compacted_factor(self) -> float:
        return (
            1.0
            - self.shrink_percent / 100.0
        )

    def bank_to_loose(
        self,
        bank_cy: float,
    ) -> float:
        if bank_cy < 0:
            raise EarthworkValidationError(
                "bank volume cannot be negative"
            )

        return (
            bank_cy
            * self.swell_factor
        )

    def bank_to_compacted(
        self,
        bank_cy: float,
    ) -> float:
        if bank_cy < 0:
            raise EarthworkValidationError(
                "bank volume cannot be negative"
            )

        return (
            bank_cy
            * self.compacted_factor
        )

    def compacted_to_bank(
        self,
        compacted_cy: float,
    ) -> float:
        if compacted_cy < 0:
            raise EarthworkValidationError(
                "compacted volume cannot be negative"
            )

        return (
            compacted_cy
            / self.compacted_factor
        )


@dataclass(frozen=True)
class GradeCell:
    """
    Deterministic grid-cell cut/fill primitive.

    positive elevation_delta = fill
    negative elevation_delta = cut
    """

    cell_id: str
    area_sqft: float
    existing_elevation_ft: float
    proposed_elevation_ft: float
    undercut_ft: float = 0.0

    def __post_init__(self) -> None:
        if self.area_sqft <= 0:
            raise EarthworkValidationError(
                "grid cell area must be positive"
            )

        if self.undercut_ft < 0:
            raise EarthworkValidationError(
                "undercut cannot be negative"
            )

    @property
    def elevation_delta_ft(self) -> float:
        return (
            self.proposed_elevation_ft
            - self.existing_elevation_ft
        )


@dataclass(frozen=True)
class EarthworkRiskFinding:
    severity: EarthworkSeverity
    code: str
    message: str
    quantity: float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class MassBalanceResult:
    gross_cut_bcy: float
    gross_fill_ccy: float

    fill_bank_required_bcy: float

    surplus_bank_bcy: float
    deficit_bank_bcy: float

    export_loose_cy: float
    import_bank_cy: float

    disturbed_area_sf: float

    soil_factors: SoilFactors

    provenance: GeometryProvenance
    confidence: float

    findings: tuple[
        EarthworkRiskFinding,
        ...
    ] = ()

    @property
    def balanced(self) -> bool:
        return (
            self.surplus_bank_bcy == 0
            and self.deficit_bank_bcy == 0
        )


@dataclass(frozen=True)
class TrenchTakeoff:
    length_ft: float
    excavation_width_ft: float
    excavation_depth_ft: float

    excavation_bcy: float

    bedding_depth_ft: float
    bedding_cy: float

    pipe_displacement_cy: float

    backfill_cy: float
    excess_spoil_bcy: float

    provenance: GeometryProvenance
    confidence: float

    findings: tuple[
        EarthworkRiskFinding,
        ...
    ] = ()


@dataclass(frozen=True)
class HaulPlan:
    loose_volume_cy: float
    truck_capacity_cy: float
    usable_capacity_cy: float

    load_factor: float

    required_loads: int

    cycle_minutes: float
    truck_count: int

    total_truck_hours: float
    elapsed_hours: float


@dataclass(frozen=True)
class ProductionPlan:
    activity: EarthworkActivity
    quantity: float
    unit: str

    production_per_hour: float
    crew_hours: float

    labor_cost_per_hour_cents: int
    equipment_cost_per_hour_cents: int

    labor_cost_cents: int
    equipment_cost_cents: int
    total_production_cost_cents: int


@dataclass(frozen=True)
class EarthworkPricingRecipe:
    excavation_code: str = "MASS_EXCAVATION"
    import_fill_code: str = "IMPORT_FILL"
    export_haul_code: str = "EXPORT_HAUL"
    disposal_code: str = "DISPOSAL"
    compaction_code: str = "COMPACTION"
    fine_grading_code: str = "FINE_GRADING"

    trench_excavation_code: str = "TRENCH_EXCAVATION"
    bedding_code: str = "BEDDING"
    trench_backfill_code: str = "TRENCH_BACKFILL"
    trench_spoil_haul_code: str = "TRENCH_SPOIL_HAUL"

    include_disposal: bool = True


@dataclass(frozen=True)
class PricedEarthworkScope:
    scope_id: str
    description: str

    components: tuple[
        PricingComponent,
        ...
    ]

    direct_cost_cents: int

    overhead_cents: int
    contingency_cents: int
    profit_cents: int

    bid_price_cents: int

    provenance: GeometryProvenance

    confidence: float
    requires_review: bool

    findings: tuple[
        EarthworkRiskFinding,
        ...
    ] = ()

    def __post_init__(self) -> None:
        if not self.components:
            raise EarthworkValidationError(
                "priced earthwork scope requires components"
            )

        if self.direct_cost_cents < 0:
            raise EarthworkValidationError(
                "direct cost cannot be negative"
            )

        if self.bid_price_cents < 0:
            raise EarthworkValidationError(
                "bid price cannot be negative"
            )

        if not 0 <= self.confidence <= 1:
            raise EarthworkValidationError(
                "confidence must be 0-1"
            )


class EarthworkTakeoffEngine:

    REVIEW_CONFIDENCE = 0.80

    @staticmethod
    def cut_fill_from_cells(
        *,
        cells: Iterable[GradeCell],
        soil_factors: SoilFactors,
        provenance: GeometryProvenance,
    ) -> MassBalanceResult:
        cell_list = tuple(
            cells
        )

        if not cell_list:
            raise EarthworkValidationError(
                "cut/fill requires at least one grid cell"
            )

        cut_cf = 0.0
        fill_cf = 0.0
        disturbed_area = 0.0

        for cell in cell_list:
            disturbed_area += (
                cell.area_sqft
            )

            delta = (
                cell.elevation_delta_ft
            )

            if delta < 0:
                cut_depth = (
                    abs(delta)
                    + cell.undercut_ft
                )

                cut_cf += (
                    cell.area_sqft
                    * cut_depth
                )

            elif delta > 0:
                fill_cf += (
                    cell.area_sqft
                    * delta
                )

                if cell.undercut_ft > 0:
                    cut_cf += (
                        cell.area_sqft
                        * cell.undercut_ft
                    )

                    fill_cf += (
                        cell.area_sqft
                        * cell.undercut_ft
                    )

            elif cell.undercut_ft > 0:
                cut_cf += (
                    cell.area_sqft
                    * cell.undercut_ft
                )

                fill_cf += (
                    cell.area_sqft
                    * cell.undercut_ft
                )

        gross_cut_bcy = (
            cut_cf
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        gross_fill_ccy = (
            fill_cf
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        fill_bank_required = (
            soil_factors.compacted_to_bank(
                gross_fill_ccy
            )
        )

        balance = (
            gross_cut_bcy
            - fill_bank_required
        )

        surplus_bank = max(
            0.0,
            balance,
        )

        deficit_bank = max(
            0.0,
            -balance,
        )

        export_loose = (
            soil_factors.bank_to_loose(
                surplus_bank
            )
        )

        findings: list[
            EarthworkRiskFinding
        ] = []

        if deficit_bank > 0:
            findings.append(
                EarthworkRiskFinding(
                    severity=(
                        EarthworkSeverity.REVIEW
                    ),
                    code="import_required",
                    message=(
                        "On-site cut does not satisfy "
                        "compacted fill requirement."
                    ),
                    quantity=deficit_bank,
                    unit="BCY",
                )
            )

        if surplus_bank > 0:
            findings.append(
                EarthworkRiskFinding(
                    severity=(
                        EarthworkSeverity.REVIEW
                    ),
                    code="export_required",
                    message=(
                        "Cut/fill balance produces "
                        "surplus bank material requiring "
                        "reuse, stockpile or export."
                    ),
                    quantity=export_loose,
                    unit="LCY",
                )
            )

        if (
            soil_factors.swell_percent == 0
            and surplus_bank > 0
        ):
            findings.append(
                EarthworkRiskFinding(
                    severity=(
                        EarthworkSeverity.REVIEW
                    ),
                    code="swell_unverified",
                    message=(
                        "Export exists but swell factor "
                        "is zero. Verify geotechnical "
                        "material behavior."
                    ),
                )
            )

        if (
            soil_factors.shrink_percent == 0
            and gross_fill_ccy > 0
        ):
            findings.append(
                EarthworkRiskFinding(
                    severity=(
                        EarthworkSeverity.REVIEW
                    ),
                    code="shrink_unverified",
                    message=(
                        "Fill exists but shrink factor "
                        "is zero. Verify compaction and "
                        "geotechnical assumptions."
                    ),
                )
            )

        return MassBalanceResult(
            gross_cut_bcy=(
                gross_cut_bcy
            ),
            gross_fill_ccy=(
                gross_fill_ccy
            ),
            fill_bank_required_bcy=(
                fill_bank_required
            ),
            surplus_bank_bcy=(
                surplus_bank
            ),
            deficit_bank_bcy=(
                deficit_bank
            ),
            export_loose_cy=(
                export_loose
            ),
            import_bank_cy=(
                deficit_bank
            ),
            disturbed_area_sf=(
                disturbed_area
            ),
            soil_factors=soil_factors,
            provenance=provenance,
            confidence=(
                provenance.confidence
            ),
            findings=tuple(
                findings
            ),
        )

    @staticmethod
    def trench(
        *,
        length_ft: float,
        excavation_width_ft: float,
        excavation_depth_ft: float,
        provenance: GeometryProvenance,
        bedding_depth_ft: float = 0.0,
        pipe_outer_diameter_inches: float = 0.0,
    ) -> TrenchTakeoff:
        for name, value in (
            (
                "length",
                length_ft,
            ),
            (
                "excavation width",
                excavation_width_ft,
            ),
            (
                "excavation depth",
                excavation_depth_ft,
            ),
        ):
            if value <= 0:
                raise EarthworkValidationError(
                    f"{name} must be positive"
                )

        if bedding_depth_ft < 0:
            raise EarthworkValidationError(
                "bedding depth cannot be negative"
            )

        if bedding_depth_ft > excavation_depth_ft:
            raise EarthworkValidationError(
                "bedding cannot exceed trench depth"
            )

        if pipe_outer_diameter_inches < 0:
            raise EarthworkValidationError(
                "pipe diameter cannot be negative"
            )

        excavation_cf = (
            length_ft
            * excavation_width_ft
            * excavation_depth_ft
        )

        excavation_cy = (
            excavation_cf
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        bedding_cf = (
            length_ft
            * excavation_width_ft
            * bedding_depth_ft
        )

        bedding_cy = (
            bedding_cf
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        pipe_diameter_ft = (
            pipe_outer_diameter_inches
            / 12.0
        )

        pipe_radius_ft = (
            pipe_diameter_ft
            / 2.0
        )

        pipe_cf = (
            3.141592653589793
            * pipe_radius_ft
            * pipe_radius_ft
            * length_ft
        )

        pipe_cy = (
            pipe_cf
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        backfill_cy = max(
            0.0,
            excavation_cy
            - bedding_cy
            - pipe_cy,
        )

        excess_spoil = max(
            0.0,
            bedding_cy
            + pipe_cy,
        )

        findings: list[
            EarthworkRiskFinding
        ] = []

        if excavation_depth_ft >= 5.0:
            findings.append(
                EarthworkRiskFinding(
                    severity=(
                        EarthworkSeverity.HIGH
                    ),
                    code=(
                        "deep_trench_review"
                    ),
                    message=(
                        "Trench depth is at least "
                        "5 feet. Safety system, soil "
                        "classification, access and "
                        "protective-system requirements "
                        "must be evaluated before work."
                    ),
                    quantity=(
                        excavation_depth_ft
                    ),
                    unit="FT",
                )
            )

        if excavation_depth_ft >= 20.0:
            findings.append(
                EarthworkRiskFinding(
                    severity=(
                        EarthworkSeverity.CRITICAL
                    ),
                    code=(
                        "engineered_trench_review"
                    ),
                    message=(
                        "Very deep excavation detected. "
                        "Require project-specific "
                        "engineering and safety review."
                    ),
                    quantity=(
                        excavation_depth_ft
                    ),
                    unit="FT",
                )
            )

        return TrenchTakeoff(
            length_ft=length_ft,
            excavation_width_ft=(
                excavation_width_ft
            ),
            excavation_depth_ft=(
                excavation_depth_ft
            ),
            excavation_bcy=(
                excavation_cy
            ),
            bedding_depth_ft=(
                bedding_depth_ft
            ),
            bedding_cy=bedding_cy,
            pipe_displacement_cy=(
                pipe_cy
            ),
            backfill_cy=backfill_cy,
            excess_spoil_bcy=(
                excess_spoil
            ),
            provenance=provenance,
            confidence=(
                provenance.confidence
            ),
            findings=tuple(
                findings
            ),
        )


class HaulPlanningEngine:

    @staticmethod
    def plan(
        *,
        loose_volume_cy: float,
        truck_capacity_cy: float,
        cycle_minutes: float,
        truck_count: int,
        load_factor: float = 0.90,
    ) -> HaulPlan:
        if loose_volume_cy < 0:
            raise EarthworkValidationError(
                "haul volume cannot be negative"
            )

        if truck_capacity_cy <= 0:
            raise EarthworkValidationError(
                "truck capacity must be positive"
            )

        if cycle_minutes <= 0:
            raise EarthworkValidationError(
                "cycle time must be positive"
            )

        if truck_count < 1:
            raise EarthworkValidationError(
                "truck count must be >= 1"
            )

        if not 0 < load_factor <= 1:
            raise EarthworkValidationError(
                "load factor must be > 0 and <= 1"
            )

        usable = (
            truck_capacity_cy
            * load_factor
        )

        loads = (
            ceil(
                loose_volume_cy
                / usable
            )
            if loose_volume_cy > 0
            else 0
        )

        total_truck_hours = (
            loads
            * cycle_minutes
            / 60.0
        )

        elapsed_hours = (
            total_truck_hours
            / truck_count
            if truck_count
            else 0.0
        )

        return HaulPlan(
            loose_volume_cy=(
                loose_volume_cy
            ),
            truck_capacity_cy=(
                truck_capacity_cy
            ),
            usable_capacity_cy=(
                usable
            ),
            load_factor=load_factor,
            required_loads=loads,
            cycle_minutes=(
                cycle_minutes
            ),
            truck_count=truck_count,
            total_truck_hours=(
                total_truck_hours
            ),
            elapsed_hours=(
                elapsed_hours
            ),
        )


class ProductionPlanningEngine:

    @staticmethod
    def estimate(
        *,
        activity: EarthworkActivity,
        quantity: float,
        unit: str,
        production_per_hour: float,
        labor_cost_per_hour_cents: int,
        equipment_cost_per_hour_cents: int,
    ) -> ProductionPlan:
        if quantity < 0:
            raise EarthworkValidationError(
                "quantity cannot be negative"
            )

        if production_per_hour <= 0:
            raise EarthworkValidationError(
                "production rate must be positive"
            )

        if labor_cost_per_hour_cents < 0:
            raise EarthworkValidationError(
                "labor rate cannot be negative"
            )

        if equipment_cost_per_hour_cents < 0:
            raise EarthworkValidationError(
                "equipment rate cannot be negative"
            )

        hours = (
            quantity
            / production_per_hour
            if quantity > 0
            else 0.0
        )

        labor = money_extension(
            quantity=hours,
            cents_per_unit=(
                labor_cost_per_hour_cents
            ),
        )

        equipment = money_extension(
            quantity=hours,
            cents_per_unit=(
                equipment_cost_per_hour_cents
            ),
        )

        return ProductionPlan(
            activity=activity,
            quantity=quantity,
            unit=unit,
            production_per_hour=(
                production_per_hour
            ),
            crew_hours=hours,
            labor_cost_per_hour_cents=(
                labor_cost_per_hour_cents
            ),
            equipment_cost_per_hour_cents=(
                equipment_cost_per_hour_cents
            ),
            labor_cost_cents=labor,
            equipment_cost_cents=(
                equipment
            ),
            total_production_cost_cents=(
                labor + equipment
            ),
        )


class EarthworkPricingEngine:

    REVIEW_THRESHOLD = 0.80

    @staticmethod
    def _component(
        *,
        price_book: PriceBook,
        code: str,
        unit: PricingUnit,
        quantity: float,
    ) -> PricingComponent:
        rate = price_book.get(
            code=code,
            unit=unit,
        )

        return PricingComponent(
            rate_code=rate.code,
            description=rate.description,
            unit=rate.unit,
            cost_class=rate.cost_class,
            quantity=quantity,
            cents_per_unit=(
                rate.cents_per_unit
            ),
            extension_cents=(
                money_extension(
                    quantity=quantity,
                    cents_per_unit=(
                        rate.cents_per_unit
                    ),
                )
            ),
            source=rate.source,
        )

    @staticmethod
    def _finish(
        *,
        scope_id: str,
        description: str,
        components: list[
            PricingComponent
        ],
        markup: MarkupPolicy,
        provenance: GeometryProvenance,
        findings: tuple[
            EarthworkRiskFinding,
            ...
        ],
    ) -> PricedEarthworkScope:
        if not components:
            raise EarthworkError(
                "earthwork scope produced no pricing components"
            )

        direct = sum(
            item.extension_cents
            for item in components
        )

        overhead = apply_bps(
            amount_cents=direct,
            basis_points=(
                markup.overhead_bps
            ),
        )

        contingency = apply_bps(
            amount_cents=direct,
            basis_points=(
                markup.contingency_bps
            ),
        )

        before_profit = (
            direct
            + overhead
            + contingency
        )

        profit = apply_bps(
            amount_cents=(
                before_profit
            ),
            basis_points=(
                markup.profit_bps
            ),
        )

        bid = (
            before_profit
            + profit
        )

        serious_finding = any(
            item.severity
            in {
                EarthworkSeverity.HIGH,
                EarthworkSeverity.CRITICAL,
            }
            for item in findings
        )

        return PricedEarthworkScope(
            scope_id=scope_id,
            description=description,
            components=tuple(
                components
            ),
            direct_cost_cents=direct,
            overhead_cents=overhead,
            contingency_cents=(
                contingency
            ),
            profit_cents=profit,
            bid_price_cents=bid,
            provenance=provenance,
            confidence=(
                provenance.confidence
            ),
            requires_review=(
                provenance.confidence
                < EarthworkPricingEngine
                .REVIEW_THRESHOLD
                or serious_finding
            ),
            findings=findings,
        )

    @classmethod
    def price_mass_balance(
        cls,
        *,
        takeoff: MassBalanceResult,
        price_book: PriceBook,
        markup: MarkupPolicy,
        recipe: (
            EarthworkPricingRecipe
            | None
        ) = None,
        fine_grading: bool = True,
    ) -> PricedEarthworkScope:
        recipe = (
            recipe
            or EarthworkPricingRecipe()
        )

        components: list[
            PricingComponent
        ] = []

        if takeoff.gross_cut_bcy > 0:
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .excavation_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=(
                        takeoff
                        .gross_cut_bcy
                    ),
                )
            )

        if takeoff.import_bank_cy > 0:
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .import_fill_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=(
                        takeoff
                        .import_bank_cy
                    ),
                )
            )

        if takeoff.export_loose_cy > 0:
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .export_haul_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=(
                        takeoff
                        .export_loose_cy
                    ),
                )
            )

            if recipe.include_disposal:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .disposal_code
                        ),
                        unit=(
                            PricingUnit.CY
                        ),
                        quantity=(
                            takeoff
                            .export_loose_cy
                        ),
                    )
                )

        if takeoff.gross_fill_ccy > 0:
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .compaction_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=(
                        takeoff
                        .gross_fill_ccy
                    ),
                )
            )

        if (
            fine_grading
            and takeoff.disturbed_area_sf
            > 0
        ):
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .fine_grading_code
                    ),
                    unit=PricingUnit.SF,
                    quantity=(
                        takeoff
                        .disturbed_area_sf
                    ),
                )
            )

        return cls._finish(
            scope_id=(
                f"earth_{uuid4().hex}"
            ),
            description=(
                "Mass Earthwork"
            ),
            components=components,
            markup=markup,
            provenance=(
                takeoff.provenance
            ),
            findings=(
                takeoff.findings
            ),
        )

    @classmethod
    def price_trench(
        cls,
        *,
        takeoff: TrenchTakeoff,
        price_book: PriceBook,
        markup: MarkupPolicy,
        recipe: (
            EarthworkPricingRecipe
            | None
        ) = None,
    ) -> PricedEarthworkScope:
        recipe = (
            recipe
            or EarthworkPricingRecipe()
        )

        components: list[
            PricingComponent
        ] = []

        components.append(
            cls._component(
                price_book=price_book,
                code=(
                    recipe
                    .trench_excavation_code
                ),
                unit=PricingUnit.CY,
                quantity=(
                    takeoff
                    .excavation_bcy
                ),
            )
        )

        if takeoff.bedding_cy > 0:
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .bedding_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=(
                        takeoff
                        .bedding_cy
                    ),
                )
            )

        if takeoff.backfill_cy > 0:
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .trench_backfill_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=(
                        takeoff
                        .backfill_cy
                    ),
                )
            )

        if takeoff.excess_spoil_bcy > 0:
            components.append(
                cls._component(
                    price_book=(
                        price_book
                    ),
                    code=(
                        recipe
                        .trench_spoil_haul_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=(
                        takeoff
                        .excess_spoil_bcy
                    ),
                )
            )

            if recipe.include_disposal:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .disposal_code
                        ),
                        unit=PricingUnit.CY,
                        quantity=(
                            takeoff
                            .excess_spoil_bcy
                        ),
                    )
                )

        return cls._finish(
            scope_id=(
                f"trench_{uuid4().hex}"
            ),
            description=(
                "Trench Excavation"
            ),
            components=components,
            markup=markup,
            provenance=(
                takeoff.provenance
            ),
            findings=(
                takeoff.findings
            ),
        )


class EarthworkEstimateBridge:
    """
    Pushes deterministic Earthwork pricing into GOAT Estimate
    without losing plan/source provenance.
    """

    @staticmethod
    def add_to_estimate(
        *,
        workflow,
        estimate_id: str,
        actor_id: str,
        priced_scope: PricedEarthworkScope,
        cost_code: str,
    ):
        refs = (
            priced_scope
            .provenance
            .source_ref,
            *priced_scope
            .provenance
            .geometry_ids,
            *priced_scope
            .provenance
            .text_refs,
        )

        return workflow.add_manual_line(
            estimate_id=estimate_id,
            actor_id=actor_id,
            description=(
                priced_scope.description
            ),
            cost_code=cost_code,
            quantity=1.0,
            unit="LS",
            direct_cost_cents=(
                priced_scope
                .direct_cost_cents
            ),
            bid_price_cents=(
                priced_scope
                .bid_price_cents
            ),
            source_refs=tuple(
                dict.fromkeys(
                    refs
                )
            ),
            confidence=(
                priced_scope.confidence
            ),
            requires_review=(
                priced_scope
                .requires_review
            ),
        )
