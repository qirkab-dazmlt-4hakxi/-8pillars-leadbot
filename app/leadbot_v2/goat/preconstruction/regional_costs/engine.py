from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Iterable
from uuid import uuid4

from leadbot_v2.goat.preconstruction.pricing.engine import (
    CostClass,
    PriceBook,
    PricingUnit,
    UnitRate,
)


class RegionalCostError(RuntimeError):
    pass


class UnresolvedRateError(RegionalCostError):
    pass


class DuplicateCostRecordError(RegionalCostError):
    pass


class TexasMarket(str, Enum):
    STATEWIDE = "texas_statewide"

    DFW = "dallas_fort_worth"
    HOUSTON = "houston"
    AUSTIN = "austin"
    SAN_ANTONIO = "san_antonio"

    MIDLAND_ODESSA = "midland_odessa"
    EL_PASO = "el_paso"
    CORPUS_CHRISTI = "corpus_christi"
    BEAUMONT_PORT_ARTHUR = (
        "beaumont_port_arthur"
    )

    RIO_GRANDE_VALLEY = (
        "rio_grande_valley"
    )

    LUBBOCK = "lubbock"
    AMARILLO = "amarillo"

    WACO = "waco"
    TEMPLE_KILLEEN = "temple_killeen"

    TYLER_EAST_TEXAS = (
        "tyler_east_texas"
    )


class SourceKind(str, Enum):
    PROJECT_QUOTE = "project_quote"

    NEGOTIATED_COMPANY_RATE = (
        "negotiated_company_rate"
    )

    RSMEANS = "rsmeans"

    PREVAILING_WAGE = (
        "prevailing_wage"
    )

    COMPANY_ACTUAL = "company_actual"

    HISTORICAL_ACTUAL = (
        "historical_actual"
    )

    BLS = "bls"

    PUBLIC_BENCHMARK = (
        "public_benchmark"
    )


class LaborBasis(str, Enum):
    OPEN_SHOP = "open_shop"
    UNION = "union"
    PREVAILING = "prevailing"
    COMPANY_ACTUAL = "company_actual"
    MARKET_BENCHMARK = (
        "market_benchmark"
    )
    UNKNOWN = "unknown"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    FUTURE = "future"


SOURCE_PRIORITY = {
    SourceKind.PROJECT_QUOTE: 100,
    SourceKind.NEGOTIATED_COMPANY_RATE: 90,
    SourceKind.RSMEANS: 80,
    SourceKind.PREVAILING_WAGE: 80,
    SourceKind.COMPANY_ACTUAL: 75,
    SourceKind.HISTORICAL_ACTUAL: 60,
    SourceKind.BLS: 50,
    SourceKind.PUBLIC_BENCHMARK: 40,
}


@dataclass(frozen=True)
class CostRecord:
    record_id: str

    source_kind: SourceKind
    source_name: str
    source_item_id: str | None

    trade: str
    description: str

    csi_division: str | None
    cost_code: str | None

    unit: PricingUnit

    market: TexasMarket

    state: str = "TX"
    city: str | None = None
    county: str | None = None
    postal_code: str | None = None

    material_cents_per_unit: int = 0
    labor_cents_per_unit: int = 0
    equipment_cents_per_unit: int = 0
    subcontract_cents_per_unit: int = 0
    other_cents_per_unit: int = 0

    wage_cents_per_hour: int | None = None
    fringe_cents_per_hour: int | None = None

    labor_basis: LaborBasis = (
        LaborBasis.UNKNOWN
    )

    effective_date: date | None = None
    expires_date: date | None = None

    release_quarter: str | None = None

    verified_at: datetime | None = None

    confidence: float = 1.0

    project_id: str | None = None
    vendor_name: str | None = None

    notes: str = ""

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError(
                "record_id required"
            )

        if not self.source_name.strip():
            raise ValueError(
                "source_name required"
            )

        if not self.trade.strip():
            raise ValueError(
                "trade required"
            )

        if not self.description.strip():
            raise ValueError(
                "description required"
            )

        for value in (
            self.material_cents_per_unit,
            self.labor_cents_per_unit,
            self.equipment_cents_per_unit,
            self.subcontract_cents_per_unit,
            self.other_cents_per_unit,
        ):
            if value < 0:
                raise ValueError(
                    "cost component cannot "
                    "be negative"
                )

        if (
            self.wage_cents_per_hour
            is not None
            and self.wage_cents_per_hour < 0
        ):
            raise ValueError(
                "wage cannot be negative"
            )

        if (
            self.fringe_cents_per_hour
            is not None
            and self.fringe_cents_per_hour < 0
        ):
            raise ValueError(
                "fringe cannot be negative"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence must be 0-1"
            )

        if (
            self.expires_date is not None
            and self.effective_date is not None
            and self.expires_date
            < self.effective_date
        ):
            raise ValueError(
                "expires_date cannot precede "
                "effective_date"
            )

    @property
    def total_cents_per_unit(
        self,
    ) -> int:
        return sum(
            (
                self.material_cents_per_unit,
                self.labor_cents_per_unit,
                self.equipment_cents_per_unit,
                self.subcontract_cents_per_unit,
                self.other_cents_per_unit,
            )
        )

    @property
    def loaded_prevailing_hourly_cents(
        self,
    ) -> int | None:
        if (
            self.wage_cents_per_hour
            is None
            and self.fringe_cents_per_hour
            is None
        ):
            return None

        return (
            self.wage_cents_per_hour or 0
        ) + (
            self.fringe_cents_per_hour or 0
        )

    def component_cents(
        self,
        cost_class: CostClass,
    ) -> int:
        if cost_class == CostClass.MATERIAL:
            return (
                self.material_cents_per_unit
            )

        if cost_class == CostClass.LABOR:
            return (
                self.labor_cents_per_unit
            )

        if cost_class == CostClass.EQUIPMENT:
            return (
                self.equipment_cents_per_unit
            )

        if cost_class == CostClass.SUBCONTRACT:
            return (
                self.subcontract_cents_per_unit
            )

        return (
            self.other_cents_per_unit
        )


@dataclass(frozen=True)
class FreshnessPolicy:
    project_quote_days: int = 30
    negotiated_rate_days: int = 90

    rsmeans_days: int = 125

    company_actual_days: int = 180
    historical_actual_days: int = 730

    bls_days: int = 550

    public_benchmark_days: int = 550

    prevailing_wage_days: int = 370

    def max_age_days(
        self,
        source: SourceKind,
    ) -> int:
        mapping = {
            SourceKind.PROJECT_QUOTE:
                self.project_quote_days,

            SourceKind.NEGOTIATED_COMPANY_RATE:
                self.negotiated_rate_days,

            SourceKind.RSMEANS:
                self.rsmeans_days,

            SourceKind.PREVAILING_WAGE:
                self.prevailing_wage_days,

            SourceKind.COMPANY_ACTUAL:
                self.company_actual_days,

            SourceKind.HISTORICAL_ACTUAL:
                self.historical_actual_days,

            SourceKind.BLS:
                self.bls_days,

            SourceKind.PUBLIC_BENCHMARK:
                self.public_benchmark_days,
        }

        return mapping[source]


@dataclass(frozen=True)
class RateContext:
    market: TexasMarket

    as_of: date

    project_id: str | None = None

    prevailing_wage_required: bool = False

    requested_labor_basis: (
        LaborBasis | None
    ) = None

    allow_statewide_fallback: bool = True

    require_current: bool = True


@dataclass(frozen=True)
class ResolvedRate:
    record: CostRecord

    freshness: FreshnessStatus

    candidates_considered: int

    selection_reason: str

    @property
    def total_cents_per_unit(
        self,
    ) -> int:
        return (
            self.record
            .total_cents_per_unit
        )


@dataclass(frozen=True)
class LaborBurdenModel:
    """
    Company labor burden model.

    Public wage data should NOT be confused with
    the actual internal cost of employing labor.

    This model converts base wage into estimating
    burden while keeping each component explicit.
    """

    base_wage_cents_per_hour: int

    fringe_cents_per_hour: int = 0
    benefits_cents_per_hour: int = 0

    payroll_tax_bps: int = 0
    workers_comp_bps: int = 0

    supervision_bps: int = 0
    small_tools_bps: int = 0

    productivity_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.base_wage_cents_per_hour < 0:
            raise ValueError(
                "base wage cannot be negative"
            )

        if self.fringe_cents_per_hour < 0:
            raise ValueError(
                "fringe cannot be negative"
            )

        if self.benefits_cents_per_hour < 0:
            raise ValueError(
                "benefits cannot be negative"
            )

        for value in (
            self.payroll_tax_bps,
            self.workers_comp_bps,
            self.supervision_bps,
            self.small_tools_bps,
        ):
            if not 0 <= value <= 100_000:
                raise ValueError(
                    "invalid labor burden "
                    "basis points"
                )

        if self.productivity_factor <= 0:
            raise ValueError(
                "productivity factor "
                "must be positive"
            )

    @staticmethod
    def _bps(
        amount: int,
        bps: int,
    ) -> int:
        value = (
            Decimal(amount)
            * Decimal(bps)
            / Decimal(10_000)
        )

        return int(
            value.quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )

    @property
    def loaded_hourly_cents(
        self,
    ) -> int:
        wage = (
            self.base_wage_cents_per_hour
        )

        wage_based = (
            wage
            + self._bps(
                wage,
                self.payroll_tax_bps,
            )
            + self._bps(
                wage,
                self.workers_comp_bps,
            )
            + self._bps(
                wage,
                self.supervision_bps,
            )
            + self._bps(
                wage,
                self.small_tools_bps,
            )
        )

        direct = (
            wage_based
            + self.fringe_cents_per_hour
            + self.benefits_cents_per_hour
        )

        adjusted = (
            Decimal(direct)
            / Decimal(
                str(
                    self.productivity_factor
                )
            )
        )

        return int(
            adjusted.quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )


class TexasMarketRegistry:
    """
    Deterministic Texas metro routing.

    ZIP-level lookup can later be populated from the
    validated regional research dataset.
    """

    _CITY_MAP = {
        # DFW
        "dallas": TexasMarket.DFW,
        "fort worth": TexasMarket.DFW,
        "arlington": TexasMarket.DFW,
        "frisco": TexasMarket.DFW,
        "plano": TexasMarket.DFW,
        "mckinney": TexasMarket.DFW,
        "prosper": TexasMarket.DFW,
        "celina": TexasMarket.DFW,
        "little elm": TexasMarket.DFW,
        "aubrey": TexasMarket.DFW,
        "denton": TexasMarket.DFW,
        "garland": TexasMarket.DFW,
        "irving": TexasMarket.DFW,
        "grand prairie": TexasMarket.DFW,

        # Houston
        "houston": TexasMarket.HOUSTON,
        "pasadena": TexasMarket.HOUSTON,
        "sugar land": TexasMarket.HOUSTON,
        "katy": TexasMarket.HOUSTON,
        "pearland": TexasMarket.HOUSTON,
        "the woodlands": TexasMarket.HOUSTON,

        # Austin
        "austin": TexasMarket.AUSTIN,
        "round rock": TexasMarket.AUSTIN,
        "georgetown": TexasMarket.AUSTIN,
        "pflugerville": TexasMarket.AUSTIN,

        # San Antonio
        "san antonio":
            TexasMarket.SAN_ANTONIO,

        "new braunfels":
            TexasMarket.SAN_ANTONIO,

        # West Texas
        "midland":
            TexasMarket.MIDLAND_ODESSA,

        "odessa":
            TexasMarket.MIDLAND_ODESSA,

        "el paso":
            TexasMarket.EL_PASO,

        # Gulf
        "corpus christi":
            TexasMarket.CORPUS_CHRISTI,

        "beaumont":
            TexasMarket.BEAUMONT_PORT_ARTHUR,

        "port arthur":
            TexasMarket.BEAUMONT_PORT_ARTHUR,

        # Valley
        "mcallen":
            TexasMarket.RIO_GRANDE_VALLEY,

        "brownsville":
            TexasMarket.RIO_GRANDE_VALLEY,

        "edinburg":
            TexasMarket.RIO_GRANDE_VALLEY,

        "harlingen":
            TexasMarket.RIO_GRANDE_VALLEY,

        # Panhandle / plains
        "lubbock":
            TexasMarket.LUBBOCK,

        "amarillo":
            TexasMarket.AMARILLO,

        # Central Texas
        "waco":
            TexasMarket.WACO,

        "temple":
            TexasMarket.TEMPLE_KILLEEN,

        "killeen":
            TexasMarket.TEMPLE_KILLEEN,

        # East Texas
        "tyler":
            TexasMarket.TYLER_EAST_TEXAS,

        "longview":
            TexasMarket.TYLER_EAST_TEXAS,
    }

    @classmethod
    def resolve(
        cls,
        *,
        city: str | None = None,
        explicit_market: (
            TexasMarket | None
        ) = None,
    ) -> TexasMarket:
        if explicit_market is not None:
            return explicit_market

        if not city:
            raise UnresolvedRateError(
                "Texas pricing market unresolved"
            )

        normalized = (
            city.strip()
            .lower()
        )

        try:
            return cls._CITY_MAP[
                normalized
            ]
        except KeyError as exc:
            raise UnresolvedRateError(
                f"Texas pricing market "
                f"not mapped for city: {city}"
            ) from exc


class RegionalCostCatalog:

    def __init__(self) -> None:
        self._records: dict[
            str,
            CostRecord,
        ] = {}

    def register(
        self,
        record: CostRecord,
    ) -> None:
        if record.record_id in self._records:
            raise DuplicateCostRecordError(
                f"duplicate cost record: "
                f"{record.record_id}"
            )

        self._records[
            record.record_id
        ] = record

    def register_many(
        self,
        records: Iterable[
            CostRecord
        ],
    ) -> None:
        for record in records:
            self.register(
                record
            )

    @property
    def records(
        self,
    ) -> tuple[
        CostRecord,
        ...
    ]:
        return tuple(
            self._records.values()
        )

    def query(
        self,
        *,
        trade: str,
        unit: PricingUnit,
        description: str | None = None,
        cost_code: str | None = None,
    ) -> tuple[
        CostRecord,
        ...
    ]:
        normalized_trade = (
            trade.strip().lower()
        )

        results = []

        for record in self._records.values():
            if (
                record.trade
                .strip()
                .lower()
                != normalized_trade
            ):
                continue

            if record.unit != unit:
                continue

            if (
                description is not None
                and record.description
                .strip()
                .lower()
                != description
                .strip()
                .lower()
            ):
                continue

            if (
                cost_code is not None
                and record.cost_code
                != cost_code
            ):
                continue

            results.append(
                record
            )

        return tuple(results)


class RegionalRateResolver:

    def __init__(
        self,
        *,
        catalog: RegionalCostCatalog,
        freshness_policy: (
            FreshnessPolicy | None
        ) = None,
    ) -> None:
        self.catalog = catalog

        self.freshness_policy = (
            freshness_policy
            or FreshnessPolicy()
        )

    def freshness(
        self,
        *,
        record: CostRecord,
        as_of: date,
    ) -> FreshnessStatus:
        if (
            record.effective_date is not None
            and record.effective_date
            > as_of
        ):
            return (
                FreshnessStatus.FUTURE
            )

        if (
            record.expires_date is not None
            and record.expires_date
            < as_of
        ):
            return (
                FreshnessStatus.EXPIRED
            )

        if record.effective_date is None:
            return FreshnessStatus.STALE

        age = (
            as_of
            - record.effective_date
        ).days

        if age < 0:
            return FreshnessStatus.FUTURE

        maximum = (
            self.freshness_policy
            .max_age_days(
                record.source_kind
            )
        )

        if age <= maximum:
            return FreshnessStatus.CURRENT

        return FreshnessStatus.STALE

    @staticmethod
    def _geography_allowed(
        *,
        record: CostRecord,
        context: RateContext,
    ) -> bool:
        if (
            record.market
            == context.market
        ):
            return True

        if (
            context.allow_statewide_fallback
            and record.market
            == TexasMarket.STATEWIDE
        ):
            return True

        return False

    @staticmethod
    def _project_allowed(
        *,
        record: CostRecord,
        context: RateContext,
    ) -> bool:
        if (
            record.source_kind
            != SourceKind.PROJECT_QUOTE
        ):
            return True

        if context.project_id is None:
            return (
                record.project_id is None
            )

        return (
            record.project_id
            == context.project_id
        )

    @staticmethod
    def _labor_allowed(
        *,
        record: CostRecord,
        context: RateContext,
        cost_class: (
            CostClass | None
        ),
    ) -> bool:
        if cost_class != CostClass.LABOR:
            return True

        if context.prevailing_wage_required:
            return (
                record.source_kind
                == SourceKind.PREVAILING_WAGE
                or record.labor_basis
                == LaborBasis.PREVAILING
            )

        if (
            context.requested_labor_basis
            is None
        ):
            return True

        return (
            record.labor_basis
            == context.requested_labor_basis
        )

    def resolve(
        self,
        *,
        trade: str,
        unit: PricingUnit,
        context: RateContext,
        description: str | None = None,
        cost_code: str | None = None,
        cost_class: (
            CostClass | None
        ) = None,
    ) -> ResolvedRate:
        candidates = list(
            self.catalog.query(
                trade=trade,
                unit=unit,
                description=description,
                cost_code=cost_code,
            )
        )

        eligible = []

        for record in candidates:
            if not self._geography_allowed(
                record=record,
                context=context,
            ):
                continue

            if not self._project_allowed(
                record=record,
                context=context,
            ):
                continue

            if not self._labor_allowed(
                record=record,
                context=context,
                cost_class=cost_class,
            ):
                continue

            status = self.freshness(
                record=record,
                as_of=context.as_of,
            )

            if status in {
                FreshnessStatus.EXPIRED,
                FreshnessStatus.FUTURE,
            }:
                continue

            if (
                context.require_current
                and status
                != FreshnessStatus.CURRENT
            ):
                continue

            eligible.append(
                (
                    record,
                    status,
                )
            )

        if not eligible:
            raise UnresolvedRateError(
                "No valid regional pricing rate "
                f"for trade={trade}, "
                f"market={context.market.value}, "
                f"unit={unit.value}"
            )

        def ranking(item):
            record, status = item

            project_exact = (
                1
                if (
                    context.project_id
                    and record.project_id
                    == context.project_id
                )
                else 0
            )

            market_exact = (
                1
                if record.market
                == context.market
                else 0
            )

            source_priority = (
                SOURCE_PRIORITY[
                    record.source_kind
                ]
            )

            effective_ordinal = (
                record.effective_date
                .toordinal()
                if record.effective_date
                else 0
            )

            verified_timestamp = (
                record.verified_at.timestamp()
                if record.verified_at
                else 0.0
            )

            return (
                project_exact,
                source_priority,
                market_exact,
                effective_ordinal,
                record.confidence,
                verified_timestamp,
            )

        eligible.sort(
            key=ranking,
            reverse=True,
        )

        selected, status = eligible[0]

        reason = (
            f"Selected {selected.source_kind.value} "
            f"for {selected.market.value}; "
            f"effective={selected.effective_date}; "
            f"confidence={selected.confidence:.2f}"
        )

        return ResolvedRate(
            record=selected,
            freshness=status,
            candidates_considered=(
                len(eligible)
            ),
            selection_reason=reason,
        )


class RegionalPriceBookBuilder:

    @staticmethod
    def add_component(
        *,
        price_book: PriceBook,
        resolved: ResolvedRate,
        code: str,
        description: str,
        cost_class: CostClass,
    ) -> UnitRate:
        cents = (
            resolved.record
            .component_cents(
                cost_class
            )
        )

        if cents <= 0:
            raise UnresolvedRateError(
                f"resolved source contains no "
                f"{cost_class.value} component"
            )

        source = (
            f"{resolved.record.source_name}"
            f" | {resolved.record.market.value}"
            f" | effective "
            f"{resolved.record.effective_date}"
        )

        rate = UnitRate(
            code=code,
            description=description,
            unit=resolved.record.unit,
            cost_class=cost_class,
            cents_per_unit=cents,
            source=source,
            region=(
                resolved.record.market.value
            ),
            effective_date=(
                resolved.record
                .effective_date.isoformat()
                if resolved.record.effective_date
                else None
            ),
        )

        price_book.register(
            rate
        )

        return rate


def new_cost_record_id() -> str:
    return (
        f"cost_{uuid4().hex}"
    )


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )
