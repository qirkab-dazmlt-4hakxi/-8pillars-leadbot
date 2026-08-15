from __future__ import annotations

import math
import re

from dataclasses import dataclass
from enum import Enum
from typing import Any

from leadbot_v2.goat.preconstruction.integration.vector_takeoff import (
    PdfVectorTakeoffBridge,
    QuantityCandidate,
    Severity,
    TradeKind,
)


class SemanticKind(str, Enum):
    SLAB = "slab"
    FOOTING = "footing"
    GRADE_BEAM = "grade_beam"
    CONCRETE_WALL = "concrete_wall"
    TRENCH = "trench"
    CONDUIT_RUN = "conduit_run"
    PIPE_RUN = "pipe_run"
    UNRESOLVED = "unresolved"


class GeometryKind(str, Enum):
    LINE = "line"
    AREA = "area"


@dataclass(frozen=True)
class SemanticFinding:
    code: str
    severity: Severity
    message: str
    candidate_id: str | None = None
    page_number: int | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class SemanticEvidence:
    kind: SemanticKind
    text: str
    lexical_score: float
    proximity_score: float
    trade_score: float
    geometry_score: float
    dimension_score: float
    total_score: float
    distance_points: float | None
    source_ref: str


@dataclass(frozen=True)
class DimensionalEvidence:
    thickness_inches: float | None = None
    width_inches: float | None = None
    depth_inches: float | None = None


@dataclass(frozen=True)
class SemanticCandidate:
    candidate_id: str

    semantic_kind: SemanticKind
    geometry_kind: GeometryKind

    trade: TradeKind

    page_number: int
    sheet_number: str | None

    quantity: float
    unit: str

    source_ref: str

    semantic_confidence: float
    measurement_confidence: float

    evidence: tuple[
        SemanticEvidence,
        ...
    ]

    dimensions: DimensionalEvidence

    requires_review: bool
    auto_classified: bool

    derived_volume_cy: float | None = None

    @property
    def ready_for_pricing(
        self,
    ) -> bool:
        return (
            self.semantic_kind
            != SemanticKind.UNRESOLVED
            and not self.requires_review
            and self.auto_classified
        )


@dataclass(frozen=True)
class SemanticTakeoff:
    document_id: str

    candidates: tuple[
        SemanticCandidate,
        ...
    ]

    findings: tuple[
        SemanticFinding,
        ...
    ]

    @property
    def blockers(
        self,
    ) -> tuple[
        SemanticFinding,
        ...
    ]:
        return tuple(
            item
            for item in self.findings
            if item.severity
            == Severity.BLOCKER
        )

    @property
    def review_candidates(
        self,
    ) -> tuple[
        SemanticCandidate,
        ...
    ]:
        return tuple(
            item
            for item in self.candidates
            if item.requires_review
        )

    @property
    def pricing_candidates(
        self,
    ) -> tuple[
        SemanticCandidate,
        ...
    ]:
        return tuple(
            item
            for item in self.candidates
            if item.ready_for_pricing
        )

    @property
    def ready_for_pricing(
        self,
    ) -> bool:
        return (
            bool(self.pricing_candidates)
            and not self.blockers
            and not self.review_candidates
        )


STRONG_PATTERNS: dict[
    SemanticKind,
    tuple[
        re.Pattern,
        ...
    ],
] = {
    SemanticKind.SLAB: (
        re.compile(
            r"\bSLAB\s+ON\s+GRADE\b",
            re.I,
        ),
        re.compile(
            r"\bS\.?O\.?G\.?\b",
            re.I,
        ),
        re.compile(
            r"\bCONCRETE\s+SLAB\b",
            re.I,
        ),
    ),

    SemanticKind.FOOTING: (
        re.compile(
            r"\bCONTINUOUS\s+FOOTING\b",
            re.I,
        ),
        re.compile(
            r"\bSPREAD\s+FOOTING\b",
            re.I,
        ),
        re.compile(
            r"\bFOOTING\b",
            re.I,
        ),
        re.compile(
            r"\bFTG\b",
            re.I,
        ),
    ),

    SemanticKind.GRADE_BEAM: (
        re.compile(
            r"\bGRADE\s+BEAM\b",
            re.I,
        ),
        re.compile(
            r"\bGB[-\s]?\d+\b",
            re.I,
        ),
    ),

    SemanticKind.CONCRETE_WALL: (
        re.compile(
            r"\bRETAINING\s+WALL\b",
            re.I,
        ),
        re.compile(
            r"\bCONCRETE\s+WALL\b",
            re.I,
        ),
        re.compile(
            r"\bCIP\s+WALL\b",
            re.I,
        ),
        re.compile(
            r"\bCAST[-\s]+IN[-\s]+PLACE\s+WALL\b",
            re.I,
        ),
    ),

    SemanticKind.TRENCH: (
        re.compile(
            r"\bUTILITY\s+TRENCH\b",
            re.I,
        ),
        re.compile(
            r"\bPIPE\s+TRENCH\b",
            re.I,
        ),
        re.compile(
            r"\bTRENCH\b",
            re.I,
        ),
        re.compile(
            r"\bEXCAVATION\b",
            re.I,
        ),
    ),

    SemanticKind.CONDUIT_RUN: (
        re.compile(
            r"\bCONDUIT\b",
            re.I,
        ),
        re.compile(
            r"\bEMT\b",
            re.I,
        ),
        re.compile(
            r"\bRMC\b",
            re.I,
        ),
        re.compile(
            r"\bIMC\b",
            re.I,
        ),
        re.compile(
            r"\bFEEDER\b",
            re.I,
        ),
    ),

    SemanticKind.PIPE_RUN: (
        re.compile(
            r"\bSANITARY\b",
            re.I,
        ),
        re.compile(
            r"\bDOMESTIC\s+WATER\b",
            re.I,
        ),
        re.compile(
            r"\bSTORM\b",
            re.I,
        ),
        re.compile(
            r"\bWASTE\b",
            re.I,
        ),
        re.compile(
            r"\bVENT\b",
            re.I,
        ),
        re.compile(
            r"\bPVC\b",
            re.I,
        ),
        re.compile(
            r"\bCOPPER\b",
            re.I,
        ),
    ),
}


WEAK_PATTERNS: dict[
    SemanticKind,
    tuple[
        re.Pattern,
        ...
    ],
] = {
    SemanticKind.SLAB: (
        re.compile(
            r"\bSLAB\b",
            re.I,
        ),
        re.compile(
            r"\bCONC\b",
            re.I,
        ),
    ),

    SemanticKind.FOOTING: (
        re.compile(
            r"\bFOUNDATION\b",
            re.I,
        ),
    ),

    SemanticKind.GRADE_BEAM: (
        re.compile(
            r"\bBEAM\b",
            re.I,
        ),
    ),

    SemanticKind.CONCRETE_WALL: (
        re.compile(
            r"\bWALL\b",
            re.I,
        ),
    ),

    SemanticKind.TRENCH: (
        re.compile(
            r"\bCUT\b",
            re.I,
        ),
        re.compile(
            r"\bBACKFILL\b",
            re.I,
        ),
    ),

    SemanticKind.CONDUIT_RUN: (
        re.compile(
            r"\bELECTRICAL\b",
            re.I,
        ),
        re.compile(
            r"\bPOWER\b",
            re.I,
        ),
    ),

    SemanticKind.PIPE_RUN: (
        re.compile(
            r"\bPLUMBING\b",
            re.I,
        ),
        re.compile(
            r"\bPIPE\b",
            re.I,
        ),
    ),
}


TRADE_COMPATIBILITY: dict[
    SemanticKind,
    set[
        TradeKind
    ],
] = {
    SemanticKind.SLAB: {
        TradeKind.CONCRETE,
        TradeKind.ARCHITECTURAL,
    },

    SemanticKind.FOOTING: {
        TradeKind.CONCRETE,
    },

    SemanticKind.GRADE_BEAM: {
        TradeKind.CONCRETE,
    },

    SemanticKind.CONCRETE_WALL: {
        TradeKind.CONCRETE,
        TradeKind.ARCHITECTURAL,
    },

    SemanticKind.TRENCH: {
        TradeKind.EARTHWORK,
        TradeKind.PLUMBING,
        TradeKind.ELECTRICAL,
    },

    SemanticKind.CONDUIT_RUN: {
        TradeKind.ELECTRICAL,
    },

    SemanticKind.PIPE_RUN: {
        TradeKind.PLUMBING,
    },
}


GEOMETRY_COMPATIBILITY: dict[
    SemanticKind,
    set[
        GeometryKind
    ],
] = {
    SemanticKind.SLAB: {
        GeometryKind.AREA,
    },

    SemanticKind.FOOTING: {
        GeometryKind.LINE,
        GeometryKind.AREA,
    },

    SemanticKind.GRADE_BEAM: {
        GeometryKind.LINE,
    },

    SemanticKind.CONCRETE_WALL: {
        GeometryKind.LINE,
    },

    SemanticKind.TRENCH: {
        GeometryKind.LINE,
    },

    SemanticKind.CONDUIT_RUN: {
        GeometryKind.LINE,
    },

    SemanticKind.PIPE_RUN: {
        GeometryKind.LINE,
    },
}


THICKNESS_PATTERNS = (
    re.compile(
        r'(?P<value>\d+(?:\.\d+)?)\s*["”]\s*'
        r'(?:SOG|SLAB|CONCRETE\s+SLAB)',
        re.I,
    ),
    re.compile(
        r'(?:SOG|SLAB)\s*'
        r'(?P<value>\d+(?:\.\d+)?)\s*["”]',
        re.I,
    ),
)


WIDTH_DEPTH_PATTERN = re.compile(
    r"""
    (?P<width>
        \d+(?:\.\d+)?
    )
    \s*["”]
    \s*
    [xX]
    \s*
    (?P<depth>
        \d+(?:\.\d+)?
    )
    \s*["”]
    """,
    re.X,
)


def _center(
    bbox: tuple[
        float,
        float,
        float,
        float,
    ],
) -> tuple[
    float,
    float,
]:
    x0, y0, x1, y1 = bbox

    return (
        (x0 + x1) / 2.0,
        (y0 + y1) / 2.0,
    )


def _distance(
    first: tuple[
        float,
        float,
    ],
    second: tuple[
        float,
        float,
    ],
) -> float:
    return math.hypot(
        first[0] - second[0],
        first[1] - second[1],
    )


def _geometry_center(
    geometry: Any,
) -> tuple[
    float,
    float,
]:
    if hasattr(
        geometry,
        "bbox",
    ):
        return _center(
            tuple(
                float(value)
                for value
                in geometry.bbox
            )
        )

    start = geometry.start
    end = geometry.end

    return (
        (
            float(start[0])
            + float(end[0])
        )
        / 2.0,
        (
            float(start[1])
            + float(end[1])
        )
        / 2.0,
    )


def _proximity_score(
    distance_points: float,
) -> float:
    if distance_points <= 36:
        return 0.18

    if distance_points <= 72:
        return 0.15

    if distance_points <= 144:
        return 0.11

    if distance_points <= 288:
        return 0.06

    if distance_points <= 576:
        return 0.02

    return 0.0


def _lexical_score(
    kind: SemanticKind,
    text: str,
) -> float:
    if any(
        pattern.search(
            text
        )
        for pattern
        in STRONG_PATTERNS[
            kind
        ]
    ):
        return 0.55

    if any(
        pattern.search(
            text
        )
        for pattern
        in WEAK_PATTERNS[
            kind
        ]
    ):
        return 0.30

    return 0.0


def _dimensions(
    text: str,
) -> DimensionalEvidence:
    thickness = None
    width = None
    depth = None

    for pattern in (
        THICKNESS_PATTERNS
    ):
        match = pattern.search(
            text
        )

        if match:
            thickness = float(
                match.group(
                    "value"
                )
            )

            break

    match = (
        WIDTH_DEPTH_PATTERN
        .search(
            text
        )
    )

    if match:
        width = float(
            match.group(
                "width"
            )
        )

        depth = float(
            match.group(
                "depth"
            )
        )

    return DimensionalEvidence(
        thickness_inches=(
            thickness
        ),
        width_inches=width,
        depth_inches=depth,
    )


class SemanticGeometryResolver:
    """
    Correlates scaled native PDF geometry with nearby plan text.

    High-confidence classification requires:
      * lexical evidence
      * geometry compatibility
      * trade compatibility
      * spatial proximity
      * meaningful separation from competing classifications

    Ambiguous evidence remains unresolved/review-required.
    """

    def __init__(
        self,
        *,
        auto_threshold: float = 0.90,
        review_threshold: float = 0.62,
        minimum_margin: float = 0.14,
    ) -> None:
        if not (
            0
            < review_threshold
            <= auto_threshold
            <= 1
        ):
            raise ValueError(
                "invalid semantic thresholds"
            )

        self.auto_threshold = (
            auto_threshold
        )

        self.review_threshold = (
            review_threshold
        )

        self.minimum_margin = (
            minimum_margin
        )

        self.bridge = (
            PdfVectorTakeoffBridge()
        )

    @staticmethod
    def _page_map(
        document: Any,
    ) -> dict[
        int,
        Any,
    ]:
        return {
            int(
                page.page_number
            ): page
            for page
            in getattr(
                document,
                "pages",
                (),
            )
        }

    @staticmethod
    def _geometry_map(
        page: Any,
    ) -> dict[
        str,
        tuple[
            GeometryKind,
            Any,
        ],
    ]:
        result: dict[
            str,
            tuple[
                GeometryKind,
                Any,
            ],
        ] = {}

        for segment in getattr(
            page,
            "segments",
            (),
        ):
            result[
                str(
                    segment.segment_id
                )
            ] = (
                GeometryKind.LINE,
                segment,
            )

        for rectangle in getattr(
            page,
            "rectangles",
            (),
        ):
            result[
                str(
                    rectangle.rectangle_id
                )
            ] = (
                GeometryKind.AREA,
                rectangle,
            )

        return result

    @staticmethod
    def _source_geometry_id(
        candidate: QuantityCandidate,
    ) -> str:
        if ":" not in (
            candidate.candidate_id
        ):
            return (
                candidate.candidate_id
            )

        return (
            candidate.candidate_id
            .split(
                ":",
                1,
            )[1]
        )

    @staticmethod
    def _span_entries(
        page: Any,
    ) -> tuple[
        tuple[
            str,
            tuple[
                float,
                float,
            ],
            str,
        ],
        ...
    ]:
        entries = []

        source_ref = str(
            getattr(
                page,
                "source_ref",
                "",
            )
        )

        for index, span in enumerate(
            getattr(
                page,
                "text_spans",
                (),
            )
        ):
            text = str(
                getattr(
                    span,
                    "text",
                    "",
                )
                or ""
            )

            bbox = tuple(
                float(value)
                for value
                in span.bbox
            )

            entries.append(
                (
                    text,
                    _center(
                        bbox
                    ),
                    (
                        f"{source_ref}"
                        f"#span={index}"
                    ),
                )
            )

        return tuple(
            entries
        )

    def _score_kind(
        self,
        *,
        kind: SemanticKind,
        candidate: QuantityCandidate,
        geometry_kind: GeometryKind,
        geometry_center: tuple[
            float,
            float,
        ],
        spans: tuple[
            tuple[
                str,
                tuple[
                    float,
                    float,
                ],
                str,
            ],
            ...
        ],
        page_text: str,
        page_source_ref: str,
    ) -> tuple[
        SemanticEvidence,
        DimensionalEvidence,
    ]:
        best: SemanticEvidence | None = None
        best_dimensions = (
            DimensionalEvidence()
        )

        for (
            text,
            span_center,
            span_source,
        ) in spans:
            lexical = (
                _lexical_score(
                    kind,
                    text,
                )
            )

            if lexical <= 0:
                continue

            distance = _distance(
                geometry_center,
                span_center,
            )

            proximity = (
                _proximity_score(
                    distance
                )
            )

            trade_score = (
                0.14
                if candidate.trade
                in TRADE_COMPATIBILITY[
                    kind
                ]
                else 0.0
            )

            geometry_score = (
                0.10
                if geometry_kind
                in GEOMETRY_COMPATIBILITY[
                    kind
                ]
                else 0.0
            )

            dims = _dimensions(
                text
            )

            dimensional_score = 0.0

            if (
                kind
                == SemanticKind.SLAB
                and dims
                .thickness_inches
                is not None
            ):
                dimensional_score = (
                    0.08
                )

            elif (
                kind
                in {
                    SemanticKind.FOOTING,
                    SemanticKind.GRADE_BEAM,
                    SemanticKind.TRENCH,
                }
                and dims.width_inches
                is not None
                and dims.depth_inches
                is not None
            ):
                dimensional_score = (
                    0.06
                )

            total = min(
                1.0,
                lexical
                + proximity
                + trade_score
                + geometry_score
                + dimensional_score,
            )

            evidence = (
                SemanticEvidence(
                    kind=kind,
                    text=text,
                    lexical_score=(
                        lexical
                    ),
                    proximity_score=(
                        proximity
                    ),
                    trade_score=(
                        trade_score
                    ),
                    geometry_score=(
                        geometry_score
                    ),
                    dimension_score=(
                        dimensional_score
                    ),
                    total_score=(
                        total
                    ),
                    distance_points=(
                        distance
                    ),
                    source_ref=(
                        span_source
                    ),
                )
            )

            if (
                best is None
                or evidence.total_score
                > best.total_score
            ):
                best = evidence
                best_dimensions = dims

        if best is None:
            lexical = (
                _lexical_score(
                    kind,
                    page_text,
                )
            )

            trade_score = (
                0.10
                if candidate.trade
                in TRADE_COMPATIBILITY[
                    kind
                ]
                else 0.0
            )

            geometry_score = (
                0.07
                if geometry_kind
                in GEOMETRY_COMPATIBILITY[
                    kind
                ]
                else 0.0
            )

            dims = _dimensions(
                page_text
            )

            dimensional_score = (
                0.04
                if (
                    kind
                    == SemanticKind.SLAB
                    and dims
                    .thickness_inches
                    is not None
                )
                else 0.0
            )

            # Page-level evidence receives no proximity credit
            # and therefore cannot normally auto-classify alone.
            total = min(
                0.79,
                lexical
                + trade_score
                + geometry_score
                + dimensional_score,
            )

            best = (
                SemanticEvidence(
                    kind=kind,
                    text=page_text,
                    lexical_score=(
                        lexical
                    ),
                    proximity_score=0.0,
                    trade_score=(
                        trade_score
                    ),
                    geometry_score=(
                        geometry_score
                    ),
                    dimension_score=(
                        dimensional_score
                    ),
                    total_score=(
                        total
                    ),
                    distance_points=None,
                    source_ref=(
                        page_source_ref
                    ),
                )
            )

            best_dimensions = dims

        return (
            best,
            best_dimensions,
        )

    @staticmethod
    def _derived_volume(
        *,
        semantic_kind: SemanticKind,
        candidate: QuantityCandidate,
        dimensions: DimensionalEvidence,
    ) -> float | None:
        if (
            semantic_kind
            == SemanticKind.SLAB
            and candidate.unit == "SF"
            and dimensions
            .thickness_inches
            is not None
        ):
            thickness_ft = (
                dimensions
                .thickness_inches
                / 12.0
            )

            return (
                candidate.quantity
                * thickness_ft
                / 27.0
            )

        return None

    def resolve(
        self,
        document: Any,
    ) -> SemanticTakeoff:
        vector_takeoff = (
            self.bridge.analyze(
                document
            )
        )

        page_map = (
            self._page_map(
                document
            )
        )

        findings: list[
            SemanticFinding
        ] = []

        candidates: list[
            SemanticCandidate
        ] = []

        for blocker in (
            vector_takeoff.blockers
        ):
            findings.append(
                SemanticFinding(
                    code=blocker.code,
                    severity=(
                        blocker.severity
                    ),
                    message=(
                        blocker.message
                    ),
                    page_number=(
                        blocker.page_number
                    ),
                    source_ref=(
                        blocker.source_ref
                    ),
                )
            )

        for candidate in (
            vector_takeoff.candidates
        ):
            page = page_map.get(
                candidate.page_number
            )

            if page is None:
                findings.append(
                    SemanticFinding(
                        code=(
                            "PAGE_EVIDENCE_MISSING"
                        ),
                        severity=(
                            Severity.BLOCKER
                        ),
                        message=(
                            "Measured geometry "
                            "references a missing "
                            "page evidence record."
                        ),
                        candidate_id=(
                            candidate
                            .candidate_id
                        ),
                        page_number=(
                            candidate
                            .page_number
                        ),
                        source_ref=(
                            candidate
                            .source_ref
                        ),
                    )
                )

                continue

            geometry_map = (
                self._geometry_map(
                    page
                )
            )

            geometry_id = (
                self._source_geometry_id(
                    candidate
                )
            )

            geometry_entry = (
                geometry_map.get(
                    geometry_id
                )
            )

            if geometry_entry is None:
                findings.append(
                    SemanticFinding(
                        code=(
                            "GEOMETRY_EVIDENCE_MISSING"
                        ),
                        severity=(
                            Severity.BLOCKER
                        ),
                        message=(
                            "Measured quantity "
                            "cannot be matched to "
                            "its native geometry."
                        ),
                        candidate_id=(
                            candidate
                            .candidate_id
                        ),
                        page_number=(
                            candidate
                            .page_number
                        ),
                        source_ref=(
                            candidate
                            .source_ref
                        ),
                    )
                )

                continue

            (
                geometry_kind,
                geometry,
            ) = geometry_entry

            center = (
                _geometry_center(
                    geometry
                )
            )

            spans = (
                self._span_entries(
                    page
                )
            )

            page_text = str(
                getattr(
                    page,
                    "text",
                    "",
                )
                or ""
            )

            page_source = str(
                getattr(
                    page,
                    "source_ref",
                    candidate.source_ref,
                )
            )

            scored = []

            for semantic_kind in (
                SemanticKind.SLAB,
                SemanticKind.FOOTING,
                SemanticKind.GRADE_BEAM,
                SemanticKind.CONCRETE_WALL,
                SemanticKind.TRENCH,
                SemanticKind.CONDUIT_RUN,
                SemanticKind.PIPE_RUN,
            ):
                evidence, dims = (
                    self._score_kind(
                        kind=semantic_kind,
                        candidate=candidate,
                        geometry_kind=(
                            geometry_kind
                        ),
                        geometry_center=(
                            center
                        ),
                        spans=spans,
                        page_text=(
                            page_text
                        ),
                        page_source_ref=(
                            page_source
                        ),
                    )
                )

                scored.append(
                    (
                        evidence
                        .total_score,
                        semantic_kind,
                        evidence,
                        dims,
                    )
                )

            scored.sort(
                key=lambda item:
                    item[0],
                reverse=True,
            )

            (
                top_score,
                top_kind,
                top_evidence,
                top_dimensions,
            ) = scored[0]

            second_score = (
                scored[1][0]
                if len(scored) > 1
                else 0.0
            )

            margin = (
                top_score
                - second_score
            )

            auto_classified = (
                top_score
                >= self.auto_threshold
                and margin
                >= self.minimum_margin
            )

            if (
                top_score
                < self.review_threshold
            ):
                resolved_kind = (
                    SemanticKind.UNRESOLVED
                )

                requires_review = True

                findings.append(
                    SemanticFinding(
                        code=(
                            "SEMANTIC_EVIDENCE_INSUFFICIENT"
                        ),
                        severity=(
                            Severity.WARNING
                        ),
                        message=(
                            "Geometry measured "
                            "successfully but "
                            "construction meaning "
                            "is unresolved."
                        ),
                        candidate_id=(
                            candidate
                            .candidate_id
                        ),
                        page_number=(
                            candidate
                            .page_number
                        ),
                        source_ref=(
                            candidate
                            .source_ref
                        ),
                    )
                )

            elif (
                margin
                < self.minimum_margin
            ):
                resolved_kind = (
                    top_kind
                )

                requires_review = True

                findings.append(
                    SemanticFinding(
                        code=(
                            "SEMANTIC_EVIDENCE_CONFLICT"
                        ),
                        severity=(
                            Severity.WARNING
                        ),
                        message=(
                            "Competing semantic "
                            "classifications are "
                            "too close for automatic "
                            "acceptance."
                        ),
                        candidate_id=(
                            candidate
                            .candidate_id
                        ),
                        page_number=(
                            candidate
                            .page_number
                        ),
                        source_ref=(
                            candidate
                            .source_ref
                        ),
                    )
                )

            else:
                resolved_kind = (
                    top_kind
                )

                requires_review = (
                    not auto_classified
                )

            evidence_tuple = tuple(
                item[2]
                for item
                in scored
                if item[0] > 0
            )

            derived_volume = (
                self._derived_volume(
                    semantic_kind=(
                        resolved_kind
                    ),
                    candidate=(
                        candidate
                    ),
                    dimensions=(
                        top_dimensions
                    ),
                )
            )

            candidates.append(
                SemanticCandidate(
                    candidate_id=(
                        candidate
                        .candidate_id
                    ),
                    semantic_kind=(
                        resolved_kind
                    ),
                    geometry_kind=(
                        geometry_kind
                    ),
                    trade=(
                        candidate.trade
                    ),
                    page_number=(
                        candidate
                        .page_number
                    ),
                    sheet_number=(
                        candidate
                        .sheet_number
                    ),
                    quantity=(
                        candidate.quantity
                    ),
                    unit=(
                        candidate.unit
                    ),
                    source_ref=(
                        candidate
                        .source_ref
                    ),
                    semantic_confidence=(
                        top_score
                    ),
                    measurement_confidence=(
                        candidate.confidence
                    ),
                    evidence=(
                        evidence_tuple
                    ),
                    dimensions=(
                        top_dimensions
                    ),
                    requires_review=(
                        requires_review
                    ),
                    auto_classified=(
                        auto_classified
                    ),
                    derived_volume_cy=(
                        derived_volume
                    ),
                )
            )

        return SemanticTakeoff(
            document_id=(
                vector_takeoff
                .document_id
            ),
            candidates=tuple(
                candidates
            ),
            findings=tuple(
                findings
            ),
        )
