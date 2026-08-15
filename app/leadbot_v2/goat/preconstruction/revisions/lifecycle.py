from __future__ import annotations

import re

from dataclasses import dataclass
from enum import Enum
from typing import Any

from leadbot_v2.goat.preconstruction.revisions.intelligence import (
    RevisionImpactPlan,
)


class RevisionLifecycleError(RuntimeError):
    pass


class RevisionLifecycleBlocked(
    RevisionLifecycleError
):
    pass


class RevisionAction(str, Enum):
    PRESERVE = "preserve"
    INVALIDATE = "invalidate"
    REPLACE = "replace"
    ADD = "add"
    REVIEW = "review"
    BLOCK = "block"


class RevisionReviewSeverity(
    str,
    Enum,
):
    REVIEW = "review"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class RevisionReviewItem:
    code: str

    severity: RevisionReviewSeverity

    message: str

    line_id: str | None = None

    candidate_id: str | None = None

    source_ref: str | None = None


@dataclass(frozen=True)
class InvalidatedEstimateLine:
    line_id: str

    description: str

    cost_code: str

    old_direct_cost_cents: int

    old_bid_price_cents: int

    source_refs: tuple[
        str,
        ...
    ]

    reason: str


@dataclass(frozen=True)
class ReplacementEstimateLine:
    line_id: str

    semantic_candidate_id: str

    description: str

    cost_code: str

    direct_cost_cents: int

    bid_price_cents: int

    source_refs: tuple[
        str,
        ...
    ]

    requires_review: bool


@dataclass(frozen=True)
class RevisionEstimateDelta:
    old_impacted_direct_cost_cents: int

    old_impacted_bid_price_cents: int

    replacement_direct_cost_cents: int

    replacement_bid_price_cents: int

    direct_cost_delta_cents: int

    bid_price_delta_cents: int


@dataclass(frozen=True)
class RevisionLifecycleResult:
    estimate_id: str

    previous_version_id: str

    previous_version_number: int

    revised_version_id: str | None

    revised_version_number: int | None

    invalidated_lines: tuple[
        InvalidatedEstimateLine,
        ...
    ]

    replacement_lines: tuple[
        ReplacementEstimateLine,
        ...
    ]

    preserved_line_ids: tuple[
        str,
        ...
    ]

    review_queue: tuple[
        RevisionReviewItem,
        ...
    ]

    delta: RevisionEstimateDelta

    changed: bool

    proposal_ready: bool

    @property
    def blockers(
        self,
    ) -> tuple[
        RevisionReviewItem,
        ...
    ]:
        return tuple(
            item
            for item
            in self.review_queue
            if (
                item.severity
                == RevisionReviewSeverity
                .BLOCKER
            )
        )


PAGE_RE = re.compile(
    r"(?:^|[?&#])page=(?P<page>\d+)"
)


PROTECTED_STATUSES = {
    "submitted",
    "awarded",
    "lost",
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


def _refs(
    value: Any,
) -> tuple[
    str,
    ...
]:
    refs = getattr(
        value,
        "source_refs",
        (),
    )

    if refs is None:
        return ()

    return tuple(
        str(
            ref
        )
        for ref
        in refs
    )


def _line_id(
    line: Any,
) -> str:
    value = getattr(
        line,
        "line_id",
        None,
    )

    if value is None:
        raise RevisionLifecycleError(
            "estimate line has no line_id"
        )

    return str(
        value
    )


def _page_from_ref(
    ref: str,
) -> int | None:
    match = PAGE_RE.search(
        ref
    )

    if not match:
        return None

    return int(
        match.group(
            "page"
        )
    )


def _document_base(
    ref: str,
) -> str:
    return (
        ref.split(
            "#",
            1,
        )[0]
        .split(
            "?",
            1,
        )[0]
    )


def _same_page_ref(
    left: str,
    right: str,
) -> bool:
    left_page = (
        _page_from_ref(
            left
        )
    )

    right_page = (
        _page_from_ref(
            right
        )
    )

    if (
        left_page is None
        or right_page is None
    ):
        return False

    return (
        left_page
        == right_page
        and _document_base(
            left
        )
        == _document_base(
            right
        )
    )


def _effective_money(
    version: Any,
    line: Any,
) -> tuple[
    int,
    int,
]:
    direct = int(
        getattr(
            line,
            "direct_cost_cents",
            0,
        )
        or 0
    )

    bid = int(
        getattr(
            line,
            "bid_price_cents",
            0,
        )
        or 0
    )

    line_id = _line_id(
        line
    )

    for override in getattr(
        version,
        "overrides",
        (),
    ):
        if str(
            getattr(
                override,
                "line_id",
                "",
            )
        ) != line_id:
            continue

        new_direct = getattr(
            override,
            "new_direct_cost_cents",
            None,
        )

        new_bid = getattr(
            override,
            "new_bid_price_cents",
            None,
        )

        if new_direct is not None:
            direct = int(
                new_direct
            )

        if new_bid is not None:
            bid = int(
                new_bid
            )

    return (
        direct,
        bid,
    )


def _scope_refs(
    scope: Any,
) -> tuple[
    str,
    ...
]:
    provenance = getattr(
        scope,
        "provenance",
        None,
    )

    if provenance is None:
        return ()

    refs = [
        getattr(
            provenance,
            "source_ref",
            None,
        ),
    ]

    for field in (
        "geometry_ids",
        "text_refs",
        "rate_refs",
    ):
        refs.extend(
            getattr(
                provenance,
                field,
                (),
            )
            or ()
        )

    return tuple(
        dict.fromkeys(
            str(
                ref
            )
            for ref
            in refs
            if ref
        )
    )


class EstimateRevisionLifecycle:
    """
    Applies plan revisions to an estimate through
    the existing immutable GOAT revision workflow.

    Existing estimate lines are never deleted.

    Affected prior lines are neutralized through
    audited estimator overrides in a new version.
    Replacement scope is inserted as new lines.

    Submitted, awarded and lost estimates are
    protected from implicit revision.
    """

    def __init__(
        self,
        *,
        workflow: Any,
    ) -> None:
        self.workflow = workflow

    @staticmethod
    def _protected_status(
        version: Any,
    ) -> bool:
        status = (
            _enum_text(
                getattr(
                    version,
                    "status",
                    "",
                )
            )
            .strip()
            .lower()
        )

        return (
            status
            in PROTECTED_STATUSES
        )

    @staticmethod
    def _impact_tokens(
        impact: RevisionImpactPlan,
    ) -> tuple[
        tuple[
            str,
            ...
        ],
        tuple[
            int,
            ...
        ],
    ]:
        refs = []

        for delta in (
            impact.changed_sheets
        ):
            if (
                delta.old_source_ref
            ):
                refs.append(
                    str(
                        delta
                        .old_source_ref
                    )
                )

        refs.extend(
            str(
                item
            )
            for item
            in impact
            .invalidated_candidate_ids
        )

        return (
            tuple(
                dict.fromkeys(
                    refs
                )
            ),
            tuple(
                impact
                .impacted_old_pages
            ),
        )

    @classmethod
    def _line_impacted(
        cls,
        *,
        line: Any,
        impact: RevisionImpactPlan,
    ) -> bool:
        line_refs = _refs(
            line
        )

        target_refs, pages = (
            cls._impact_tokens(
                impact
            )
        )

        if not line_refs:
            return False

        for line_ref in (
            line_refs
        ):
            if line_ref in (
                target_refs
            ):
                return True

            for target in (
                target_refs
            ):
                if (
                    _same_page_ref(
                        line_ref,
                        target,
                    )
                ):
                    return True

            line_page = (
                _page_from_ref(
                    line_ref
                )
            )

            if (
                line_page
                in pages
                and any(
                    _document_base(
                        line_ref
                    )
                    == _document_base(
                        target
                    )
                    for target
                    in target_refs
                    if _page_from_ref(
                        target
                    )
                    is not None
                )
            ):
                return True

        return False

    @staticmethod
    def _candidate_pages(
        semantic: Any,
    ) -> dict[
        str,
        int,
    ]:
        result = {}

        for candidate in getattr(
            semantic,
            "candidates",
            (),
        ):
            candidate_id = getattr(
                candidate,
                "candidate_id",
                None,
            )

            page_number = getattr(
                candidate,
                "page_number",
                None,
            )

            if (
                candidate_id is None
                or page_number is None
            ):
                continue

            result[
                str(
                    candidate_id
                )
            ] = int(
                page_number
            )

        return result

    @classmethod
    def _replacement_scopes(
        cls,
        *,
        impact: RevisionImpactPlan,
        new_semantic: Any,
        new_pricing: Any,
    ) -> tuple[
        Any,
        ...
    ]:
        candidate_pages = (
            cls._candidate_pages(
                new_semantic
            )
        )

        impacted_pages = set(
            impact
            .impacted_new_pages
        )

        result = []

        seen = set()

        for scope in getattr(
            new_pricing,
            "scopes",
            (),
        ):
            candidate_id = str(
                getattr(
                    scope,
                    "semantic_candidate_id",
                    "",
                )
            )

            if not candidate_id:
                continue

            page_number = (
                candidate_pages.get(
                    candidate_id
                )
            )

            if (
                page_number
                not in impacted_pages
            ):
                continue

            if candidate_id in seen:
                raise RevisionLifecycleError(
                    "duplicate replacement "
                    "semantic candidate: "
                    f"{candidate_id}"
                )

            seen.add(
                candidate_id
            )

            result.append(
                scope
            )

        return tuple(
            result
        )

    @staticmethod
    def _empty_delta(
    ) -> RevisionEstimateDelta:
        return (
            RevisionEstimateDelta(
                old_impacted_direct_cost_cents=0,
                old_impacted_bid_price_cents=0,
                replacement_direct_cost_cents=0,
                replacement_bid_price_cents=0,
                direct_cost_delta_cents=0,
                bid_price_delta_cents=0,
            )
        )

    def apply(
        self,
        *,
        estimate_id: str,
        actor_id: str,
        impact: RevisionImpactPlan,
        new_semantic: Any,
        new_pricing: Any,
    ) -> RevisionLifecycleResult:
        current = (
            self.workflow
            .current_version(
                estimate_id
            )
        )

        previous_version_id = str(
            getattr(
                current,
                "version_id",
                "",
            )
        )

        previous_version_number = int(
            getattr(
                current,
                "version_number",
                0,
            )
        )

        if impact.no_change:
            return RevisionLifecycleResult(
                estimate_id=(
                    estimate_id
                ),
                previous_version_id=(
                    previous_version_id
                ),
                previous_version_number=(
                    previous_version_number
                ),
                revised_version_id=None,
                revised_version_number=None,
                invalidated_lines=(),
                replacement_lines=(),
                preserved_line_ids=tuple(
                    _line_id(
                        line
                    )
                    for line
                    in getattr(
                        current,
                        "lines",
                        (),
                    )
                ),
                review_queue=(),
                delta=(
                    self._empty_delta()
                ),
                changed=False,
                proposal_ready=True,
            )

        if impact.blockers:
            queue = tuple(
                RevisionReviewItem(
                    code=(
                        finding.code
                    ),
                    severity=(
                        RevisionReviewSeverity
                        .BLOCKER
                    ),
                    message=(
                        finding.message
                    ),
                    source_ref=(
                        finding.source_ref
                    ),
                )
                for finding
                in impact.blockers
            )

            return RevisionLifecycleResult(
                estimate_id=estimate_id,
                previous_version_id=(
                    previous_version_id
                ),
                previous_version_number=(
                    previous_version_number
                ),
                revised_version_id=None,
                revised_version_number=None,
                invalidated_lines=(),
                replacement_lines=(),
                preserved_line_ids=tuple(
                    _line_id(
                        line
                    )
                    for line
                    in getattr(
                        current,
                        "lines",
                        (),
                    )
                ),
                review_queue=queue,
                delta=(
                    self._empty_delta()
                ),
                changed=False,
                proposal_ready=False,
            )

        if self._protected_status(
            current
        ):
            status = _enum_text(
                getattr(
                    current,
                    "status",
                    "",
                )
            )

            queue = (
                RevisionReviewItem(
                    code=(
                        "ESTIMATE_STATUS_PROTECTED"
                    ),
                    severity=(
                        RevisionReviewSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Estimate status "
                        f"{status} cannot be "
                        "silently revised."
                    ),
                ),
            )

            return RevisionLifecycleResult(
                estimate_id=estimate_id,
                previous_version_id=(
                    previous_version_id
                ),
                previous_version_number=(
                    previous_version_number
                ),
                revised_version_id=None,
                revised_version_number=None,
                invalidated_lines=(),
                replacement_lines=(),
                preserved_line_ids=tuple(
                    _line_id(
                        line
                    )
                    for line
                    in getattr(
                        current,
                        "lines",
                        (),
                    )
                ),
                review_queue=queue,
                delta=(
                    self._empty_delta()
                ),
                changed=False,
                proposal_ready=False,
            )

        impacted_lines = []

        preserved_lines = []

        for line in getattr(
            current,
            "lines",
            (),
        ):
            if self._line_impacted(
                line=line,
                impact=impact,
            ):
                impacted_lines.append(
                    line
                )
            else:
                preserved_lines.append(
                    line
                )

        replacement_scopes = (
            self._replacement_scopes(
                impact=impact,
                new_semantic=(
                    new_semantic
                ),
                new_pricing=(
                    new_pricing
                ),
            )
        )

        review_queue = []

        for scope in (
            replacement_scopes
        ):
            ready = bool(
                getattr(
                    scope,
                    "ready_for_estimate",
                    False,
                )
            )

            requires_review = bool(
                getattr(
                    scope,
                    "requires_review",
                    False,
                )
            )

            candidate_id = str(
                getattr(
                    scope,
                    "semantic_candidate_id",
                    "",
                )
            )

            if not ready:
                review_queue.append(
                    RevisionReviewItem(
                        code=(
                            "REVISION_SCOPE_UNPRICED"
                        ),
                        severity=(
                            RevisionReviewSeverity
                            .BLOCKER
                        ),
                        message=(
                            getattr(
                                scope,
                                "unresolved_reason",
                                None,
                            )
                            or (
                                "Revised scope has "
                                "no valid price."
                            )
                        ),
                        candidate_id=(
                            candidate_id
                        ),
                        source_ref=(
                            getattr(
                                getattr(
                                    scope,
                                    "provenance",
                                    None,
                                ),
                                "source_ref",
                                None,
                            )
                        ),
                    )
                )

            elif requires_review:
                review_queue.append(
                    RevisionReviewItem(
                        code=(
                            "REVISION_SCOPE_REVIEW"
                        ),
                        severity=(
                            RevisionReviewSeverity
                            .REVIEW
                        ),
                        message=(
                            "Revised priced scope "
                            "requires estimator review."
                        ),
                        candidate_id=(
                            candidate_id
                        ),
                    )
                )

        if any(
            item.severity
            == RevisionReviewSeverity
            .BLOCKER
            for item
            in review_queue
        ):
            return RevisionLifecycleResult(
                estimate_id=estimate_id,
                previous_version_id=(
                    previous_version_id
                ),
                previous_version_number=(
                    previous_version_number
                ),
                revised_version_id=None,
                revised_version_number=None,
                invalidated_lines=(),
                replacement_lines=(),
                preserved_line_ids=tuple(
                    _line_id(
                        line
                    )
                    for line
                    in preserved_lines
                ),
                review_queue=tuple(
                    review_queue
                ),
                delta=(
                    self._empty_delta()
                ),
                changed=False,
                proposal_ready=False,
            )

        old_direct = 0
        old_bid = 0

        invalidated = []

        for line in (
            impacted_lines
        ):
            direct, bid = (
                _effective_money(
                    current,
                    line,
                )
            )

            old_direct += direct
            old_bid += bid

            invalidated.append(
                InvalidatedEstimateLine(
                    line_id=(
                        _line_id(
                            line
                        )
                    ),
                    description=str(
                        getattr(
                            line,
                            "description",
                            "",
                        )
                    ),
                    cost_code=str(
                        getattr(
                            line,
                            "cost_code",
                            "",
                        )
                    ),
                    old_direct_cost_cents=(
                        direct
                    ),
                    old_bid_price_cents=(
                        bid
                    ),
                    source_refs=(
                        _refs(
                            line
                        )
                    ),
                    reason=(
                        "Plan revision invalidated "
                        "the source evidence for "
                        "this estimate line."
                    ),
                )
            )

        revised = (
            self.workflow
            .create_revision(
                estimate_id=(
                    estimate_id
                ),
                actor_id=(
                    actor_id
                ),
            )
        )

        for line in (
            invalidated
        ):
            self.workflow.override_line(
                estimate_id=(
                    estimate_id
                ),
                actor_id=(
                    actor_id
                ),
                line_id=(
                    line.line_id
                ),
                reason=(
                    line.reason
                ),
                new_direct_cost_cents=0,
                new_bid_price_cents=0,
            )

        replacements = []

        replacement_direct = 0
        replacement_bid = 0

        for scope in (
            replacement_scopes
        ):
            if not bool(
                getattr(
                    scope,
                    "ready_for_estimate",
                    False,
                )
            ):
                continue

            direct = int(
                getattr(
                    scope,
                    "direct_cost_cents",
                    0,
                )
                or 0
            )

            bid = int(
                getattr(
                    scope,
                    "bid_price_cents",
                    0,
                )
                or 0
            )

            line = (
                self.workflow
                .add_manual_line(
                    estimate_id=(
                        estimate_id
                    ),
                    actor_id=(
                        actor_id
                    ),
                    description=str(
                        getattr(
                            scope,
                            "description",
                            "Revised scope",
                        )
                    ),
                    cost_code=str(
                        getattr(
                            scope,
                            "cost_code",
                            "UNRESOLVED",
                        )
                    ),
                    quantity=float(
                        getattr(
                            scope,
                            "quantity",
                            0,
                        )
                    ),
                    unit=str(
                        getattr(
                            scope,
                            "unit",
                            "",
                        )
                    ),
                    direct_cost_cents=(
                        direct
                    ),
                    bid_price_cents=(
                        bid
                    ),
                    source_refs=(
                        _scope_refs(
                            scope
                        )
                    ),
                    confidence=float(
                        getattr(
                            scope,
                            "confidence",
                            0,
                        )
                    ),
                    requires_review=bool(
                        getattr(
                            scope,
                            "requires_review",
                            False,
                        )
                    ),
                )
            )

            replacement_direct += (
                direct
            )

            replacement_bid += bid

            replacements.append(
                ReplacementEstimateLine(
                    line_id=(
                        _line_id(
                            line
                        )
                    ),
                    semantic_candidate_id=str(
                        getattr(
                            scope,
                            "semantic_candidate_id",
                            "",
                        )
                    ),
                    description=str(
                        getattr(
                            scope,
                            "description",
                            "",
                        )
                    ),
                    cost_code=str(
                        getattr(
                            scope,
                            "cost_code",
                            "",
                        )
                    ),
                    direct_cost_cents=(
                        direct
                    ),
                    bid_price_cents=(
                        bid
                    ),
                    source_refs=(
                        _scope_refs(
                            scope
                        )
                    ),
                    requires_review=bool(
                        getattr(
                            scope,
                            "requires_review",
                            False,
                        )
                    ),
                )
            )

        final_version = (
            self.workflow
            .current_version(
                estimate_id
            )
        )

        delta = RevisionEstimateDelta(
            old_impacted_direct_cost_cents=(
                old_direct
            ),
            old_impacted_bid_price_cents=(
                old_bid
            ),
            replacement_direct_cost_cents=(
                replacement_direct
            ),
            replacement_bid_price_cents=(
                replacement_bid
            ),
            direct_cost_delta_cents=(
                replacement_direct
                - old_direct
            ),
            bid_price_delta_cents=(
                replacement_bid
                - old_bid
            ),
        )

        proposal_ready = (
            not review_queue
        )

        return RevisionLifecycleResult(
            estimate_id=estimate_id,
            previous_version_id=(
                previous_version_id
            ),
            previous_version_number=(
                previous_version_number
            ),
            revised_version_id=str(
                getattr(
                    final_version,
                    "version_id",
                    getattr(
                        revised,
                        "version_id",
                        "",
                    ),
                )
            ),
            revised_version_number=int(
                getattr(
                    final_version,
                    "version_number",
                    getattr(
                        revised,
                        "version_number",
                        previous_version_number
                        + 1,
                    ),
                )
            ),
            invalidated_lines=tuple(
                invalidated
            ),
            replacement_lines=tuple(
                replacements
            ),
            preserved_line_ids=tuple(
                _line_id(
                    line
                )
                for line
                in preserved_lines
            ),
            review_queue=tuple(
                review_queue
            ),
            delta=delta,
            changed=True,
            proposal_ready=(
                proposal_ready
            ),
        )
