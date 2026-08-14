from __future__ import annotations

import math
import re

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)
from leadbot_v2.goat.preconstruction.pricing.engine import (
    MarkupPolicy,
    PriceBook,
    PricingComponent,
    PricingUnit,
    apply_bps,
    money_extension,
)


class PlumbingValidationError(ValueError):
    pass


class PlumbingSystem(str, Enum):
    SANITARY = "sanitary"
    DOMESTIC_WATER = "domestic_water"
    STORM = "storm"
    GAS = "gas"
    VENT = "vent"
    UNKNOWN = "unknown"


class PlumbingSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    HIGH = "high"


@dataclass(frozen=True)
class PlumbingRiskFinding:
    severity: PlumbingSeverity
    code: str
    message: str


@dataclass(frozen=True)
class PipeSpecification:
    size_inches: str
    material: str | None
    system: PlumbingSystem
    raw: str
    confidence: float


@dataclass(frozen=True)
class PlumbingRunTakeoff:
    run_id: str

    description: str

    length_ft: float
    pipe: PipeSpecification

    fitting_count: int

    hanger_spacing_ft: float | None
    hanger_count: int

    provenance: GeometryProvenance
    confidence: float

    findings: tuple[
        PlumbingRiskFinding,
        ...
    ]

    @property
    def requires_review(self) -> bool:
        return (
            self.confidence < 0.80
            or any(
                item.severity
                == PlumbingSeverity.HIGH
                for item in self.findings
            )
        )


@dataclass(frozen=True)
class PlumbingFixtureTakeoff:
    takeoff_id: str
    fixture_type: str
    quantity: int
    provenance: GeometryProvenance
    confidence: float


@dataclass(frozen=True)
class PlumbingPricingRecipe:
    pipe_material_code: str
    pipe_labor_code: str

    fitting_material_code: str | None = None
    fitting_labor_code: str | None = None

    hanger_material_code: str | None = None
    hanger_labor_code: str | None = None


@dataclass(frozen=True)
class PricedPlumbingScope:
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
        PlumbingRiskFinding,
        ...
    ]


PIPE_RE = re.compile(
    r"\b(?P<size>"
    r"\d+(?:\.\d+)?"
    r"|\d+\s+\d+/\d+"
    r"|\d+/\d+"
    r")\s*"
    r"[\"”]?\s*"
    r"(?P<material>"
    r"PVC|CPVC|PEX|COPPER|CU|"
    r"CAST\s+IRON|CI|HDPE|"
    r"DUCTILE\s+IRON|DI"
    r")?\s*"
    r"(?P<system>"
    r"SANITARY|SAN|"
    r"DOMESTIC\s+WATER|CW|HW|"
    r"STORM|"
    r"GAS|"
    r"VENT"
    r")?\b",
    re.I,
)


class PlumbingCalloutParser:

    @staticmethod
    def _system(
        value: str | None,
        text: str,
    ) -> PlumbingSystem:
        combined = (
            f"{value or ''} {text}"
            .upper()
        )

        if (
            "SANITARY" in combined
            or re.search(
                r"\bSAN\b",
                combined,
            )
        ):
            return PlumbingSystem.SANITARY

        if (
            "DOMESTIC WATER"
            in combined
            or re.search(
                r"\bCW\b",
                combined,
            )
            or re.search(
                r"\bHW\b",
                combined,
            )
        ):
            return (
                PlumbingSystem
                .DOMESTIC_WATER
            )

        if "STORM" in combined:
            return PlumbingSystem.STORM

        if "GAS" in combined:
            return PlumbingSystem.GAS

        if "VENT" in combined:
            return PlumbingSystem.VENT

        return PlumbingSystem.UNKNOWN

    @staticmethod
    def parse(
        text: str,
    ) -> PipeSpecification | None:
        match = PIPE_RE.search(
            text
        )

        if not match:
            return None

        material = (
            match.group(
                "material"
            )
        )

        if material:
            material = (
                re.sub(
                    r"\s+",
                    " ",
                    material.upper(),
                )
            )

        system = (
            PlumbingCalloutParser
            ._system(
                match.group(
                    "system"
                ),
                text,
            )
        )

        confidence = 0.95

        if not material:
            confidence -= 0.10

        if (
            system
            == PlumbingSystem.UNKNOWN
        ):
            confidence -= 0.15

        return PipeSpecification(
            size_inches=(
                match.group("size")
                .strip()
            ),
            material=material,
            system=system,
            raw=match.group(0),
            confidence=max(
                0.50,
                confidence,
            ),
        )


class PlumbingTakeoffEngine:

    @staticmethod
    def run(
        *,
        description: str,
        length_ft: float,
        pipe: PipeSpecification,
        provenance: GeometryProvenance,
        fitting_count: int = 0,
        hanger_spacing_ft: (
            float | None
        ) = None,
    ) -> PlumbingRunTakeoff:
        if length_ft <= 0:
            raise PlumbingValidationError(
                "pipe length must be positive"
            )

        if fitting_count < 0:
            raise PlumbingValidationError(
                "fitting count cannot be negative"
            )

        if (
            hanger_spacing_ft
            is not None
            and hanger_spacing_ft <= 0
        ):
            raise PlumbingValidationError(
                "hanger spacing must be positive"
            )

        hanger_count = 0

        if hanger_spacing_ft is not None:
            hanger_count = (
                math.ceil(
                    length_ft
                    / hanger_spacing_ft
                )
                + 1
            )

        findings: list[
            PlumbingRiskFinding
        ] = []

        if pipe.material is None:
            findings.append(
                PlumbingRiskFinding(
                    severity=(
                        PlumbingSeverity.REVIEW
                    ),
                    code=(
                        "pipe_material_unresolved"
                    ),
                    message=(
                        "Pipe material was not "
                        "resolved from the drawings."
                    ),
                )
            )

        if (
            pipe.system
            == PlumbingSystem.UNKNOWN
        ):
            findings.append(
                PlumbingRiskFinding(
                    severity=(
                        PlumbingSeverity.HIGH
                    ),
                    code=(
                        "pipe_system_unresolved"
                    ),
                    message=(
                        "Plumbing system type could not "
                        "be determined. Do not finalize "
                        "pricing until verified."
                    ),
                )
            )

        confidence = min(
            pipe.confidence,
            provenance.confidence,
        )

        return PlumbingRunTakeoff(
            run_id=(
                f"plumb_{uuid4().hex}"
            ),
            description=description,
            length_ft=length_ft,
            pipe=pipe,
            fitting_count=(
                fitting_count
            ),
            hanger_spacing_ft=(
                hanger_spacing_ft
            ),
            hanger_count=(
                hanger_count
            ),
            provenance=provenance,
            confidence=confidence,
            findings=tuple(
                findings
            ),
        )

    @staticmethod
    def fixture(
        *,
        fixture_type: str,
        quantity: int,
        provenance: GeometryProvenance,
    ) -> PlumbingFixtureTakeoff:
        if quantity < 1:
            raise PlumbingValidationError(
                "fixture quantity must be >= 1"
            )

        if not fixture_type.strip():
            raise PlumbingValidationError(
                "fixture type required"
            )

        return PlumbingFixtureTakeoff(
            takeoff_id=(
                f"fixture_{uuid4().hex}"
            ),
            fixture_type=(
                fixture_type.strip()
            ),
            quantity=quantity,
            provenance=provenance,
            confidence=(
                provenance.confidence
            ),
        )


class PlumbingPricingEngine:

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
        description: str,
        scope_id: str,
        components: list[
            PricingComponent
        ],
        markup: MarkupPolicy,
        provenance: GeometryProvenance,
        confidence: float,
        requires_review: bool,
        findings,
    ) -> PricedPlumbingScope:
        if not components:
            raise PlumbingValidationError(
                "plumbing scope produced no pricing components"
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

        return PricedPlumbingScope(
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
            bid_price_cents=(
                subtotal + profit
            ),
            provenance=provenance,
            confidence=confidence,
            requires_review=(
                requires_review
            ),
            findings=tuple(
                findings
            ),
        )

    @classmethod
    def price_run(
        cls,
        *,
        takeoff: PlumbingRunTakeoff,
        price_book: PriceBook,
        markup: MarkupPolicy,
        recipe: PlumbingPricingRecipe,
    ) -> PricedPlumbingScope:
        components = [
            cls._component(
                price_book=price_book,
                code=(
                    recipe
                    .pipe_material_code
                ),
                unit=PricingUnit.LF,
                quantity=(
                    takeoff.length_ft
                ),
            ),
            cls._component(
                price_book=price_book,
                code=(
                    recipe
                    .pipe_labor_code
                ),
                unit=PricingUnit.LF,
                quantity=(
                    takeoff.length_ft
                ),
            ),
        ]

        if takeoff.fitting_count > 0:
            if recipe.fitting_material_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .fitting_material_code
                        ),
                        unit=PricingUnit.EA,
                        quantity=(
                            takeoff
                            .fitting_count
                        ),
                    )
                )

            if recipe.fitting_labor_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .fitting_labor_code
                        ),
                        unit=PricingUnit.EA,
                        quantity=(
                            takeoff
                            .fitting_count
                        ),
                    )
                )

        if takeoff.hanger_count > 0:
            if recipe.hanger_material_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .hanger_material_code
                        ),
                        unit=PricingUnit.EA,
                        quantity=(
                            takeoff
                            .hanger_count
                        ),
                    )
                )

            if recipe.hanger_labor_code:
                components.append(
                    cls._component(
                        price_book=(
                            price_book
                        ),
                        code=(
                            recipe
                            .hanger_labor_code
                        ),
                        unit=PricingUnit.EA,
                        quantity=(
                            takeoff
                            .hanger_count
                        ),
                    )
                )

        return cls._finish(
            description=(
                takeoff.description
            ),
            scope_id=(
                takeoff.run_id
            ),
            components=components,
            markup=markup,
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
    def price_fixture(
        cls,
        *,
        takeoff: PlumbingFixtureTakeoff,
        price_book: PriceBook,
        markup: MarkupPolicy,
        material_code: str | None,
        labor_code: str | None,
    ) -> PricedPlumbingScope:
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

        return cls._finish(
            description=(
                takeoff.fixture_type
            ),
            scope_id=(
                takeoff.takeoff_id
            ),
            components=components,
            markup=markup,
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
