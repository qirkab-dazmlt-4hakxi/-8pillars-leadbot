from __future__ import annotations

import re

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)
from leadbot_v2.goat.preconstruction.pricing.engine import (
    MarkupPolicy,
    MissingRateError,
    PriceBook,
    PricingComponent,
    PricingUnit,
    apply_bps,
    money_extension,
)


class ElectricalValidationError(ValueError):
    pass


class ElectricalSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    HIGH = "high"
    CRITICAL = "critical"


class ElectricalSystemKind(str, Enum):
    SERVICE = "service"
    FEEDER = "feeder"
    BRANCH = "branch"
    LIGHTING = "lighting"
    DEVICE = "device"
    PANEL = "panel"
    EQUIPMENT = "equipment"


@dataclass(frozen=True)
class ElectricalRiskFinding:
    severity: ElectricalSeverity
    code: str
    message: str


@dataclass(frozen=True)
class ElectricalServiceCallout:
    amperage: int
    voltage: str | None
    phase: int | None
    raw: str
    confidence: float

    def __post_init__(self) -> None:
        if self.amperage <= 0:
            raise ElectricalValidationError(
                "service amperage must be positive"
            )

        if not 0 <= self.confidence <= 1:
            raise ElectricalValidationError(
                "confidence must be 0-1"
            )


@dataclass(frozen=True)
class ConductorSpecification:
    count: int
    size: str
    material: str | None
    raw: str
    confidence: float

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ElectricalValidationError(
                "conductor count must be >= 1"
            )

        if not self.size.strip():
            raise ElectricalValidationError(
                "conductor size required"
            )


@dataclass(frozen=True)
class ConduitSpecification:
    size_inches: str
    conduit_type: str
    raw: str
    confidence: float


@dataclass(frozen=True)
class ElectricalRunTakeoff:
    run_id: str

    description: str
    length_ft: float

    conduit: ConduitSpecification | None
    conductors: ConductorSpecification | None

    conductor_waste_percent: float
    conductor_linear_feet: float

    termination_count: int

    provenance: GeometryProvenance

    confidence: float

    findings: tuple[
        ElectricalRiskFinding,
        ...
    ]

    @property
    def requires_review(self) -> bool:
        return (
            self.confidence < 0.80
            or any(
                finding.severity
                in {
                    ElectricalSeverity.HIGH,
                    ElectricalSeverity.CRITICAL,
                }
                for finding in self.findings
            )
        )


@dataclass(frozen=True)
class ElectricalCountTakeoff:
    takeoff_id: str
    description: str
    quantity: int
    provenance: GeometryProvenance
    confidence: float


@dataclass(frozen=True)
class ElectricalPricingRecipe:
    conduit_material_code: str | None = None
    conduit_labor_code: str | None = None

    conductor_material_code: str | None = None
    conductor_labor_code: str | None = None

    termination_code: str | None = None


@dataclass(frozen=True)
class PricedElectricalScope:
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
        ElectricalRiskFinding,
        ...
    ]


SERVICE_RE = re.compile(
    r"\b(?P<amps>\d{2,5})\s*"
    r"(?:A|AMP|AMPS)\b"
    r"(?:.*?"
    r"(?P<voltage>"
    r"\d{3}(?:Y/\d{3})?"
    r"|\d{3}/\d{3}"
    r")\s*V?)?"
    r"(?:.*?"
    r"(?P<phase>[13])\s*"
    r"(?:PH|PHASE|Ø))?",
    re.I,
)


CONDUIT_RE = re.compile(
    r"\b(?P<size>"
    r"\d+(?:\.\d+)?"
    r"|\d+\s+\d+/\d+"
    r"|\d+/\d+"
    r")\s*"
    r"[\"”]?\s*"
    r"(?P<type>"
    r"EMT|IMC|RMC|PVC|"
    r"SCH(?:EDULE)?\s*40|"
    r"SCH(?:EDULE)?\s*80"
    r")\b",
    re.I,
)


CONDUCTOR_RE = re.compile(
    r"\b(?P<count>\d+)\s*"
    r"(?:X|\-|\s)?\s*"
    r"#?\s*"
    r"(?P<size>"
    r"[1-4]/0"
    r"|\d{1,2}"
    r")\s*"
    r"(?P<material>"
    r"CU|COPPER|AL|ALUMINUM"
    r")?\b",
    re.I,
)


class ElectricalCalloutParser:

    @staticmethod
    def service(
        text: str,
    ) -> ElectricalServiceCallout | None:
        match = SERVICE_RE.search(
            text
        )

        if not match:
            return None

        phase = (
            int(
                match.group("phase")
            )
            if match.group("phase")
            else None
        )

        return ElectricalServiceCallout(
            amperage=int(
                match.group("amps")
            ),
            voltage=(
                match.group("voltage")
            ),
            phase=phase,
            raw=text.strip(),
            confidence=(
                0.98
                if (
                    match.group("voltage")
                    and phase
                )
                else 0.86
            ),
        )

    @staticmethod
    def conduit(
        text: str,
    ) -> ConduitSpecification | None:
        match = CONDUIT_RE.search(
            text
        )

        if not match:
            return None

        conduit_type = (
            match.group("type")
            .upper()
            .replace(
                "SCHEDULE",
                "SCH"
            )
        )

        conduit_type = re.sub(
            r"\s+",
            " ",
            conduit_type,
        )

        return ConduitSpecification(
            size_inches=(
                match.group("size")
                .strip()
            ),
            conduit_type=(
                conduit_type
            ),
            raw=match.group(0),
            confidence=0.97,
        )

    @staticmethod
    def conductors(
        text: str,
    ) -> ConductorSpecification | None:
        match = CONDUCTOR_RE.search(
            text
        )

        if not match:
            return None

        material = (
            match.group("material")
        )

        if material:
            normalized = (
                material.upper()
            )

            material = (
                "CU"
                if normalized
                in {
                    "CU",
                    "COPPER",
                }
                else "AL"
            )

        return ConductorSpecification(
            count=int(
                match.group("count")
            ),
            size=(
                match.group("size")
            ),
            material=material,
            raw=match.group(0),
            confidence=(
                0.97
                if material
                else 0.88
            ),
        )


class ElectricalTakeoffEngine:

    @staticmethod
    def run(
        *,
        description: str,
        length_ft: float,
        provenance: GeometryProvenance,
        conduit: (
            ConduitSpecification
            | None
        ),
        conductors: (
            ConductorSpecification
            | None
        ),
        conductor_waste_percent: float = 10.0,
        termination_count: int = 0,
    ) -> ElectricalRunTakeoff:
        if length_ft <= 0:
            raise ElectricalValidationError(
                "electrical run length must be positive"
            )

        if conductor_waste_percent < 0:
            raise ElectricalValidationError(
                "wire waste cannot be negative"
            )

        if termination_count < 0:
            raise ElectricalValidationError(
                "termination count cannot be negative"
            )

        findings: list[
            ElectricalRiskFinding
        ] = []

        if conduit is None:
            findings.append(
                ElectricalRiskFinding(
                    severity=(
                        ElectricalSeverity.REVIEW
                    ),
                    code=(
                        "conduit_unresolved"
                    ),
                    message=(
                        "Conduit type/size was not "
                        "resolved from the drawing."
                    ),
                )
            )

        if conductors is None:
            findings.append(
                ElectricalRiskFinding(
                    severity=(
                        ElectricalSeverity.HIGH
                    ),
                    code=(
                        "conductors_unresolved"
                    ),
                    message=(
                        "Conductor quantity/size was not "
                        "resolved. Do not finalize feeder "
                        "pricing until verified."
                    ),
                )
            )

        conductor_lf = 0.0

        if conductors is not None:
            conductor_lf = (
                length_ft
                * conductors.count
                * (
                    1.0
                    + conductor_waste_percent
                    / 100.0
                )
            )

        confidence_values = [
            provenance.confidence,
        ]

        if conduit:
            confidence_values.append(
                conduit.confidence
            )

        if conductors:
            confidence_values.append(
                conductors.confidence
            )

        confidence = min(
            confidence_values
        )

        return ElectricalRunTakeoff(
            run_id=(
                f"elec_{uuid4().hex}"
            ),
            description=description,
            length_ft=length_ft,
            conduit=conduit,
            conductors=conductors,
            conductor_waste_percent=(
                conductor_waste_percent
            ),
            conductor_linear_feet=(
                conductor_lf
            ),
            termination_count=(
                termination_count
            ),
            provenance=provenance,
            confidence=confidence,
            findings=tuple(
                findings
            ),
        )

    @staticmethod
    def count(
        *,
        description: str,
        quantity: int,
        provenance: GeometryProvenance,
    ) -> ElectricalCountTakeoff:
        if quantity < 1:
            raise ElectricalValidationError(
                "electrical count must be >= 1"
            )

        return ElectricalCountTakeoff(
            takeoff_id=(
                f"eleccount_{uuid4().hex}"
            ),
            description=description,
            quantity=quantity,
            provenance=provenance,
            confidence=(
                provenance.confidence
            ),
        )


class ElectricalPricingEngine:

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
        takeoff: ElectricalRunTakeoff,
        components: list[
            PricingComponent
        ],
        markup: MarkupPolicy,
    ) -> PricedElectricalScope:
        if not components:
            raise ElectricalValidationError(
                "electrical scope produced no pricing components"
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

        subtotal = (
            direct
            + overhead
            + contingency
        )

        profit = apply_bps(
            amount_cents=subtotal,
            basis_points=(
                markup.profit_bps
            ),
        )

        return PricedElectricalScope(
            scope_id=takeoff.run_id,
            description=(
                takeoff.description
            ),
            components=tuple(
                components
            ),
            direct_cost_cents=direct,
            overhead_cents=overhead,
            contingency_cents=(
                contingency
            ),
            profit_cents=profit,
            bid_price_cents=(
                subtotal + profit
            ),
            provenance=(
                takeoff.provenance
            ),
            confidence=(
                takeoff.confidence
            ),
            requires_review=(
                takeoff.requires_review
            ),
            findings=(
                takeoff.findings
            ),
        )

    @classmethod
    def price_run(
        cls,
        *,
        takeoff: ElectricalRunTakeoff,
        price_book: PriceBook,
        markup: MarkupPolicy,
        recipe: ElectricalPricingRecipe,
    ) -> PricedElectricalScope:
        components: list[
            PricingComponent
        ] = []

        if takeoff.conduit is not None:
            if recipe.conduit_material_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .conduit_material_code
                        ),
                        unit=PricingUnit.LF,
                        quantity=(
                            takeoff.length_ft
                        ),
                    )
                )

            if recipe.conduit_labor_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .conduit_labor_code
                        ),
                        unit=PricingUnit.LF,
                        quantity=(
                            takeoff.length_ft
                        ),
                    )
                )

        if takeoff.conductors is not None:
            if recipe.conductor_material_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .conductor_material_code
                        ),
                        unit=PricingUnit.LF,
                        quantity=(
                            takeoff
                            .conductor_linear_feet
                        ),
                    )
                )

            if recipe.conductor_labor_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .conductor_labor_code
                        ),
                        unit=PricingUnit.LF,
                        quantity=(
                            takeoff
                            .conductor_linear_feet
                        ),
                    )
                )

        if (
            recipe.termination_code
            and takeoff.termination_count
            > 0
        ):
            components.append(
                cls._component(
                    price_book=price_book,
                    code=(
                        recipe
                        .termination_code
                    ),
                    unit=PricingUnit.EA,
                    quantity=(
                        takeoff
                        .termination_count
                    ),
                )
            )

        return cls._finish(
            takeoff=takeoff,
            components=components,
            markup=markup,
        )

    @classmethod
    def price_count(
        cls,
        *,
        takeoff: ElectricalCountTakeoff,
        price_book: PriceBook,
        material_code: str | None,
        labor_code: str | None,
        markup: MarkupPolicy,
    ) -> PricedElectricalScope:
        components = []

        for code in (
            material_code,
            labor_code,
        ):
            if code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=code,
                        unit=PricingUnit.EA,
                        quantity=(
                            takeoff.quantity
                        ),
                    )
                )

        if not components:
            raise ElectricalValidationError(
                "count scope has no pricing recipe"
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

        subtotal = (
            direct
            + overhead
            + contingency
        )

        profit = apply_bps(
            amount_cents=subtotal,
            basis_points=(
                markup.profit_bps
            ),
        )

        return PricedElectricalScope(
            scope_id=(
                takeoff.takeoff_id
            ),
            description=(
                takeoff.description
            ),
            components=tuple(
                components
            ),
            direct_cost_cents=direct,
            overhead_cents=overhead,
            contingency_cents=(
                contingency
            ),
            profit_cents=profit,
            bid_price_cents=(
                subtotal + profit
            ),
            provenance=(
                takeoff.provenance
            ),
            confidence=(
                takeoff.confidence
            ),
            requires_review=(
                takeoff.confidence
                < 0.80
            ),
            findings=(),
        )
