from __future__ import annotations

import hashlib
import json

from dataclasses import (
    asdict,
    dataclass,
    replace,
)
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.access_control import (
    EXECUTIVE_ROLES,
    Principal,
)
from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)
from leadbot_v2.goat.finance.project_finance import (
    ProjectFinanceService,
)
from leadbot_v2.goat.preconstruction.pricing.engine import (
    PricedAssembly,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class EstimateWorkflowError(RuntimeError):
    pass


class EstimateAuthorizationError(
    PermissionError
):
    pass


class EstimateIntegrityError(RuntimeError):
    pass


class EstimateStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    LOCKED = "locked"
    SUBMITTED = "submitted"
    AWARDED = "awarded"
    LOST = "lost"


class RFIImpactStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class EstimateLine:
    line_id: str
    description: str
    cost_code: str
    quantity: float
    unit: str
    direct_cost_cents: int
    bid_price_cents: int
    source_refs: tuple[str, ...]
    confidence: float = 1.0
    requires_review: bool = False

    def __post_init__(self) -> None:
        if not self.line_id.strip():
            raise ValueError(
                "line_id required"
            )

        if not self.description.strip():
            raise ValueError(
                "description required"
            )

        if not self.cost_code.strip():
            raise ValueError(
                "cost_code required"
            )

        if self.quantity < 0:
            raise ValueError(
                "quantity cannot be negative"
            )

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


@dataclass(frozen=True)
class EstimateAllowance:
    allowance_id: str
    description: str
    cost_code: str
    direct_cost_cents: int
    bid_price_cents: int
    reason: str

    def __post_init__(self) -> None:
        if self.direct_cost_cents < 0:
            raise ValueError(
                "allowance direct cost cannot be negative"
            )

        if self.bid_price_cents < 0:
            raise ValueError(
                "allowance price cannot be negative"
            )

        if not self.reason.strip():
            raise ValueError(
                "allowance reason required"
            )


@dataclass(frozen=True)
class EstimateAlternate:
    alternate_id: str
    description: str
    cost_code: str
    direct_cost_cents: int
    bid_price_cents: int
    additive: bool = True

    def __post_init__(self) -> None:
        if self.direct_cost_cents < 0:
            raise ValueError(
                "alternate direct cost cannot be negative"
            )

        if self.bid_price_cents < 0:
            raise ValueError(
                "alternate price cannot be negative"
            )


@dataclass(frozen=True)
class EstimateExclusion:
    exclusion_id: str
    description: str
    reason: str

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError(
                "exclusion description required"
            )

        if not self.reason.strip():
            raise ValueError(
                "exclusion reason required"
            )


@dataclass(frozen=True)
class RFIEffect:
    rfi_id: str
    description: str
    cost_code: str
    cost_delta_cents: int
    price_delta_cents: int
    blocking: bool
    status: RFIImpactStatus
    resolution_note: str | None = None

    @property
    def resolved(self) -> bool:
        return (
            self.status
            == RFIImpactStatus.RESOLVED
        )


@dataclass(frozen=True)
class EstimatorOverride:
    override_id: str
    line_id: str
    actor_id: str
    reason: str

    original_direct_cost_cents: int
    new_direct_cost_cents: int

    original_bid_price_cents: int
    new_bid_price_cents: int

    created_at: datetime

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(
                "override reason required"
            )


@dataclass(frozen=True)
class EstimateApproval:
    approval_id: str
    approved_by: str
    approved_at: datetime
    note: str


@dataclass(frozen=True)
class EstimateVersion:
    estimate_id: str
    version_id: str
    version_number: int
    tenant_id: str
    project_name: str
    business_unit_id: str

    status: EstimateStatus
    created_at: datetime
    created_by: str

    parent_version_id: str | None = None

    lines: tuple[
        EstimateLine,
        ...
    ] = ()

    allowances: tuple[
        EstimateAllowance,
        ...
    ] = ()

    alternates: tuple[
        EstimateAlternate,
        ...
    ] = ()

    exclusions: tuple[
        EstimateExclusion,
        ...
    ] = ()

    qualifications: tuple[
        str,
        ...
    ] = ()

    rfi_effects: tuple[
        RFIEffect,
        ...
    ] = ()

    overrides: tuple[
        EstimatorOverride,
        ...
    ] = ()

    approvals: tuple[
        EstimateApproval,
        ...
    ] = ()

    accepted_alternate_ids: tuple[
        str,
        ...
    ] = ()

    version_hash: str = ""

    @property
    def resolved_rfi_cost_delta_cents(
        self,
    ) -> int:
        return sum(
            item.cost_delta_cents
            for item in self.rfi_effects
            if item.resolved
        )

    @property
    def resolved_rfi_price_delta_cents(
        self,
    ) -> int:
        return sum(
            item.price_delta_cents
            for item in self.rfi_effects
            if item.resolved
        )

    @property
    def base_direct_cost_cents(
        self,
    ) -> int:
        return (
            sum(
                line.direct_cost_cents
                for line in self.lines
            )
            + sum(
                item.direct_cost_cents
                for item in self.allowances
            )
            + self.resolved_rfi_cost_delta_cents
        )

    @property
    def base_bid_price_cents(
        self,
    ) -> int:
        return (
            sum(
                line.bid_price_cents
                for line in self.lines
            )
            + sum(
                item.bid_price_cents
                for item in self.allowances
            )
            + self.resolved_rfi_price_delta_cents
        )

    @property
    def open_blocking_rfis(
        self,
    ) -> tuple[
        RFIEffect,
        ...
    ]:
        return tuple(
            item
            for item in self.rfi_effects
            if (
                item.blocking
                and not item.resolved
            )
        )

    @property
    def review_line_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            line.line_id
            for line in self.lines
            if line.requires_review
        )

    @property
    def accepted_alternate_direct_cost_cents(
        self,
    ) -> int:
        accepted = set(
            self.accepted_alternate_ids
        )

        return sum(
            item.direct_cost_cents
            for item in self.alternates
            if item.alternate_id in accepted
        )

    @property
    def accepted_alternate_bid_price_cents(
        self,
    ) -> int:
        accepted = set(
            self.accepted_alternate_ids
        )

        return sum(
            item.bid_price_cents
            for item in self.alternates
            if item.alternate_id in accepted
        )

    @property
    def awarded_direct_cost_cents(
        self,
    ) -> int:
        return (
            self.base_direct_cost_cents
            + self.accepted_alternate_direct_cost_cents
        )

    @property
    def awarded_bid_price_cents(
        self,
    ) -> int:
        return (
            self.base_bid_price_cents
            + self.accepted_alternate_bid_price_cents
        )


@dataclass(frozen=True)
class ProposalSnapshot:
    estimate_id: str
    version_id: str
    version_number: int
    project_name: str

    base_bid_price_cents: int
    alternates: tuple[
        EstimateAlternate,
        ...
    ]

    allowances: tuple[
        EstimateAllowance,
        ...
    ]

    exclusions: tuple[
        EstimateExclusion,
        ...
    ]

    qualifications: tuple[
        str,
        ...
    ]

    generated_at: datetime
    content_hash: str


@dataclass(frozen=True)
class BudgetHandoffResult:
    estimate_id: str
    version_id: str
    project_id: str
    budget_by_cost_code: tuple[
        tuple[str, int],
        ...
    ]
    total_budget_cents: int


def _json_default(value):
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


def calculate_version_hash(
    version: EstimateVersion,
) -> str:
    payload = asdict(
        version
    )

    payload.pop(
        "version_hash",
        None,
    )

    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode()

    return hashlib.sha256(
        raw
    ).hexdigest()


class EstimateWorkflowService:
    """
    High-assurance estimate lifecycle.

    Drafts may be edited.
    Approved/locked/submitted estimates cannot be silently changed.
    Changes after approval require a new estimate revision.
    """

    def __init__(
        self,
        *,
        spine: InMemoryDataSpine,
    ) -> None:
        self.spine = spine

        self._versions: dict[
            str,
            EstimateVersion,
        ] = {}

        self._estimate_versions: dict[
            str,
            list[str],
        ] = {}

        self._current: dict[
            str,
            str,
        ] = {}

        self._budget_handoffs: set[
            tuple[str, str]
        ] = set()

    def _seal(
        self,
        version: EstimateVersion,
    ) -> EstimateVersion:
        unsigned = replace(
            version,
            version_hash="",
        )

        return replace(
            unsigned,
            version_hash=(
                calculate_version_hash(
                    unsigned
                )
            ),
        )

    def _store(
        self,
        version: EstimateVersion,
    ) -> EstimateVersion:
        sealed = self._seal(
            version
        )

        self._versions[
            sealed.version_id
        ] = sealed

        self._current[
            sealed.estimate_id
        ] = sealed.version_id

        return sealed

    def _event(
        self,
        *,
        version: EstimateVersion,
        event_type: str,
        actor_id: str,
        payload: dict | None = None,
    ) -> None:
        self.spine.append_event(
            tenant_id=version.tenant_id,
            aggregate_type="Estimate",
            aggregate_id=version.estimate_id,
            event_type=event_type,
            actor_id=actor_id,
            payload={
                "version_id":
                    version.version_id,
                "version_number":
                    version.version_number,
                **(payload or {}),
            },
        )

    @staticmethod
    def _require_draft(
        version: EstimateVersion,
    ) -> None:
        if version.status != EstimateStatus.DRAFT:
            raise EstimateWorkflowError(
                "estimate version is not editable"
            )

    @staticmethod
    def _require_executive(
        principal: Principal,
    ) -> None:
        if principal.role not in EXECUTIVE_ROLES:
            raise EstimateAuthorizationError(
                "executive approval required"
            )

    def create_estimate(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        project_name: str,
        actor_id: str,
    ) -> EstimateVersion:
        estimate_id = new_id(
            "estimate"
        )

        version = EstimateVersion(
            estimate_id=estimate_id,
            version_id=new_id(
                "estver"
            ),
            version_number=1,
            tenant_id=tenant_id,
            project_name=(
                project_name.strip()
            ),
            business_unit_id=(
                business_unit_id
            ),
            status=EstimateStatus.DRAFT,
            created_at=utc_now(),
            created_by=actor_id,
        )

        sealed = self._seal(
            version
        )

        self._versions[
            sealed.version_id
        ] = sealed

        self._estimate_versions[
            estimate_id
        ] = [
            sealed.version_id
        ]

        self._current[
            estimate_id
        ] = sealed.version_id

        self._event(
            version=sealed,
            event_type=(
                "estimate.created"
            ),
            actor_id=actor_id,
        )

        return sealed

    def get_version(
        self,
        version_id: str,
    ) -> EstimateVersion:
        try:
            return self._versions[
                version_id
            ]
        except KeyError as exc:
            raise KeyError(
                f"estimate version not found: "
                f"{version_id}"
            ) from exc

    def current_version(
        self,
        estimate_id: str,
    ) -> EstimateVersion:
        try:
            version_id = self._current[
                estimate_id
            ]
        except KeyError as exc:
            raise KeyError(
                f"estimate not found: "
                f"{estimate_id}"
            ) from exc

        return self.get_version(
            version_id
        )

    def verify_integrity(
        self,
        version_id: str,
    ) -> bool:
        version = self.get_version(
            version_id
        )

        return (
            calculate_version_hash(
                version
            )
            == version.version_hash
        )

    def add_manual_line(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        description: str,
        cost_code: str,
        quantity: float,
        unit: str,
        direct_cost_cents: int,
        bid_price_cents: int,
        source_refs: tuple[
            str,
            ...
        ] = (),
        confidence: float = 1.0,
        requires_review: bool = False,
    ) -> EstimateLine:
        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        line = EstimateLine(
            line_id=new_id(
                "line"
            ),
            description=description,
            cost_code=cost_code,
            quantity=quantity,
            unit=unit,
            direct_cost_cents=(
                direct_cost_cents
            ),
            bid_price_cents=(
                bid_price_cents
            ),
            source_refs=source_refs,
            confidence=confidence,
            requires_review=(
                requires_review
            ),
        )

        updated = self._store(
            replace(
                version,
                lines=(
                    version.lines
                    + (line,)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.line.added"
            ),
            actor_id=actor_id,
            payload={
                "line_id": line.line_id,
                "cost_code": cost_code,
            },
        )

        return line

    def add_priced_assembly(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        assembly: PricedAssembly,
        cost_code: str,
    ) -> EstimateLine:
        refs = (
            assembly.provenance.source_ref,
            *assembly.provenance.geometry_ids,
            *assembly.provenance.text_refs,
        )

        return self.add_manual_line(
            estimate_id=estimate_id,
            actor_id=actor_id,
            description=(
                assembly.description
            ),
            cost_code=cost_code,
            quantity=1.0,
            unit="LS",
            direct_cost_cents=(
                assembly.direct_cost_cents
            ),
            bid_price_cents=(
                assembly.bid_price_cents
            ),
            source_refs=tuple(
                dict.fromkeys(refs)
            ),
            confidence=(
                assembly.confidence
            ),
            requires_review=(
                assembly.requires_review
            ),
        )

    def add_allowance(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        description: str,
        cost_code: str,
        direct_cost_cents: int,
        bid_price_cents: int,
        reason: str,
    ) -> EstimateAllowance:
        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        item = EstimateAllowance(
            allowance_id=new_id(
                "allow"
            ),
            description=description,
            cost_code=cost_code,
            direct_cost_cents=(
                direct_cost_cents
            ),
            bid_price_cents=(
                bid_price_cents
            ),
            reason=reason,
        )

        updated = self._store(
            replace(
                version,
                allowances=(
                    version.allowances
                    + (item,)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.allowance.added"
            ),
            actor_id=actor_id,
            payload={
                "allowance_id":
                    item.allowance_id,
            },
        )

        return item

    def add_alternate(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        description: str,
        cost_code: str,
        direct_cost_cents: int,
        bid_price_cents: int,
        additive: bool = True,
    ) -> EstimateAlternate:
        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        item = EstimateAlternate(
            alternate_id=new_id(
                "alt"
            ),
            description=description,
            cost_code=cost_code,
            direct_cost_cents=(
                direct_cost_cents
            ),
            bid_price_cents=(
                bid_price_cents
            ),
            additive=additive,
        )

        updated = self._store(
            replace(
                version,
                alternates=(
                    version.alternates
                    + (item,)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.alternate.added"
            ),
            actor_id=actor_id,
            payload={
                "alternate_id":
                    item.alternate_id,
            },
        )

        return item

    def add_exclusion(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        description: str,
        reason: str,
    ) -> EstimateExclusion:
        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        item = EstimateExclusion(
            exclusion_id=new_id(
                "exclude"
            ),
            description=description,
            reason=reason,
        )

        updated = self._store(
            replace(
                version,
                exclusions=(
                    version.exclusions
                    + (item,)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.exclusion.added"
            ),
            actor_id=actor_id,
            payload={
                "exclusion_id":
                    item.exclusion_id,
            },
        )

        return item

    def add_qualification(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        text: str,
    ) -> None:
        if not text.strip():
            raise ValueError(
                "qualification required"
            )

        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        updated = self._store(
            replace(
                version,
                qualifications=(
                    version.qualifications
                    + (text.strip(),)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.qualification.added"
            ),
            actor_id=actor_id,
        )

    def add_rfi_effect(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        rfi_id: str,
        description: str,
        cost_code: str,
        cost_delta_cents: int,
        price_delta_cents: int,
        blocking: bool,
    ) -> RFIEffect:
        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        if any(
            item.rfi_id == rfi_id
            for item in version.rfi_effects
        ):
            raise EstimateWorkflowError(
                "RFI already linked to estimate"
            )

        effect = RFIEffect(
            rfi_id=rfi_id,
            description=description,
            cost_code=cost_code,
            cost_delta_cents=(
                cost_delta_cents
            ),
            price_delta_cents=(
                price_delta_cents
            ),
            blocking=blocking,
            status=RFIImpactStatus.OPEN,
        )

        updated = self._store(
            replace(
                version,
                rfi_effects=(
                    version.rfi_effects
                    + (effect,)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.rfi.linked"
            ),
            actor_id=actor_id,
            payload={
                "rfi_id": rfi_id,
                "blocking": blocking,
            },
        )

        return effect

    def resolve_rfi_effect(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        rfi_id: str,
        resolution_note: str,
        final_cost_delta_cents: (
            int | None
        ) = None,
        final_price_delta_cents: (
            int | None
        ) = None,
    ) -> RFIEffect:
        if not resolution_note.strip():
            raise ValueError(
                "RFI resolution note required"
            )

        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        found = None
        updated_effects = []

        for item in version.rfi_effects:
            if item.rfi_id != rfi_id:
                updated_effects.append(
                    item
                )
                continue

            if item.resolved:
                raise EstimateWorkflowError(
                    "RFI impact already resolved"
                )

            found = replace(
                item,
                cost_delta_cents=(
                    final_cost_delta_cents
                    if final_cost_delta_cents
                    is not None
                    else item.cost_delta_cents
                ),
                price_delta_cents=(
                    final_price_delta_cents
                    if final_price_delta_cents
                    is not None
                    else item.price_delta_cents
                ),
                status=(
                    RFIImpactStatus.RESOLVED
                ),
                resolution_note=(
                    resolution_note.strip()
                ),
            )

            updated_effects.append(
                found
            )

        if found is None:
            raise KeyError(
                f"RFI not found: {rfi_id}"
            )

        updated = self._store(
            replace(
                version,
                rfi_effects=tuple(
                    updated_effects
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.rfi.resolved"
            ),
            actor_id=actor_id,
            payload={
                "rfi_id": rfi_id,
            },
        )

        return found

    def override_line(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        line_id: str,
        reason: str,
        new_direct_cost_cents: (
            int | None
        ) = None,
        new_bid_price_cents: (
            int | None
        ) = None,
    ) -> EstimatorOverride:
        if not reason.strip():
            raise ValueError(
                "override reason required"
            )

        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        new_lines = []
        target = None

        for line in version.lines:
            if line.line_id != line_id:
                new_lines.append(
                    line
                )
                continue

            target = line

            direct = (
                new_direct_cost_cents
                if new_direct_cost_cents
                is not None
                else line.direct_cost_cents
            )

            bid = (
                new_bid_price_cents
                if new_bid_price_cents
                is not None
                else line.bid_price_cents
            )

            if direct < 0 or bid < 0:
                raise ValueError(
                    "override cannot create "
                    "negative pricing"
                )

            if (
                direct
                == line.direct_cost_cents
                and bid
                == line.bid_price_cents
            ):
                raise ValueError(
                    "override must change a value"
                )

            new_lines.append(
                replace(
                    line,
                    direct_cost_cents=direct,
                    bid_price_cents=bid,
                )
            )

        if target is None:
            raise KeyError(
                f"estimate line not found: "
                f"{line_id}"
            )

        override = EstimatorOverride(
            override_id=new_id(
                "override"
            ),
            line_id=line_id,
            actor_id=actor_id,
            reason=reason.strip(),
            original_direct_cost_cents=(
                target.direct_cost_cents
            ),
            new_direct_cost_cents=(
                new_direct_cost_cents
                if new_direct_cost_cents
                is not None
                else target.direct_cost_cents
            ),
            original_bid_price_cents=(
                target.bid_price_cents
            ),
            new_bid_price_cents=(
                new_bid_price_cents
                if new_bid_price_cents
                is not None
                else target.bid_price_cents
            ),
            created_at=utc_now(),
        )

        updated = self._store(
            replace(
                version,
                lines=tuple(
                    new_lines
                ),
                overrides=(
                    version.overrides
                    + (override,)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.line.overridden"
            ),
            actor_id=actor_id,
            payload={
                "line_id": line_id,
                "override_id":
                    override.override_id,
            },
        )

        return override

    def approve(
        self,
        *,
        estimate_id: str,
        principal: Principal,
        note: str = "",
    ) -> EstimateVersion:
        self._require_executive(
            principal
        )

        version = self.current_version(
            estimate_id
        )

        self._require_draft(
            version
        )

        if (
            principal.tenant_id
            != version.tenant_id
        ):
            raise EstimateAuthorizationError(
                "cross-tenant estimate approval denied"
            )

        if version.open_blocking_rfis:
            raise EstimateWorkflowError(
                "blocking RFIs must be resolved "
                "before approval"
            )

        if version.review_line_ids:
            raise EstimateWorkflowError(
                "estimate contains lines requiring "
                "estimator review"
            )

        if not version.lines:
            raise EstimateWorkflowError(
                "estimate has no priced lines"
            )

        approval = EstimateApproval(
            approval_id=new_id(
                "approval"
            ),
            approved_by=(
                principal.user_id
            ),
            approved_at=utc_now(),
            note=note.strip(),
        )

        updated = self._store(
            replace(
                version,
                status=(
                    EstimateStatus.APPROVED
                ),
                approvals=(
                    version.approvals
                    + (approval,)
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.approved"
            ),
            actor_id=principal.user_id,
        )

        return updated

    def lock(
        self,
        *,
        estimate_id: str,
        principal: Principal,
    ) -> EstimateVersion:
        self._require_executive(
            principal
        )

        version = self.current_version(
            estimate_id
        )

        if (
            version.status
            != EstimateStatus.APPROVED
        ):
            raise EstimateWorkflowError(
                "only approved estimates can be locked"
            )

        updated = self._store(
            replace(
                version,
                status=(
                    EstimateStatus.LOCKED
                ),
            )
        )

        self._event(
            version=updated,
            event_type="estimate.locked",
            actor_id=principal.user_id,
        )

        return updated

    def submit(
        self,
        *,
        estimate_id: str,
        principal: Principal,
    ) -> EstimateVersion:
        self._require_executive(
            principal
        )

        version = self.current_version(
            estimate_id
        )

        if (
            version.status
            != EstimateStatus.LOCKED
        ):
            raise EstimateWorkflowError(
                "estimate must be locked "
                "before submission"
            )

        updated = self._store(
            replace(
                version,
                status=(
                    EstimateStatus.SUBMITTED
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.submitted"
            ),
            actor_id=principal.user_id,
        )

        return updated

    def award(
        self,
        *,
        estimate_id: str,
        principal: Principal,
        accepted_alternate_ids: tuple[
            str,
            ...
        ] = (),
    ) -> EstimateVersion:
        self._require_executive(
            principal
        )

        version = self.current_version(
            estimate_id
        )

        if (
            version.status
            != EstimateStatus.SUBMITTED
        ):
            raise EstimateWorkflowError(
                "only submitted estimates "
                "can be awarded"
            )

        valid = {
            item.alternate_id
            for item in version.alternates
        }

        unknown = (
            set(
                accepted_alternate_ids
            )
            - valid
        )

        if unknown:
            raise EstimateWorkflowError(
                "unknown accepted alternate(s): "
                + ", ".join(
                    sorted(unknown)
                )
            )

        updated = self._store(
            replace(
                version,
                status=(
                    EstimateStatus.AWARDED
                ),
                accepted_alternate_ids=tuple(
                    dict.fromkeys(
                        accepted_alternate_ids
                    )
                ),
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.awarded"
            ),
            actor_id=principal.user_id,
            payload={
                "accepted_alternate_ids":
                    list(
                        updated
                        .accepted_alternate_ids
                    ),
            },
        )

        return updated

    def mark_lost(
        self,
        *,
        estimate_id: str,
        principal: Principal,
        reason: str,
    ) -> EstimateVersion:
        self._require_executive(
            principal
        )

        if not reason.strip():
            raise ValueError(
                "lost reason required"
            )

        version = self.current_version(
            estimate_id
        )

        if (
            version.status
            != EstimateStatus.SUBMITTED
        ):
            raise EstimateWorkflowError(
                "only submitted estimate "
                "can be marked lost"
            )

        updated = self._store(
            replace(
                version,
                status=EstimateStatus.LOST,
            )
        )

        self._event(
            version=updated,
            event_type=(
                "estimate.lost"
            ),
            actor_id=principal.user_id,
            payload={
                "reason": reason.strip()
            },
        )

        return updated

    def create_revision(
        self,
        *,
        estimate_id: str,
        actor_id: str,
    ) -> EstimateVersion:
        current = self.current_version(
            estimate_id
        )

        if current.status == EstimateStatus.DRAFT:
            raise EstimateWorkflowError(
                "current estimate is already editable"
            )

        if current.status == EstimateStatus.AWARDED:
            raise EstimateWorkflowError(
                "awarded estimate changes belong "
                "in project change-order workflow"
            )

        revision = EstimateVersion(
            estimate_id=current.estimate_id,
            version_id=new_id(
                "estver"
            ),
            version_number=(
                current.version_number
                + 1
            ),
            tenant_id=current.tenant_id,
            project_name=(
                current.project_name
            ),
            business_unit_id=(
                current.business_unit_id
            ),
            status=EstimateStatus.DRAFT,
            created_at=utc_now(),
            created_by=actor_id,
            parent_version_id=(
                current.version_id
            ),
            lines=current.lines,
            allowances=current.allowances,
            alternates=current.alternates,
            exclusions=current.exclusions,
            qualifications=(
                current.qualifications
            ),
            rfi_effects=current.rfi_effects,
            overrides=current.overrides,
        )

        sealed = self._seal(
            revision
        )

        self._versions[
            sealed.version_id
        ] = sealed

        self._estimate_versions[
            estimate_id
        ].append(
            sealed.version_id
        )

        self._current[
            estimate_id
        ] = sealed.version_id

        self._event(
            version=sealed,
            event_type=(
                "estimate.revision.created"
            ),
            actor_id=actor_id,
            payload={
                "parent_version_id":
                    current.version_id,
            },
        )

        return sealed

    def proposal_snapshot(
        self,
        *,
        estimate_id: str,
    ) -> ProposalSnapshot:
        version = self.current_version(
            estimate_id
        )

        if version.status not in {
            EstimateStatus.LOCKED,
            EstimateStatus.SUBMITTED,
            EstimateStatus.AWARDED,
        }:
            raise EstimateWorkflowError(
                "proposal requires locked "
                "estimate content"
            )

        return ProposalSnapshot(
            estimate_id=(
                version.estimate_id
            ),
            version_id=(
                version.version_id
            ),
            version_number=(
                version.version_number
            ),
            project_name=(
                version.project_name
            ),
            base_bid_price_cents=(
                version.base_bid_price_cents
            ),
            alternates=version.alternates,
            allowances=version.allowances,
            exclusions=version.exclusions,
            qualifications=(
                version.qualifications
            ),
            generated_at=utc_now(),
            content_hash=(
                version.version_hash
            ),
        )

    def handoff_to_project_budget(
        self,
        *,
        estimate_id: str,
        project_id: str,
        principal: Principal,
        finance: ProjectFinanceService,
    ) -> BudgetHandoffResult:
        version = self.current_version(
            estimate_id
        )

        if (
            version.status
            != EstimateStatus.AWARDED
        ):
            raise EstimateWorkflowError(
                "only awarded estimate can "
                "become project budget"
            )

        key = (
            version.version_id,
            project_id,
        )

        if key in self._budget_handoffs:
            raise EstimateWorkflowError(
                "estimate version already "
                "handed off to this project"
            )

        budget: dict[
            str,
            int,
        ] = {}

        def add(
            code: str,
            amount: int,
        ) -> None:
            budget[code] = (
                budget.get(
                    code,
                    0,
                )
                + amount
            )

        for line in version.lines:
            add(
                line.cost_code,
                line.direct_cost_cents,
            )

        for item in version.allowances:
            add(
                item.cost_code,
                item.direct_cost_cents,
            )

        for effect in version.rfi_effects:
            if effect.resolved:
                add(
                    effect.cost_code,
                    effect.cost_delta_cents,
                )

        accepted = set(
            version.accepted_alternate_ids
        )

        for item in version.alternates:
            if item.alternate_id in accepted:
                add(
                    item.cost_code,
                    item.direct_cost_cents,
                )

        if any(
            amount < 0
            for amount in budget.values()
        ):
            raise EstimateWorkflowError(
                "estimate produces negative "
                "project budget cost code"
            )

        for code, amount in sorted(
            budget.items()
        ):
            finance.set_budget(
                principal=principal,
                tenant_id=(
                    version.tenant_id
                ),
                project_id=project_id,
                cost_code=code,
                amount_cents=amount,
            )

        self._budget_handoffs.add(
            key
        )

        self._event(
            version=version,
            event_type=(
                "estimate.budget_handoff"
            ),
            actor_id=principal.user_id,
            payload={
                "project_id": project_id,
                "budget_cents": sum(
                    budget.values()
                ),
            },
        )

        return BudgetHandoffResult(
            estimate_id=(
                version.estimate_id
            ),
            version_id=(
                version.version_id
            ),
            project_id=project_id,
            budget_by_cost_code=tuple(
                sorted(
                    budget.items()
                )
            ),
            total_budget_cents=sum(
                budget.values()
            ),
        )
