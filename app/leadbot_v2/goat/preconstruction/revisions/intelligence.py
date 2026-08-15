from __future__ import annotations

import hashlib
import json
import math
import re

from dataclasses import dataclass
from enum import Enum
from typing import Any

from leadbot_v2.goat.preconstruction.integration.vector_takeoff import (
    TradeKind,
    trade_from_sheet,
)


class RevisionIntegrityError(RuntimeError):
    pass


class RevisionSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    BLOCKER = "blocker"


class SheetChangeKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class RevisionAspect(str, Enum):
    TEXT = "text"
    VECTOR_GEOMETRY = "vector_geometry"
    SCALE = "scale"
    REVISION_MARKER = "revision_marker"
    SHEET_IDENTITY = "sheet_identity"


class RerunStage(str, Enum):
    NONE = "none"
    SEMANTIC = "semantic"
    GEOMETRY = "geometry"
    FULL_SHEET = "full_sheet"


@dataclass(frozen=True)
class RevisionFinding:
    code: str
    severity: RevisionSeverity
    message: str
    sheet_number: str | None = None
    old_page_number: int | None = None
    new_page_number: int | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class SheetFingerprint:
    sheet_number: str | None
    page_number: int
    source_ref: str

    trade: TradeKind

    text_hash: str
    geometry_hash: str
    scale_hash: str
    revision_hash: str
    combined_hash: str

    scale_text: str | None

    revision_markers: tuple[
        str,
        ...
    ]

    vector_count: int

    @property
    def stable_key(
        self,
    ) -> str:
        if self.sheet_number:
            return (
                "sheet:"
                + self.sheet_number
            )

        return (
            "page:"
            + str(
                self.page_number
            )
        )


@dataclass(frozen=True)
class SheetRevisionDelta:
    key: str

    sheet_number: str | None

    old_page_number: int | None
    new_page_number: int | None

    old_source_ref: str | None
    new_source_ref: str | None

    trade: TradeKind

    change_kind: SheetChangeKind

    aspects: tuple[
        RevisionAspect,
        ...
    ]

    rerun_stage: RerunStage

    requires_review: bool

    old_fingerprint: (
        SheetFingerprint
        | None
    )

    new_fingerprint: (
        SheetFingerprint
        | None
    )

    @property
    def changed(
        self,
    ) -> bool:
        return (
            self.change_kind
            != SheetChangeKind
            .UNCHANGED
        )


@dataclass(frozen=True)
class RevisionImpactPlan:
    old_document_id: str
    new_document_id: str

    deltas: tuple[
        SheetRevisionDelta,
        ...
    ]

    findings: tuple[
        RevisionFinding,
        ...
    ]

    invalidated_candidate_ids: tuple[
        str,
        ...
    ]

    impacted_old_pages: tuple[
        int,
        ...
    ]

    impacted_new_pages: tuple[
        int,
        ...
    ]

    impacted_trades: tuple[
        TradeKind,
        ...
    ]

    requires_full_rerun: bool

    @property
    def blockers(
        self,
    ) -> tuple[
        RevisionFinding,
        ...
    ]:
        return tuple(
            finding
            for finding
            in self.findings
            if (
                finding.severity
                == RevisionSeverity.BLOCKER
            )
        )

    @property
    def changed_sheets(
        self,
    ) -> tuple[
        SheetRevisionDelta,
        ...
    ]:
        return tuple(
            delta
            for delta
            in self.deltas
            if delta.changed
        )

    @property
    def unchanged_sheets(
        self,
    ) -> tuple[
        SheetRevisionDelta,
        ...
    ]:
        return tuple(
            delta
            for delta
            in self.deltas
            if not delta.changed
        )

    @property
    def can_incrementally_rerun(
        self,
    ) -> bool:
        return (
            bool(
                self.changed_sheets
            )
            and not self.blockers
            and not self
            .requires_full_rerun
        )

    @property
    def no_change(
        self,
    ) -> bool:
        return (
            not self.changed_sheets
            and not self.blockers
        )


REVISION_PATTERNS = (
    re.compile(
        r"\bREV(?:ISION)?"
        r"\s*[:#-]?\s*"
        r"(?P<value>[A-Z0-9.-]+)\b",
        re.I,
    ),
    re.compile(
        r"\bADDENDUM"
        r"\s*[:#-]?\s*"
        r"(?P<value>[A-Z0-9.-]+)\b",
        re.I,
    ),
    re.compile(
        r"\bISSUE(?:D)?\s+FOR\s+"
        r"(?P<value>"
        r"CONSTRUCTION|"
        r"BID|"
        r"PERMIT|"
        r"REVIEW"
        r")\b",
        re.I,
    ),
)


TRADE_ORDER = (
    TradeKind.CONCRETE,
    TradeKind.EARTHWORK,
    TradeKind.ELECTRICAL,
    TradeKind.PLUMBING,
    TradeKind.ARCHITECTURAL,
    TradeKind.COORDINATION,
)


def _sha(
    value: Any,
) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        hashlib
        .sha256(
            encoded
        )
        .hexdigest()
    )


def _normalize_text(
    text: str,
) -> str:
    return " ".join(
        (text or "")
        .upper()
        .split()
    )


def _normalize_scale(
    value: Any,
) -> str:
    if value is None:
        return ""

    return " ".join(
        str(
            value
        )
        .upper()
        .split()
    )


def _finite_round(
    value: Any,
    digits: int = 3,
) -> float:
    number = float(
        value
    )

    if not math.isfinite(
        number
    ):
        raise RevisionIntegrityError(
            "non-finite PDF geometry "
            "encountered during revision "
            "fingerprinting"
        )

    return round(
        number,
        digits,
    )


def _point(
    value: Any,
) -> tuple[
    float,
    float,
]:
    if hasattr(
        value,
        "x",
    ):
        return (
            _finite_round(
                value.x
            ),
            _finite_round(
                value.y
            ),
        )

    return (
        _finite_round(
            value[0]
        ),
        _finite_round(
            value[1]
        ),
    )


def _normalize_line(
    segment: Any,
) -> tuple:
    start = _point(
        segment.start
    )

    end = _point(
        segment.end
    )

    # PDF line direction is not semantically meaningful.
    # Normalize endpoint order so reversed primitives do not
    # generate a false revision.
    ordered = tuple(
        sorted(
            (
                start,
                end,
            )
        )
    )

    return (
        "line",
        ordered[0],
        ordered[1],
        _finite_round(
            getattr(
                segment,
                "width_points",
                0.0,
            )
        ),
    )


def _normalize_rectangle(
    rectangle: Any,
) -> tuple:
    raw = tuple(
        _finite_round(
            value
        )
        for value
        in rectangle.bbox
    )

    if len(
        raw
    ) != 4:
        raise RevisionIntegrityError(
            "rectangle bbox must contain "
            "four coordinates"
        )

    x0, y0, x1, y1 = raw

    return (
        "rectangle",
        min(
            x0,
            x1,
        ),
        min(
            y0,
            y1,
        ),
        max(
            x0,
            x1,
        ),
        max(
            y0,
            y1,
        ),
        _finite_round(
            getattr(
                rectangle,
                "width_points",
                0.0,
            )
        ),
    )


def _geometry_signature(
    page: Any,
) -> tuple:
    lines = [
        _normalize_line(
            segment
        )
        for segment
        in getattr(
            page,
            "segments",
            (),
        )
    ]

    rectangles = [
        _normalize_rectangle(
            rectangle
        )
        for rectangle
        in getattr(
            page,
            "rectangles",
            (),
        )
    ]

    return tuple(
        sorted(
            lines
            + rectangles,
            key=repr,
        )
    )


def extract_revision_markers(
    text: str,
) -> tuple[
    str,
    ...
]:
    values = []

    source = (
        text
        or ""
    )

    for pattern in (
        REVISION_PATTERNS
    ):
        for match in (
            pattern
            .finditer(
                source
            )
        ):
            values.append(
                " ".join(
                    match
                    .group(0)
                    .upper()
                    .split()
                )
            )

    return tuple(
        sorted(
            set(
                values
            )
        )
    )


def fingerprint_page(
    page: Any,
) -> SheetFingerprint:
    page_number = int(
        getattr(
            page,
            "page_number",
            0,
        )
    )

    if page_number <= 0:
        raise RevisionIntegrityError(
            "page_number must be positive"
        )

    text = str(
        getattr(
            page,
            "text",
            "",
        )
        or ""
    )

    sheet_number = getattr(
        page,
        "sheet_hint",
        None,
    )

    if sheet_number is not None:
        sheet_number = (
            str(
                sheet_number
            )
            .strip()
            .upper()
            or None
        )

    source_ref = str(
        getattr(
            page,
            "source_ref",
            f"page:{page_number}",
        )
    )

    scale_text = getattr(
        page,
        "scale_text",
        None,
    )

    if scale_text is not None:
        scale_text = str(
            scale_text
        )

    normalized_text = (
        _normalize_text(
            text
        )
    )

    geometry = (
        _geometry_signature(
            page
        )
    )

    revision_markers = (
        extract_revision_markers(
            text
        )
    )

    trade = (
        trade_from_sheet(
            sheet_number,
            text,
        )
    )

    text_hash = _sha(
        normalized_text
    )

    geometry_hash = _sha(
        geometry
    )

    scale_hash = _sha(
        _normalize_scale(
            scale_text
        )
    )

    revision_hash = _sha(
        revision_markers
    )

    combined_hash = _sha(
        {
            "sheet_number":
                sheet_number,
            "trade":
                trade.value,
            "text_hash":
                text_hash,
            "geometry_hash":
                geometry_hash,
            "scale_hash":
                scale_hash,
            "revision_hash":
                revision_hash,
        }
    )

    return SheetFingerprint(
        sheet_number=(
            sheet_number
        ),
        page_number=(
            page_number
        ),
        source_ref=(
            source_ref
        ),
        trade=trade,
        text_hash=(
            text_hash
        ),
        geometry_hash=(
            geometry_hash
        ),
        scale_hash=(
            scale_hash
        ),
        revision_hash=(
            revision_hash
        ),
        combined_hash=(
            combined_hash
        ),
        scale_text=(
            scale_text
        ),
        revision_markers=(
            revision_markers
        ),
        vector_count=len(
            geometry
        ),
    )


def _rerun_stage(
    aspects: tuple[
        RevisionAspect,
        ...
    ],
    change_kind: SheetChangeKind,
) -> RerunStage:
    if (
        change_kind
        in {
            SheetChangeKind.ADDED,
            SheetChangeKind.REMOVED,
        }
    ):
        return (
            RerunStage.FULL_SHEET
        )

    aspect_set = set(
        aspects
    )

    if (
        RevisionAspect.SCALE
        in aspect_set
    ):
        return (
            RerunStage.FULL_SHEET
        )

    if (
        RevisionAspect
        .VECTOR_GEOMETRY
        in aspect_set
    ):
        return (
            RerunStage.GEOMETRY
        )

    if (
        RevisionAspect.TEXT
        in aspect_set
        or RevisionAspect
        .REVISION_MARKER
        in aspect_set
    ):
        return (
            RerunStage.SEMANTIC
        )

    return (
        RerunStage.NONE
    )


def _delta(
    key: str,
    old: (
        SheetFingerprint
        | None
    ),
    new: (
        SheetFingerprint
        | None
    ),
) -> SheetRevisionDelta:
    if (
        old is None
        and new is None
    ):
        raise ValueError(
            "old and new cannot both "
            "be None"
        )

    if old is None:
        return (
            SheetRevisionDelta(
                key=key,
                sheet_number=(
                    new.sheet_number
                ),
                old_page_number=None,
                new_page_number=(
                    new.page_number
                ),
                old_source_ref=None,
                new_source_ref=(
                    new.source_ref
                ),
                trade=new.trade,
                change_kind=(
                    SheetChangeKind
                    .ADDED
                ),
                aspects=(
                    RevisionAspect
                    .SHEET_IDENTITY,
                ),
                rerun_stage=(
                    RerunStage
                    .FULL_SHEET
                ),
                requires_review=True,
                old_fingerprint=None,
                new_fingerprint=new,
            )
        )

    if new is None:
        return (
            SheetRevisionDelta(
                key=key,
                sheet_number=(
                    old.sheet_number
                ),
                old_page_number=(
                    old.page_number
                ),
                new_page_number=None,
                old_source_ref=(
                    old.source_ref
                ),
                new_source_ref=None,
                trade=old.trade,
                change_kind=(
                    SheetChangeKind
                    .REMOVED
                ),
                aspects=(
                    RevisionAspect
                    .SHEET_IDENTITY,
                ),
                rerun_stage=(
                    RerunStage
                    .FULL_SHEET
                ),
                requires_review=True,
                old_fingerprint=old,
                new_fingerprint=None,
            )
        )

    aspects = []

    if (
        old.text_hash
        != new.text_hash
    ):
        aspects.append(
            RevisionAspect.TEXT
        )

    if (
        old.geometry_hash
        != new.geometry_hash
    ):
        aspects.append(
            RevisionAspect
            .VECTOR_GEOMETRY
        )

    if (
        old.scale_hash
        != new.scale_hash
    ):
        aspects.append(
            RevisionAspect.SCALE
        )

    if (
        old.revision_hash
        != new.revision_hash
    ):
        aspects.append(
            RevisionAspect
            .REVISION_MARKER
        )

    if not aspects:
        change_kind = (
            SheetChangeKind
            .UNCHANGED
        )
    else:
        change_kind = (
            SheetChangeKind
            .MODIFIED
        )

    aspect_tuple = tuple(
        aspects
    )

    return SheetRevisionDelta(
        key=key,
        sheet_number=(
            new.sheet_number
            or old.sheet_number
        ),
        old_page_number=(
            old.page_number
        ),
        new_page_number=(
            new.page_number
        ),
        old_source_ref=(
            old.source_ref
        ),
        new_source_ref=(
            new.source_ref
        ),
        trade=(
            new.trade
        ),
        change_kind=(
            change_kind
        ),
        aspects=(
            aspect_tuple
        ),
        rerun_stage=(
            _rerun_stage(
                aspect_tuple,
                change_kind,
            )
        ),
        requires_review=(
            change_kind
            != SheetChangeKind
            .UNCHANGED
        ),
        old_fingerprint=old,
        new_fingerprint=new,
    )


class PlanRevisionEngine:
    """
    Deterministic plan-set revision intelligence.

    Stable sheet numbers are the primary identity key.
    Page numbers are treated only as document positions,
    so page reordering does not create false revisions.

    When sheet identity cannot be trusted, GOAT expands
    the review/rerun scope instead of silently matching
    unrelated pages.
    """

    def __init__(
        self,
        *,
        require_sheet_ids_for_vectors: (
            bool
        ) = True,
    ) -> None:
        self.require_sheet_ids_for_vectors = (
            require_sheet_ids_for_vectors
        )

    @staticmethod
    def _document_id(
        document: Any,
    ) -> str:
        return str(
            getattr(
                document,
                "document_id",
                "unknown-document",
            )
        )

    def _index(
        self,
        document: Any,
        *,
        label: str,
    ) -> tuple[
        dict[
            str,
            SheetFingerprint,
        ],
        tuple[
            RevisionFinding,
            ...
        ],
        bool,
    ]:
        index = {}

        findings = []

        full_rerun = False

        pages = tuple(
            getattr(
                document,
                "pages",
                (),
            )
        )

        if not pages:
            findings.append(
                RevisionFinding(
                    code=(
                        "REVISION_DOCUMENT_EMPTY"
                    ),
                    severity=(
                        RevisionSeverity
                        .BLOCKER
                    ),
                    message=(
                        f"{label} document "
                        "contains no pages."
                    ),
                )
            )

            return (
                index,
                tuple(
                    findings
                ),
                True,
            )

        for page in pages:
            fingerprint = (
                fingerprint_page(
                    page
                )
            )

            if (
                fingerprint
                .sheet_number
            ):
                key = (
                    "sheet:"
                    + fingerprint
                    .sheet_number
                )

            else:
                key = (
                    "page:"
                    + str(
                        fingerprint
                        .page_number
                    )
                )

                if (
                    self
                    .require_sheet_ids_for_vectors
                    and fingerprint
                    .vector_count
                    > 0
                ):
                    findings.append(
                        RevisionFinding(
                            code=(
                                "VECTOR_SHEET_ID_MISSING"
                            ),
                            severity=(
                                RevisionSeverity
                                .BLOCKER
                            ),
                            message=(
                                f"{label} vector "
                                "sheet has no stable "
                                "sheet identifier."
                            ),
                            old_page_number=(
                                fingerprint
                                .page_number
                                if label
                                == "old"
                                else None
                            ),
                            new_page_number=(
                                fingerprint
                                .page_number
                                if label
                                == "new"
                                else None
                            ),
                            source_ref=(
                                fingerprint
                                .source_ref
                            ),
                        )
                    )

                    full_rerun = True

            if key in index:
                existing = (
                    index[
                        key
                    ]
                )

                findings.append(
                    RevisionFinding(
                        code=(
                            "DUPLICATE_SHEET_ID"
                        ),
                        severity=(
                            RevisionSeverity
                            .BLOCKER
                        ),
                        message=(
                            f"{label} document "
                            f"contains duplicate "
                            f"sheet identity "
                            f"{key}."
                        ),
                        sheet_number=(
                            fingerprint
                            .sheet_number
                        ),
                        old_page_number=(
                            existing
                            .page_number
                            if label
                            == "old"
                            else None
                        ),
                        new_page_number=(
                            fingerprint
                            .page_number
                            if label
                            == "new"
                            else None
                        ),
                        source_ref=(
                            fingerprint
                            .source_ref
                        ),
                    )
                )

                full_rerun = True

                continue

            index[
                key
            ] = (
                fingerprint
            )

        return (
            index,
            tuple(
                findings
            ),
            full_rerun,
        )

    @staticmethod
    def _invalidated_candidates(
        *,
        previous_semantic: (
            Any | None
        ),
        impacted_old_pages: set[
            int
        ],
    ) -> tuple[
        str,
        ...
    ]:
        if (
            previous_semantic
            is None
        ):
            return ()

        result = []

        for candidate in getattr(
            previous_semantic,
            "candidates",
            (),
        ):
            page_number = getattr(
                candidate,
                "page_number",
                None,
            )

            if page_number is None:
                continue

            if (
                int(
                    page_number
                )
                not in impacted_old_pages
            ):
                continue

            candidate_id = getattr(
                candidate,
                "candidate_id",
                None,
            )

            if candidate_id is None:
                continue

            result.append(
                str(
                    candidate_id
                )
            )

        return tuple(
            sorted(
                set(
                    result
                )
            )
        )

    def compare(
        self,
        *,
        old_document: Any,
        new_document: Any,
        previous_semantic: (
            Any | None
        ) = None,
    ) -> RevisionImpactPlan:
        (
            old_index,
            old_findings,
            old_full,
        ) = self._index(
            old_document,
            label="old",
        )

        (
            new_index,
            new_findings,
            new_full,
        ) = self._index(
            new_document,
            label="new",
        )

        findings = list(
            old_findings
            + new_findings
        )

        keys = sorted(
            set(
                old_index
            )
            | set(
                new_index
            )
        )

        deltas = tuple(
            _delta(
                key,
                old_index.get(
                    key
                ),
                new_index.get(
                    key
                ),
            )
            for key
            in keys
        )

        impacted_old_pages: set[
            int
        ] = set()

        impacted_new_pages: set[
            int
        ] = set()

        impacted_trades: set[
            TradeKind
        ] = set()

        for delta in deltas:
            if not delta.changed:
                continue

            impacted_trades.add(
                delta.trade
            )

            if (
                delta
                .old_page_number
                is not None
            ):
                impacted_old_pages.add(
                    delta
                    .old_page_number
                )

            if (
                delta
                .new_page_number
                is not None
            ):
                impacted_new_pages.add(
                    delta
                    .new_page_number
                )

            if (
                RevisionAspect.SCALE
                in delta.aspects
            ):
                findings.append(
                    RevisionFinding(
                        code=(
                            "DRAWING_SCALE_CHANGED"
                        ),
                        severity=(
                            RevisionSeverity
                            .REVIEW
                        ),
                        message=(
                            "Drawing scale changed. "
                            "Existing measured "
                            "quantities from this "
                            "sheet must be invalidated."
                        ),
                        sheet_number=(
                            delta
                            .sheet_number
                        ),
                        old_page_number=(
                            delta
                            .old_page_number
                        ),
                        new_page_number=(
                            delta
                            .new_page_number
                        ),
                        source_ref=(
                            delta
                            .new_source_ref
                            or delta
                            .old_source_ref
                        ),
                    )
                )

            if (
                delta.change_kind
                == SheetChangeKind
                .REMOVED
            ):
                findings.append(
                    RevisionFinding(
                        code=(
                            "SHEET_REMOVED"
                        ),
                        severity=(
                            RevisionSeverity
                            .REVIEW
                        ),
                        message=(
                            "Previously bid sheet "
                            "was removed from the "
                            "new plan set."
                        ),
                        sheet_number=(
                            delta
                            .sheet_number
                        ),
                        old_page_number=(
                            delta
                            .old_page_number
                        ),
                        source_ref=(
                            delta
                            .old_source_ref
                        ),
                    )
                )

            if (
                delta.change_kind
                == SheetChangeKind
                .ADDED
            ):
                findings.append(
                    RevisionFinding(
                        code=(
                            "SHEET_ADDED"
                        ),
                        severity=(
                            RevisionSeverity
                            .REVIEW
                        ),
                        message=(
                            "New sheet added to "
                            "the bid package."
                        ),
                        sheet_number=(
                            delta
                            .sheet_number
                        ),
                        new_page_number=(
                            delta
                            .new_page_number
                        ),
                        source_ref=(
                            delta
                            .new_source_ref
                        ),
                    )
                )

        invalidated = (
            self
            ._invalidated_candidates(
                previous_semantic=(
                    previous_semantic
                ),
                impacted_old_pages=(
                    impacted_old_pages
                ),
            )
        )

        full_rerun = (
            old_full
            or new_full
            or bool(
                [
                    finding
                    for finding
                    in findings
                    if (
                        finding.severity
                        == RevisionSeverity
                        .BLOCKER
                    )
                ]
            )
        )

        ordered_trades = tuple(
            trade
            for trade
            in TRADE_ORDER
            if trade
            in impacted_trades
        )

        return RevisionImpactPlan(
            old_document_id=(
                self._document_id(
                    old_document
                )
            ),
            new_document_id=(
                self._document_id(
                    new_document
                )
            ),
            deltas=deltas,
            findings=tuple(
                findings
            ),
            invalidated_candidate_ids=(
                invalidated
            ),
            impacted_old_pages=tuple(
                sorted(
                    impacted_old_pages
                )
            ),
            impacted_new_pages=tuple(
                sorted(
                    impacted_new_pages
                )
            ),
            impacted_trades=(
                ordered_trades
            ),
            requires_full_rerun=(
                full_rerun
            ),
        )


class RevisionRerunPlanner:
    """
    Converts revision intelligence into an explicit
    GOAT execution instruction without mutating an
    existing estimate.

    Actual estimate replacement remains a separate,
    audited workflow action.
    """

    @staticmethod
    def execution_plan(
        impact: RevisionImpactPlan,
    ) -> dict:
        if impact.no_change:
            return {
                "mode":
                    "no_change",

                "pages":
                    (),

                "trades":
                    (),

                "invalidate":
                    (),
            }

        if (
            impact
            .requires_full_rerun
        ):
            return {
                "mode":
                    "full_rerun",

                "pages":
                    impact
                    .impacted_new_pages,

                "trades":
                    tuple(
                        trade.value
                        for trade
                        in impact
                        .impacted_trades
                    ),

                "invalidate":
                    impact
                    .invalidated_candidate_ids,
            }

        return {
            "mode":
                "incremental",

            "pages":
                impact
                .impacted_new_pages,

            "trades":
                tuple(
                    trade.value
                    for trade
                    in impact
                    .impacted_trades
                ),

            "invalidate":
                impact
                .invalidated_candidate_ids,
        }
