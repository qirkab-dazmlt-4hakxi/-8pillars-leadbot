from __future__ import annotations

import math
import re

from dataclasses import dataclass
from enum import Enum
from typing import Any


PDF_POINTS_PER_INCH = 72.0


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class TradeKind(str, Enum):
    CONCRETE = "concrete"
    EARTHWORK = "earthwork"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    ARCHITECTURAL = "architectural"
    COORDINATION = "coordination"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    page_number: int | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class ScaleEvidence:
    raw_text: str
    paper_inches: float
    real_feet: float
    confidence: float

    def __post_init__(self) -> None:
        if self.paper_inches <= 0:
            raise ValueError(
                "paper scale must be positive"
            )

        if self.real_feet <= 0:
            raise ValueError(
                "real scale must be positive"
            )

        if not 0 <= self.confidence <= 1:
            raise ValueError(
                "confidence must be 0-1"
            )

    @property
    def feet_per_paper_inch(
        self,
    ) -> float:
        return (
            self.real_feet
            / self.paper_inches
        )


@dataclass(frozen=True)
class QuantityCandidate:
    candidate_id: str
    trade: TradeKind
    page_number: int
    sheet_number: str | None
    description: str
    quantity: float
    unit: str
    source_ref: str
    confidence: float
    evidence_type: str
    requires_review: bool


@dataclass(frozen=True)
class SheetVectorTakeoff:
    page_number: int
    sheet_number: str | None
    trade: TradeKind
    source_ref: str
    scale: ScaleEvidence | None
    candidates: tuple[
        QuantityCandidate,
        ...
    ]
    findings: tuple[
        Finding,
        ...
    ]

    @property
    def blockers(
        self,
    ) -> tuple[
        Finding,
        ...
    ]:
        return tuple(
            item
            for item in self.findings
            if item.severity
            == Severity.BLOCKER
        )


@dataclass(frozen=True)
class PlanVectorTakeoff:
    document_id: str
    sheets: tuple[
        SheetVectorTakeoff,
        ...
    ]
    findings: tuple[
        Finding,
        ...
    ]

    @property
    def candidates(
        self,
    ) -> tuple[
        QuantityCandidate,
        ...
    ]:
        return tuple(
            candidate
            for sheet in self.sheets
            for candidate
            in sheet.candidates
        )

    @property
    def blockers(
        self,
    ) -> tuple[
        Finding,
        ...
    ]:
        return tuple(
            [
                item
                for item in self.findings
                if (
                    item.severity
                    == Severity.BLOCKER
                )
            ]
            + [
                item
                for sheet in self.sheets
                for item in sheet.blockers
            ]
        )

    @property
    def ready_for_final_pricing(
        self,
    ) -> bool:
        return (
            bool(self.candidates)
            and not self.blockers
            and not any(
                candidate.requires_review
                for candidate
                in self.candidates
            )
        )


SCALE_RE = re.compile(
    r"""
    (?P<paper>
        \d+/\d+
        |
        \d+(?:\.\d+)?
    )
    \s*["”]
    \s*=\s*
    (?P<feet>
        \d+(?:\.\d+)?
    )
    \s*['’]
    (?:
        \s*-\s*
        (?P<inches>
            \d+(?:\.\d+)?
        )
        \s*["”]
    )?
    """,
    re.I | re.X,
)


def _fraction(
    value: str,
) -> float:
    if "/" not in value:
        return float(value)

    numerator, denominator = (
        value.split(
            "/",
            1,
        )
    )

    denominator_value = float(
        denominator
    )

    if denominator_value == 0:
        raise ValueError(
            "scale denominator "
            "cannot be zero"
        )

    return (
        float(numerator)
        / denominator_value
    )


def parse_scale(
    text: str | None,
) -> ScaleEvidence | None:
    if not text:
        return None

    upper = text.upper()

    if (
        "NOT TO SCALE" in upper
        or "N.T.S." in upper
        or upper.strip() == "NTS"
    ):
        return None

    match = SCALE_RE.search(
        text
    )

    if not match:
        return None

    paper = _fraction(
        match.group(
            "paper"
        )
    )

    feet = float(
        match.group(
            "feet"
        )
    )

    inches = float(
        match.group(
            "inches"
        )
        or 0
    )

    return ScaleEvidence(
        raw_text=(
            match.group(0)
            .strip()
        ),
        paper_inches=paper,
        real_feet=(
            feet
            + inches / 12.0
        ),
        confidence=0.99,
    )


def trade_from_sheet(
    sheet_number: str | None,
    text: str = "",
) -> TradeKind:
    if sheet_number:
        prefix = (
            sheet_number
            .upper()[0]
        )

        mapping = {
            "S": TradeKind.CONCRETE,
            "C": TradeKind.EARTHWORK,
            "E": TradeKind.ELECTRICAL,
            "P": TradeKind.PLUMBING,
            "A": TradeKind.ARCHITECTURAL,
        }

        if prefix in mapping:
            return mapping[
                prefix
            ]

    upper = text.upper()

    if any(
        term in upper
        for term in (
            "FOUNDATION",
            "REBAR",
            "CONCRETE",
            "SLAB",
        )
    ):
        return TradeKind.CONCRETE

    if any(
        term in upper
        for term in (
            "GRADING",
            "EARTHWORK",
            "EXCAVATION",
        )
    ):
        return TradeKind.EARTHWORK

    if any(
        term in upper
        for term in (
            "POWER PLAN",
            "ELECTRICAL",
            "FEEDER",
        )
    ):
        return TradeKind.ELECTRICAL

    if any(
        term in upper
        for term in (
            "PLUMBING",
            "SANITARY",
            "DOMESTIC WATER",
        )
    ):
        return TradeKind.PLUMBING

    return TradeKind.COORDINATION


def _length_points(
    segment: Any,
) -> float:
    if hasattr(
        segment,
        "length_points",
    ):
        return float(
            segment.length_points
        )

    start = segment.start
    end = segment.end

    return math.hypot(
        float(end[0])
        - float(start[0]),
        float(end[1])
        - float(start[1]),
    )


def _area_points2(
    rectangle: Any,
) -> float:
    if hasattr(
        rectangle,
        "area_points2",
    ):
        return float(
            rectangle.area_points2
        )

    x0, y0, x1, y1 = (
        rectangle.bbox
    )

    return abs(
        (float(x1) - float(x0))
        * (float(y1) - float(y0))
    )


class PdfVectorTakeoffBridge:
    """
    Deterministic PDF coordinate conversion.

    Native geometry is measured here.
    Semantic construction classification remains
    review-gated until supported by callouts,
    details and neighboring evidence.
    """

    def analyze(
        self,
        document: Any,
    ) -> PlanVectorTakeoff:
        sheets: list[
            SheetVectorTakeoff
        ] = []

        document_findings: list[
            Finding
        ] = []

        pages = tuple(
            getattr(
                document,
                "pages",
                (),
            )
        )

        if not pages:
            document_findings.append(
                Finding(
                    code="NO_PAGES",
                    severity=(
                        Severity.BLOCKER
                    ),
                    message=(
                        "Document contains "
                        "no pages."
                    ),
                )
            )

        seen_scales: dict[
            str,
            set[float],
        ] = {}

        for page in pages:
            page_number = int(
                getattr(
                    page,
                    "page_number",
                    0,
                )
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

            source_ref = str(
                getattr(
                    page,
                    "source_ref",
                    f"page:{page_number}",
                )
            )

            trade = trade_from_sheet(
                sheet_number,
                text,
            )

            scale = parse_scale(
                getattr(
                    page,
                    "scale_text",
                    None,
                )
                or text
            )

            segments = tuple(
                getattr(
                    page,
                    "segments",
                    (),
                )
            )

            rectangles = tuple(
                getattr(
                    page,
                    "rectangles",
                    (),
                )
            )

            findings: list[
                Finding
            ] = []

            candidates: list[
                QuantityCandidate
            ] = []

            if (
                segments
                or rectangles
            ) and scale is None:
                findings.append(
                    Finding(
                        code=(
                            "VECTOR_SCALE_UNRESOLVED"
                        ),
                        severity=(
                            Severity.BLOCKER
                        ),
                        message=(
                            "Native vectors exist "
                            "but drawing scale is "
                            "unresolved. Scale will "
                            "not be inferred."
                        ),
                        page_number=(
                            page_number
                        ),
                        source_ref=(
                            source_ref
                        ),
                    )
                )

            if (
                scale is not None
                and sheet_number
            ):
                seen_scales.setdefault(
                    sheet_number,
                    set(),
                ).add(
                    round(
                        scale
                        .feet_per_paper_inch,
                        8,
                    )
                )

            if scale is not None:
                linear_factor = (
                    scale
                    .feet_per_paper_inch
                    / PDF_POINTS_PER_INCH
                )

                area_factor = (
                    linear_factor
                    ** 2
                )

                for index, segment in enumerate(
                    segments
                ):
                    length = (
                        _length_points(
                            segment
                        )
                    )

                    if (
                        not math.isfinite(
                            length
                        )
                        or length <= 0
                    ):
                        findings.append(
                            Finding(
                                code=(
                                    "INVALID_VECTOR_LINE"
                                ),
                                severity=(
                                    Severity.WARNING
                                ),
                                message=(
                                    "Invalid or "
                                    "zero-length vector "
                                    "ignored."
                                ),
                                page_number=(
                                    page_number
                                ),
                                source_ref=(
                                    source_ref
                                ),
                            )
                        )

                        continue

                    source_id = str(
                        getattr(
                            segment,
                            "segment_id",
                            (
                                f"line-"
                                f"{page_number}-"
                                f"{index}"
                            ),
                        )
                    )

                    candidates.append(
                        QuantityCandidate(
                            candidate_id=(
                                f"LF:{source_id}"
                            ),
                            trade=trade,
                            page_number=(
                                page_number
                            ),
                            sheet_number=(
                                sheet_number
                            ),
                            description=(
                                "Native vector "
                                "linear measurement"
                            ),
                            quantity=(
                                length
                                * linear_factor
                            ),
                            unit="LF",
                            source_ref=str(
                                getattr(
                                    segment,
                                    "source_ref",
                                    source_ref,
                                )
                            ),
                            confidence=(
                                scale.confidence
                            ),
                            evidence_type=(
                                "pdf_vector_line"
                            ),
                            requires_review=True,
                        )
                    )

                for index, rectangle in enumerate(
                    rectangles
                ):
                    area = (
                        _area_points2(
                            rectangle
                        )
                    )

                    if (
                        not math.isfinite(
                            area
                        )
                        or area <= 0
                    ):
                        findings.append(
                            Finding(
                                code=(
                                    "INVALID_VECTOR_AREA"
                                ),
                                severity=(
                                    Severity.WARNING
                                ),
                                message=(
                                    "Invalid or "
                                    "zero-area vector "
                                    "ignored."
                                ),
                                page_number=(
                                    page_number
                                ),
                                source_ref=(
                                    source_ref
                                ),
                            )
                        )

                        continue

                    source_id = str(
                        getattr(
                            rectangle,
                            "rectangle_id",
                            (
                                f"area-"
                                f"{page_number}-"
                                f"{index}"
                            ),
                        )
                    )

                    candidates.append(
                        QuantityCandidate(
                            candidate_id=(
                                f"SF:{source_id}"
                            ),
                            trade=trade,
                            page_number=(
                                page_number
                            ),
                            sheet_number=(
                                sheet_number
                            ),
                            description=(
                                "Native vector "
                                "area measurement"
                            ),
                            quantity=(
                                area
                                * area_factor
                            ),
                            unit="SF",
                            source_ref=str(
                                getattr(
                                    rectangle,
                                    "source_ref",
                                    source_ref,
                                )
                            ),
                            confidence=(
                                scale.confidence
                            ),
                            evidence_type=(
                                "pdf_vector_rectangle"
                            ),
                            requires_review=True,
                        )
                    )

            sheets.append(
                SheetVectorTakeoff(
                    page_number=(
                        page_number
                    ),
                    sheet_number=(
                        sheet_number
                    ),
                    trade=trade,
                    source_ref=(
                        source_ref
                    ),
                    scale=scale,
                    candidates=tuple(
                        candidates
                    ),
                    findings=tuple(
                        findings
                    ),
                )
            )

        for sheet_number, scales in (
            seen_scales.items()
        ):
            if len(scales) > 1:
                document_findings.append(
                    Finding(
                        code=(
                            "CONFLICTING_SHEET_SCALE"
                        ),
                        severity=(
                            Severity.BLOCKER
                        ),
                        message=(
                            f"Sheet {sheet_number} "
                            "contains conflicting "
                            "scale evidence."
                        ),
                    )
                )

        return PlanVectorTakeoff(
            document_id=str(
                getattr(
                    document,
                    "document_id",
                    "unknown",
                )
            ),
            sheets=tuple(
                sheets
            ),
            findings=tuple(
                document_findings
            ),
        )
