from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any

from leadbot_v2.goat.preconstruction.pricing.engine import (
    MarkupPolicy,
    PricingUnit,
)

from leadbot_v2.goat.preconstruction.regional_costs.engine import (
    RateContext,
    RegionalRateResolver,
    TexasMarketRegistry,
)

from leadbot_v2.goat.preconstruction.semantic.geometry import (
    SemanticCandidate,
    SemanticKind,
    SemanticTakeoff,
)


class PricingIntegrityError(RuntimeError):
    pass


class PricingDisposition(str, Enum):
    PRICED = "priced"

    REVIEW_REQUIRED = (
        "review_required"
    )

    PRICE_UNRESOLVED = (
        "price_unresolved"
    )

    BLOCKED = "blocked"


@dataclass(frozen=True)
class ScopeProvenance:
    source_ref: str

    geometry_ids: tuple[
        str,
        ...
    ]

    text_refs: tuple[
        str,
        ...
    ]

    rate_refs: tuple[
        str,
        ...
    ] = ()


@dataclass(frozen=True)
class RateEvidence:
    record_id: str

    source_kind: str
    source_name: str

    market: str

    city: str | None
    county: str | None
    postal_code: str | None

    trade: str
    cost_code: str
    unit: str

    effective_date: (
        str | None
    )

    expires_date: (
        str | None
    )

    verified_at: (
        str | None
    )

    confidence: float

    freshness_status: str

    material_cents_per_unit: int
    labor_cents_per_unit: int
    equipment_cents_per_unit: int
    subcontract_cents_per_unit: int
    other_cents_per_unit: int

    @property
    def unit_direct_cost_cents(
        self,
    ) -> int:
        return (
            self.material_cents_per_unit
            + self.labor_cents_per_unit
            + self.equipment_cents_per_unit
            + self.subcontract_cents_per_unit
            + self.other_cents_per_unit
        )

    @property
    def source_ref(
        self,
    ) -> str:
        return (
            "rate:"
            f"{self.record_id}:"
            f"{self.source_kind}:"
            f"{self.market}"
        )


@dataclass(frozen=True)
class PricingBasis:
    description: str

    cost_code: str

    trade: str

    quantity: float

    unit: PricingUnit


@dataclass(frozen=True)
class ResolvedSemanticPrice:
    semantic_candidate_id: str

    semantic_kind: SemanticKind

    description: str

    trade: str

    cost_code: str

    quantity: float

    unit: str

    unit_direct_cost_cents: (
        int | None
    )

    direct_cost_cents: (
        int | None
    )

    bid_price_cents: (
        int | None
    )

    disposition: PricingDisposition

    unresolved_reason: (
        str | None
    )

    rate_evidence: (
        RateEvidence | None
    )

    provenance: ScopeProvenance

    confidence: float

    requires_review: bool

    @property
    def has_price(
        self,
    ) -> bool:
        return (
            self.direct_cost_cents
            is not None
            and self.bid_price_cents
            is not None
            and self
            .unit_direct_cost_cents
            is not None
        )

    @property
    def ready_for_estimate(
        self,
    ) -> bool:
        return (
            self.has_price
            and self.disposition
            in {
                PricingDisposition
                .PRICED,

                PricingDisposition
                .REVIEW_REQUIRED,
            }
        )


@dataclass(frozen=True)
class SemanticPricingResult:
    city: str

    market: str

    as_of: date

    scopes: tuple[
        ResolvedSemanticPrice,
        ...
    ]

    @property
    def priced_scopes(
        self,
    ) -> tuple[
        ResolvedSemanticPrice,
        ...
    ]:
        return tuple(
            item
            for item in self.scopes
            if item
            .disposition
            == PricingDisposition
            .PRICED
        )

    @property
    def review_scopes(
        self,
    ) -> tuple[
        ResolvedSemanticPrice,
        ...
    ]:
        return tuple(
            item
            for item in self.scopes
            if item
            .disposition
            == PricingDisposition
            .REVIEW_REQUIRED
        )

    @property
    def unresolved_scopes(
        self,
    ) -> tuple[
        ResolvedSemanticPrice,
        ...
    ]:
        return tuple(
            item
            for item in self.scopes
            if item
            .disposition
            in {
                PricingDisposition
                .PRICE_UNRESOLVED,

                PricingDisposition
                .BLOCKED,
            }
        )

    @property
    def ready_for_submission(
        self,
    ) -> bool:
        return (
            bool(
                self.priced_scopes
            )
            and not self.review_scopes
            and not self
            .unresolved_scopes
        )

    @property
    def direct_cost_cents(
        self,
    ) -> int:
        return sum(
            item.direct_cost_cents
            or 0
            for item
            in self.scopes
        )

    @property
    def bid_price_cents(
        self,
    ) -> int:
        return sum(
            item.bid_price_cents
            or 0
            for item
            in self.scopes
        )


SEMANTIC_DESCRIPTION = {
    SemanticKind.SLAB:
        "Concrete slab",

    SemanticKind.FOOTING:
        "Concrete footing",

    SemanticKind.GRADE_BEAM:
        "Concrete grade beam",

    SemanticKind.CONCRETE_WALL:
        "Cast-in-place concrete wall",

    SemanticKind.TRENCH:
        "Excavation trench",

    SemanticKind.CONDUIT_RUN:
        "Electrical conduit run",

    SemanticKind.PIPE_RUN:
        "Plumbing pipe run",
}


SEMANTIC_COST_CODE = {
    SemanticKind.SLAB:
        "03-3000",

    SemanticKind.FOOTING:
        "03-3000-FTG",

    SemanticKind.GRADE_BEAM:
        "03-3000-GB",

    SemanticKind.CONCRETE_WALL:
        "03-3000-WALL",

    SemanticKind.TRENCH:
        "31-2300",

    SemanticKind.CONDUIT_RUN:
        "26-0533",

    SemanticKind.PIPE_RUN:
        "22-1000",
}


SEMANTIC_TRADE = {
    SemanticKind.SLAB:
        "concrete",

    SemanticKind.FOOTING:
        "concrete",

    SemanticKind.GRADE_BEAM:
        "concrete",

    SemanticKind.CONCRETE_WALL:
        "concrete",

    SemanticKind.TRENCH:
        "earthwork",

    SemanticKind.CONDUIT_RUN:
        "electrical",

    SemanticKind.PIPE_RUN:
        "plumbing",
}


def _enum_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    enum_value = getattr(
        value,
        "value",
        None,
    )

    if enum_value is not None:
        return str(
            enum_value
        )

    return str(
        value
    )


def _date_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    isoformat = getattr(
        value,
        "isoformat",
        None,
    )

    if callable(
        isoformat
    ):
        return str(
            isoformat()
        )

    return str(
        value
    )


def _integer_component(
    record: Any,
    field_name: str,
) -> int:
    if not hasattr(
        record,
        field_name,
    ):
        raise PricingIntegrityError(
            "Resolved rate is missing "
            f"required field: "
            f"{field_name}"
        )

    value = getattr(
        record,
        field_name,
    )

    if isinstance(
        value,
        bool,
    ):
        raise PricingIntegrityError(
            f"{field_name} "
            "cannot be boolean"
        )

    try:
        result = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise PricingIntegrityError(
            f"{field_name} "
            "must be integer cents"
        ) from exc

    if result < 0:
        raise PricingIntegrityError(
            f"{field_name} "
            "cannot be negative"
        )

    return result


def _extract_record(
    resolved: Any,
) -> Any:
    for field_name in (
        "record",
        "selected_record",
        "cost_record",
    ):
        record = getattr(
            resolved,
            field_name,
            None,
        )

        if record is not None:
            return record

    required = (
        "material_cents_per_unit",
        "labor_cents_per_unit",
        "equipment_cents_per_unit",
        "subcontract_cents_per_unit",
        "other_cents_per_unit",
    )

    if all(
        hasattr(
            resolved,
            field_name,
        )
        for field_name
        in required
    ):
        return resolved

    raise PricingIntegrityError(
        "Regional resolver returned "
        "an unsupported rate object."
    )


def _freshness_text(
    resolved: Any,
) -> str:
    freshness = getattr(
        resolved,
        "freshness",
        None,
    )

    if freshness is None:
        freshness = getattr(
            resolved,
            "freshness_status",
            None,
        )

    if freshness is None:
        return "unknown"

    status = getattr(
        freshness,
        "status",
        freshness,
    )

    result = _enum_text(
        status
    ).strip().lower()

    return (
        result
        or "unknown"
    )


def _confidence(
    record: Any,
) -> float:
    value = getattr(
        record,
        "confidence",
        None,
    )

    if value is None:
        return 0.0

    try:
        result = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise PricingIntegrityError(
            "Rate confidence "
            "must be numeric."
        ) from exc

    if not (
        0 <= result <= 1
    ):
        raise PricingIntegrityError(
            "Rate confidence "
            "must be between 0 and 1."
        )

    return result


def _rate_evidence(
    resolved: Any,
    *,
    cost_code: str,
    trade: str,
    unit: PricingUnit,
) -> RateEvidence:
    record = _extract_record(
        resolved
    )

    material = (
        _integer_component(
            record,
            "material_cents_per_unit",
        )
    )

    labor = (
        _integer_component(
            record,
            "labor_cents_per_unit",
        )
    )

    equipment = (
        _integer_component(
            record,
            "equipment_cents_per_unit",
        )
    )

    subcontract = (
        _integer_component(
            record,
            "subcontract_cents_per_unit",
        )
    )

    other = (
        _integer_component(
            record,
            "other_cents_per_unit",
        )
    )

    return RateEvidence(
        record_id=str(
            getattr(
                record,
                "record_id",
                "unknown-rate",
            )
        ),

        source_kind=(
            _enum_text(
                getattr(
                    record,
                    "source_kind",
                    "unknown",
                )
            )
        ),

        source_name=str(
            getattr(
                record,
                "source_name",
                "unknown",
            )
        ),

        market=(
            _enum_text(
                getattr(
                    record,
                    "market",
                    "unknown",
                )
            )
        ),

        city=(
            str(
                getattr(
                    record,
                    "city",
                )
            )
            if getattr(
                record,
                "city",
                None,
            )
            is not None
            else None
        ),

        county=(
            str(
                getattr(
                    record,
                    "county",
                )
            )
            if getattr(
                record,
                "county",
                None,
            )
            is not None
            else None
        ),

        postal_code=(
            str(
                getattr(
                    record,
                    "postal_code",
                )
            )
            if getattr(
                record,
                "postal_code",
                None,
            )
            is not None
            else None
        ),

        trade=trade,

        cost_code=(
            cost_code
        ),

        unit=(
            _enum_text(
                unit
            )
        ),

        effective_date=(
            _date_text(
                getattr(
                    record,
                    "effective_date",
                    None,
                )
            )
        ),

        expires_date=(
            _date_text(
                getattr(
                    record,
                    "expires_date",
                    None,
                )
            )
        ),

        verified_at=(
            _date_text(
                getattr(
                    record,
                    "verified_at",
                    None,
                )
            )
        ),

        confidence=(
            _confidence(
                record
            )
        ),

        freshness_status=(
            _freshness_text(
                resolved
            )
        ),

        material_cents_per_unit=(
            material
        ),

        labor_cents_per_unit=(
            labor
        ),

        equipment_cents_per_unit=(
            equipment
        ),

        subcontract_cents_per_unit=(
            subcontract
        ),

        other_cents_per_unit=(
            other
        ),
    )


def _extend_money(
    quantity: float,
    cents_per_unit: int,
) -> int:
    if quantity <= 0:
        raise PricingIntegrityError(
            "Quantity must be positive."
        )

    if cents_per_unit < 0:
        raise PricingIntegrityError(
            "Unit cost cannot be negative."
        )

    result = (
        Decimal(
            str(
                quantity
            )
        )
        * Decimal(
            cents_per_unit
        )
    )

    return int(
        result.quantize(
            Decimal("1"),
            rounding=(
                ROUND_HALF_UP
            ),
        )
    )


def _basis_point_amount(
    amount_cents: int,
    basis_points: int,
) -> int:
    if basis_points < 0:
        raise PricingIntegrityError(
            "Markup basis points "
            "cannot be negative."
        )

    result = (
        Decimal(
            amount_cents
        )
        * Decimal(
            basis_points
        )
        / Decimal(
            10_000
        )
    )

    return int(
        result.quantize(
            Decimal("1"),
            rounding=(
                ROUND_HALF_UP
            ),
        )
    )


def _bid_price(
    direct_cost_cents: int,
    markup: MarkupPolicy,
) -> int:
    overhead = (
        _basis_point_amount(
            direct_cost_cents,
            int(
                markup.overhead_bps
            ),
        )
    )

    contingency = (
        _basis_point_amount(
            direct_cost_cents,
            int(
                markup
                .contingency_bps
            ),
        )
    )

    profit = (
        _basis_point_amount(
            direct_cost_cents,
            int(
                markup.profit_bps
            ),
        )
    )

    return (
        direct_cost_cents
        + overhead
        + contingency
        + profit
    )


def _pricing_basis(
    candidate: SemanticCandidate,
) -> PricingBasis:
    if (
        candidate.semantic_kind
        == SemanticKind.SLAB
    ):
        if (
            candidate
            .derived_volume_cy
            is None
            or candidate
            .derived_volume_cy
            <= 0
        ):
            raise PricingIntegrityError(
                "Slab pricing requires "
                "validated concrete CY."
            )

        return PricingBasis(
            description=(
                SEMANTIC_DESCRIPTION[
                    SemanticKind.SLAB
                ]
            ),
            cost_code=(
                SEMANTIC_COST_CODE[
                    SemanticKind.SLAB
                ]
            ),
            trade="concrete",
            quantity=(
                candidate
                .derived_volume_cy
            ),
            unit=PricingUnit.CY,
        )

    if (
        candidate.semantic_kind
        not in SEMANTIC_DESCRIPTION
    ):
        raise PricingIntegrityError(
            "Semantic scope has "
            "no approved pricing map."
        )

    if candidate.unit != "LF":
        raise PricingIntegrityError(
            f"{candidate.semantic_kind.value} "
            "requires an approved LF "
            "pricing basis."
        )

    return PricingBasis(
        description=(
            SEMANTIC_DESCRIPTION[
                candidate
                .semantic_kind
            ]
        ),

        cost_code=(
            SEMANTIC_COST_CODE[
                candidate
                .semantic_kind
            ]
        ),

        trade=(
            SEMANTIC_TRADE[
                candidate
                .semantic_kind
            ]
        ),

        quantity=(
            candidate.quantity
        ),

        unit=PricingUnit.LF,
    )


def _provenance(
    candidate: SemanticCandidate,
    rate: (
        RateEvidence | None
    ) = None,
) -> ScopeProvenance:
    text_refs = tuple(
        dict.fromkeys(
            evidence.source_ref
            for evidence
            in candidate.evidence
            if evidence.source_ref
        )
    )

    return ScopeProvenance(
        source_ref=(
            candidate.source_ref
        ),

        geometry_ids=(
            candidate
            .candidate_id,
        ),

        text_refs=(
            text_refs
        ),

        rate_refs=(
            (
                rate.source_ref,
            )
            if rate is not None
            else ()
        ),
    )


class SemanticRegionalPricingService:
    """
    Converts reviewed semantic plan scope into
    geographically resolved, source-backed costs.

    Rules:
      * unresolved semantic scope is never priced
      * review-gated semantic scope is not silently priced
      * missing quantity basis is PRICE_UNRESOLVED
      * rate lookup failures are PRICE_UNRESOLVED
      * stale/expired/future rates are rejected
      * missing rate component fields are rejected
      * zero-dollar aggregate rates are rejected
      * weak/unknown rate confidence requires review
      * all estimate prices retain plan + rate provenance
    """

    def __init__(
        self,
        *,
        resolver: RegionalRateResolver,
        market_registry: (
            TexasMarketRegistry
            | None
        ) = None,
        minimum_rate_confidence: (
            float
        ) = 0.80,
    ) -> None:
        if not (
            0
            <= minimum_rate_confidence
            <= 1
        ):
            raise ValueError(
                "minimum rate confidence "
                "must be 0-1"
            )

        self.resolver = resolver

        self.market_registry = (
            market_registry
            or TexasMarketRegistry()
        )

        self.minimum_rate_confidence = (
            minimum_rate_confidence
        )

    def _blocked_scope(
        self,
        candidate: SemanticCandidate,
        *,
        reason: str,
        disposition: (
            PricingDisposition
        ),
    ) -> ResolvedSemanticPrice:
        description = (
            SEMANTIC_DESCRIPTION.get(
                candidate
                .semantic_kind,
                "Unresolved construction scope",
            )
        )

        cost_code = (
            SEMANTIC_COST_CODE.get(
                candidate
                .semantic_kind,
                "UNRESOLVED",
            )
        )

        trade = (
            SEMANTIC_TRADE.get(
                candidate
                .semantic_kind,
                candidate.trade.value,
            )
        )

        return ResolvedSemanticPrice(
            semantic_candidate_id=(
                candidate
                .candidate_id
            ),

            semantic_kind=(
                candidate
                .semantic_kind
            ),

            description=(
                description
            ),

            trade=trade,

            cost_code=(
                cost_code
            ),

            quantity=(
                candidate.quantity
            ),

            unit=(
                candidate.unit
            ),

            unit_direct_cost_cents=None,

            direct_cost_cents=None,

            bid_price_cents=None,

            disposition=(
                disposition
            ),

            unresolved_reason=(
                reason
            ),

            rate_evidence=None,

            provenance=(
                _provenance(
                    candidate
                )
            ),

            confidence=(
                candidate
                .semantic_confidence
            ),

            requires_review=True,
        )

    def price_candidate(
        self,
        *,
        candidate: SemanticCandidate,
        context: RateContext,
        markup: MarkupPolicy,
    ) -> ResolvedSemanticPrice:
        if (
            candidate.semantic_kind
            == SemanticKind.UNRESOLVED
        ):
            return self._blocked_scope(
                candidate,
                reason=(
                    "SEMANTIC_SCOPE_UNRESOLVED"
                ),
                disposition=(
                    PricingDisposition
                    .BLOCKED
                ),
            )

        if (
            candidate.requires_review
            or not candidate
            .auto_classified
        ):
            return self._blocked_scope(
                candidate,
                reason=(
                    "SEMANTIC_REVIEW_REQUIRED"
                ),
                disposition=(
                    PricingDisposition
                    .REVIEW_REQUIRED
                ),
            )

        try:
            basis = (
                _pricing_basis(
                    candidate
                )
            )

        except PricingIntegrityError as exc:
            return self._blocked_scope(
                candidate,
                reason=(
                    "QUANTITY_BASIS_UNRESOLVED:"
                    f"{exc}"
                ),
                disposition=(
                    PricingDisposition
                    .PRICE_UNRESOLVED
                ),
            )

        try:
            resolved = (
                self.resolver.resolve(
                    trade=(
                        basis.trade
                    ),
                    unit=(
                        basis.unit
                    ),
                    context=context,
                    description=(
                        basis.description
                    ),
                    cost_code=(
                        basis.cost_code
                    ),
                )
            )

        except Exception as exc:
            return self._blocked_scope(
                candidate,
                reason=(
                    "PRICE_UNRESOLVED:"
                    f"{type(exc).__name__}:"
                    f"{exc}"
                ),
                disposition=(
                    PricingDisposition
                    .PRICE_UNRESOLVED
                ),
            )

        try:
            rate = _rate_evidence(
                resolved,
                cost_code=(
                    basis.cost_code
                ),
                trade=(
                    basis.trade
                ),
                unit=(
                    basis.unit
                ),
            )

        except PricingIntegrityError as exc:
            return self._blocked_scope(
                candidate,
                reason=(
                    "RATE_INTEGRITY_FAILURE:"
                    f"{exc}"
                ),
                disposition=(
                    PricingDisposition
                    .PRICE_UNRESOLVED
                ),
            )

        freshness = (
            rate
            .freshness_status
            .lower()
        )

        if freshness in {
            "stale",
            "expired",
            "future",
        }:
            return self._blocked_scope(
                candidate,
                reason=(
                    "RATE_NOT_CURRENT:"
                    f"{freshness}"
                ),
                disposition=(
                    PricingDisposition
                    .PRICE_UNRESOLVED
                ),
            )

        unit_direct = (
            rate
            .unit_direct_cost_cents
        )

        if unit_direct <= 0:
            return self._blocked_scope(
                candidate,
                reason=(
                    "ZERO_OR_EMPTY_RATE"
                ),
                disposition=(
                    PricingDisposition
                    .PRICE_UNRESOLVED
                ),
            )

        direct = _extend_money(
            basis.quantity,
            unit_direct,
        )

        bid = _bid_price(
            direct,
            markup,
        )

        rate_requires_review = (
            rate.confidence
            < self
            .minimum_rate_confidence
            or freshness
            == "unknown"
        )

        combined_confidence = min(
            candidate
            .semantic_confidence,

            candidate
            .measurement_confidence,

            rate.confidence,
        )

        disposition = (
            PricingDisposition
            .REVIEW_REQUIRED
            if rate_requires_review
            else PricingDisposition
            .PRICED
        )

        reason = (
            "RATE_REVIEW_REQUIRED"
            if rate_requires_review
            else None
        )

        return ResolvedSemanticPrice(
            semantic_candidate_id=(
                candidate
                .candidate_id
            ),

            semantic_kind=(
                candidate
                .semantic_kind
            ),

            description=(
                basis.description
            ),

            trade=(
                basis.trade
            ),

            cost_code=(
                basis.cost_code
            ),

            quantity=(
                basis.quantity
            ),

            unit=(
                _enum_text(
                    basis.unit
                )
            ),

            unit_direct_cost_cents=(
                unit_direct
            ),

            direct_cost_cents=(
                direct
            ),

            bid_price_cents=(
                bid
            ),

            disposition=(
                disposition
            ),

            unresolved_reason=(
                reason
            ),

            rate_evidence=(
                rate
            ),

            provenance=(
                _provenance(
                    candidate,
                    rate,
                )
            ),

            confidence=(
                combined_confidence
            ),

            requires_review=(
                rate_requires_review
            ),
        )

    def price_takeoff(
        self,
        *,
        takeoff: SemanticTakeoff,
        city: str,
        as_of: date,
        markup: MarkupPolicy,
        project_id: str | None = None,
        prevailing_wage_required: (
            bool
        ) = False,
        requested_labor_basis: (
            Any | None
        ) = None,
        allow_statewide_fallback: (
            bool
        ) = True,
    ) -> SemanticPricingResult:
        if not city.strip():
            raise ValueError(
                "city required"
            )

        market = (
            self.market_registry
            .resolve(
                city=city,
            )
        )

        context = RateContext(
            market=market,
            as_of=as_of,
            project_id=(
                project_id
            ),
            prevailing_wage_required=(
                prevailing_wage_required
            ),
            requested_labor_basis=(
                requested_labor_basis
            ),
            allow_statewide_fallback=(
                allow_statewide_fallback
            ),
            require_current=True,
        )

        scopes = tuple(
            self.price_candidate(
                candidate=candidate,
                context=context,
                markup=markup,
            )
            for candidate
            in takeoff.candidates
        )

        return SemanticPricingResult(
            city=city,
            market=(
                _enum_text(
                    market
                )
            ),
            as_of=as_of,
            scopes=scopes,
        )


class SemanticEstimateBridge:
    """
    Adds only resolved monetary scope to the
    existing GOAT EstimateWorkflowService.
    """

    @staticmethod
    def add_scope(
        *,
        workflow: Any,
        estimate_id: str,
        actor_id: str,
        scope: ResolvedSemanticPrice,
    ) -> Any:
        if not scope.ready_for_estimate:
            raise PricingIntegrityError(
                "Scope is not eligible "
                "for estimate insertion."
            )

        if (
            scope.direct_cost_cents
            is None
            or scope.bid_price_cents
            is None
        ):
            raise PricingIntegrityError(
                "Resolved scope has "
                "no monetary value."
            )

        refs = tuple(
            dict.fromkeys(
                (
                    scope
                    .provenance
                    .source_ref,

                    *scope
                    .provenance
                    .geometry_ids,

                    *scope
                    .provenance
                    .text_refs,

                    *scope
                    .provenance
                    .rate_refs,
                )
            )
        )

        return (
            workflow
            .add_manual_line(
                estimate_id=(
                    estimate_id
                ),
                actor_id=(
                    actor_id
                ),
                description=(
                    scope.description
                ),
                cost_code=(
                    scope.cost_code
                ),
                quantity=(
                    scope.quantity
                ),
                unit=(
                    scope.unit
                ),
                direct_cost_cents=(
                    scope
                    .direct_cost_cents
                ),
                bid_price_cents=(
                    scope
                    .bid_price_cents
                ),
                source_refs=(
                    refs
                ),
                confidence=(
                    scope.confidence
                ),
                requires_review=(
                    scope
                    .requires_review
                ),
            )
        )

    @classmethod
    def add_result(
        cls,
        *,
        workflow: Any,
        estimate_id: str,
        actor_id: str,
        result: SemanticPricingResult,
    ) -> tuple[
        Any,
        ...
    ]:
        lines = []

        for scope in (
            result.scopes
        ):
            if (
                scope
                .ready_for_estimate
            ):
                lines.append(
                    cls.add_scope(
                        workflow=workflow,
                        estimate_id=(
                            estimate_id
                        ),
                        actor_id=(
                            actor_id
                        ),
                        scope=scope,
                    )
                )

        return tuple(
            lines
        )


class SemanticBidSessionBridge:
    """
    Feeds a resolved semantic scope into an
    already-created GOAT BidSession work item.
    """

    @staticmethod
    def record_scope(
        *,
        bid_service: Any,
        session_id: str,
        work_id: str,
        actor_id: str,
        scope: ResolvedSemanticPrice,
    ) -> Any:
        if not scope.ready_for_estimate:
            raise PricingIntegrityError(
                "Scope cannot enter "
                "Bid Session before "
                "pricing resolution."
            )

        return (
            bid_service
            .record_priced_scope(
                session_id=(
                    session_id
                ),
                work_id=(
                    work_id
                ),
                actor_id=(
                    actor_id
                ),
                priced_scope=(
                    scope
                ),
                cost_code=(
                    scope.cost_code
                ),
            )
        )


class ProjectBudgetHandoffBridge:
    """
    Uses the established estimator workflow
    budget handoff. No parallel accounting path
    is created here.
    """

    @staticmethod
    def handoff(
        *,
        workflow: Any,
        estimate_id: str,
        project_id: str,
        principal: Any,
        finance: Any,
    ) -> Any:
        return (
            workflow
            .handoff_to_project_budget(
                estimate_id=(
                    estimate_id
                ),
                project_id=(
                    project_id
                ),
                principal=(
                    principal
                ),
                finance=finance,
            )
        )
