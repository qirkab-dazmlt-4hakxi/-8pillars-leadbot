from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    Decimal,
    ROUND_HALF_UP,
)
from enum import Enum

from leadbot_v2.goat.preconstruction.assemblies.structural import (
    AutomatedConcreteAssembly,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)


class PricingError(RuntimeError):
    pass


class MissingRateError(PricingError):
    pass


class DuplicateRateError(PricingError):
    pass


class PricingUnit(str, Enum):
    CY = "CY"
    SF = "SF"
    LF = "LF"
    LB = "LB"
    EA = "EA"
    LS = "LS"
    HOUR = "HOUR"


class CostClass(str, Enum):
    MATERIAL = "material"
    LABOR = "labor"
    EQUIPMENT = "equipment"
    SUBCONTRACT = "subcontract"
    FREIGHT = "freight"
    OTHER = "other"


@dataclass(frozen=True)
class UnitRate:
    code: str
    description: str
    unit: PricingUnit
    cost_class: CostClass
    cents_per_unit: int
    source: str
    region: str = "DFW"
    effective_date: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError(
                "rate code required"
            )

        if not self.description.strip():
            raise ValueError(
                "rate description required"
            )

        if self.cents_per_unit < 0:
            raise ValueError(
                "unit rate cannot be negative"
            )

        if not self.source.strip():
            raise ValueError(
                "rate source required"
            )


class PriceBook:

    def __init__(self) -> None:
        self._rates: dict[
            tuple[str, PricingUnit],
            UnitRate,
        ] = {}

    def register(
        self,
        rate: UnitRate,
    ) -> None:
        key = (
            rate.code,
            rate.unit,
        )

        if key in self._rates:
            raise DuplicateRateError(
                f"duplicate rate: "
                f"{rate.code}/{rate.unit.value}"
            )

        self._rates[key] = rate

    def get(
        self,
        *,
        code: str,
        unit: PricingUnit,
    ) -> UnitRate:
        try:
            return self._rates[
                (
                    code,
                    unit,
                )
            ]
        except KeyError as exc:
            raise MissingRateError(
                f"required pricing rate missing: "
                f"{code}/{unit.value}"
            ) from exc


def money_extension(
    *,
    quantity: float,
    cents_per_unit: int,
) -> int:
    if quantity < 0:
        raise ValueError(
            "quantity cannot be negative"
        )

    if cents_per_unit < 0:
        raise ValueError(
            "rate cannot be negative"
        )

    value = (
        Decimal(str(quantity))
        * Decimal(cents_per_unit)
    )

    return int(
        value.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def apply_bps(
    *,
    amount_cents: int,
    basis_points: int,
) -> int:
    if amount_cents < 0:
        raise ValueError(
            "amount cannot be negative"
        )

    if not 0 <= basis_points <= 100_000:
        raise ValueError(
            "invalid basis points"
        )

    value = (
        Decimal(amount_cents)
        * Decimal(basis_points)
        / Decimal(10_000)
    )

    return int(
        value.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


@dataclass(frozen=True)
class MarkupPolicy:
    overhead_bps: int = 0
    contingency_bps: int = 0
    profit_bps: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.overhead_bps,
            self.contingency_bps,
            self.profit_bps,
        ):
            if not 0 <= value <= 100_000:
                raise ValueError(
                    "invalid markup basis points"
                )


@dataclass(frozen=True)
class PricingComponent:
    rate_code: str
    description: str
    unit: PricingUnit
    cost_class: CostClass
    quantity: float
    cents_per_unit: int
    extension_cents: int
    source: str


@dataclass(frozen=True)
class ConcretePricingRecipe:
    concrete_material_code: str = (
        "CONCRETE_READY_MIX"
    )

    concrete_labor_code: str = (
        "CONCRETE_PLACEMENT_LABOR"
    )

    concrete_equipment_code: (
        str | None
    ) = None

    formwork_code: str | None = (
        "FORMWORK"
    )

    rebar_material_code: str | None = (
        "REBAR_MATERIAL"
    )

    rebar_labor_code: str | None = (
        "REBAR_INSTALL_LABOR"
    )


@dataclass(frozen=True)
class PricedAssembly:
    assembly_id: str
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

    def __post_init__(self) -> None:
        if self.direct_cost_cents < 0:
            raise ValueError(
                "direct cost cannot be negative"
            )

        if self.bid_price_cents < 0:
            raise ValueError(
                "bid price cannot be negative"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence must be 0-1"
            )

        if not self.components:
            raise ValueError(
                "priced assembly requires components"
            )


class ConcreteAssemblyPricingEngine:

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

        extension = money_extension(
            quantity=quantity,
            cents_per_unit=(
                rate.cents_per_unit
            ),
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
            extension_cents=extension,
            source=rate.source,
        )

    @classmethod
    def price(
        cls,
        *,
        assembly: AutomatedConcreteAssembly,
        price_book: PriceBook,
        markup: MarkupPolicy,
        recipe: (
            ConcretePricingRecipe
            | None
        ) = None,
    ) -> PricedAssembly:
        recipe = (
            recipe
            or ConcretePricingRecipe()
        )

        components: list[
            PricingComponent
        ] = []

        concrete_cy = (
            assembly.concrete
            .bid_concrete_cy
        )

        components.append(
            cls._component(
                price_book=price_book,
                code=(
                    recipe
                    .concrete_material_code
                ),
                unit=PricingUnit.CY,
                quantity=concrete_cy,
            )
        )

        components.append(
            cls._component(
                price_book=price_book,
                code=(
                    recipe
                    .concrete_labor_code
                ),
                unit=PricingUnit.CY,
                quantity=concrete_cy,
            )
        )

        if (
            recipe.concrete_equipment_code
            is not None
            and concrete_cy > 0
        ):
            components.append(
                cls._component(
                    price_book=price_book,
                    code=(
                        recipe
                        .concrete_equipment_code
                    ),
                    unit=PricingUnit.CY,
                    quantity=concrete_cy,
                )
            )

        formwork_sf = (
            assembly.concrete.formwork_sf
        )

        if (
            recipe.formwork_code
            is not None
            and formwork_sf > 0
        ):
            components.append(
                cls._component(
                    price_book=price_book,
                    code=(
                        recipe.formwork_code
                    ),
                    unit=PricingUnit.SF,
                    quantity=formwork_sf,
                )
            )

        if assembly.rebar is not None:
            rebar_lb = (
                assembly.rebar
                .total_weight_lb
            )

            if (
                recipe.rebar_material_code
                is not None
            ):
                components.append(
                    cls._component(
                        price_book=price_book,
                        code=(
                            recipe
                            .rebar_material_code
                        ),
                        unit=PricingUnit.LB,
                        quantity=rebar_lb,
                    )
                )

            if (
                recipe.rebar_labor_code
                is not None
            ):
                components.append(
                    cls._component(
                        price_book=price_book,
                        code=(
                            recipe
                            .rebar_labor_code
                        ),
                        unit=PricingUnit.LB,
                        quantity=rebar_lb,
                    )
                )

        direct = sum(
            component.extension_cents
            for component in components
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
            amount_cents=before_profit,
            basis_points=(
                markup.profit_bps
            ),
        )

        total = (
            before_profit
            + profit
        )

        return PricedAssembly(
            assembly_id=(
                assembly.concrete.takeoff_id
            ),
            description=(
                assembly.concrete.description
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
            bid_price_cents=total,
            provenance=(
                assembly.concrete.provenance
            ),
            confidence=min(
                assembly.concrete.confidence,
                assembly.candidate.confidence,
            ),
            requires_review=(
                assembly.requires_review
            ),
        )


class EstimatePackage:

    def __init__(
        self,
        *,
        estimate_id: str,
    ) -> None:
        if not estimate_id.strip():
            raise ValueError(
                "estimate_id required"
            )

        self.estimate_id = estimate_id

        self._assemblies: dict[
            str,
            PricedAssembly,
        ] = {}

    def add(
        self,
        assembly: PricedAssembly,
    ) -> None:
        if (
            assembly.assembly_id
            in self._assemblies
        ):
            raise ValueError(
                "duplicate priced assembly"
            )

        self._assemblies[
            assembly.assembly_id
        ] = assembly

    @property
    def assemblies(
        self,
    ) -> tuple[
        PricedAssembly,
        ...
    ]:
        return tuple(
            self._assemblies.values()
        )

    @property
    def direct_cost_cents(
        self,
    ) -> int:
        return sum(
            item.direct_cost_cents
            for item
            in self._assemblies.values()
        )

    @property
    def bid_price_cents(
        self,
    ) -> int:
        return sum(
            item.bid_price_cents
            for item
            in self._assemblies.values()
        )

    @property
    def requires_review(
        self,
    ) -> bool:
        return any(
            item.requires_review
            for item
            in self._assemblies.values()
        )
