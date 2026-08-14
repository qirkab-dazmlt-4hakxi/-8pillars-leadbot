from __future__ import annotations

import hashlib
import math
import re

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from leadbot_v2.goat.preconstruction.documents.intelligence import RawPage


try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None


class PdfIngestError(RuntimeError):
    pass


class PdfDependencyError(PdfIngestError):
    pass


class PdfSecurityError(PdfIngestError):
    pass


class PdfLimitError(PdfIngestError):
    pass


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class PdfPageKind(str, Enum):
    VECTOR = "vector"
    HYBRID = "hybrid"
    RASTER = "raster"
    TEXT_ONLY = "text_only"
    EMPTY = "empty"


@dataclass(frozen=True)
class PdfIngestPolicy:
    max_file_bytes: int = 250 * 1024 * 1024
    max_pages: int = 1000
    max_vectors_per_page: int = 150_000
    max_text_chars_per_page: int = 5_000_000
    max_text_spans_per_page: int = 100_000

    def __post_init__(self) -> None:
        values = (
            self.max_file_bytes,
            self.max_pages,
            self.max_vectors_per_page,
            self.max_text_chars_per_page,
            self.max_text_spans_per_page,
        )

        if any(value <= 0 for value in values):
            raise ValueError(
                "PDF limits must be positive"
            )


@dataclass(frozen=True)
class PdfFinding:
    code: str
    severity: FindingSeverity
    message: str
    page_number: int | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class PdfTextSpan:
    text: str
    bbox: tuple[float, float, float, float]
    font: str | None
    size: float | None


@dataclass(frozen=True)
class PdfVectorSegment:
    segment_id: str
    page_number: int
    start: tuple[float, float]
    end: tuple[float, float]
    width_points: float
    source_ref: str

    @property
    def length_points(self) -> float:
        return math.hypot(
            self.end[0] - self.start[0],
            self.end[1] - self.start[1],
        )


@dataclass(frozen=True)
class PdfVectorRectangle:
    rectangle_id: str
    page_number: int
    bbox: tuple[
        float,
        float,
        float,
        float,
    ]
    width_points: float
    source_ref: str

    @property
    def area_points2(self) -> float:
        x0, y0, x1, y1 = self.bbox

        return abs(
            (x1 - x0)
            * (y1 - y0)
        )


@dataclass(frozen=True)
class PdfPageEvidence:
    page_number: int
    width_points: float
    height_points: float
    rotation: int
    text: str
    text_spans: tuple[PdfTextSpan, ...]
    segments: tuple[PdfVectorSegment, ...]
    rectangles: tuple[PdfVectorRectangle, ...]
    image_count: int
    page_kind: PdfPageKind
    source_ref: str
    sheet_hint: str | None
    scale_text: str | None
    findings: tuple[PdfFinding, ...]

    @property
    def vector_count(self) -> int:
        return (
            len(self.segments)
            + len(self.rectangles)
        )

    @property
    def has_vectors(self) -> bool:
        return self.vector_count > 0

    @property
    def blockers(self) -> tuple[PdfFinding, ...]:
        return tuple(
            item
            for item in self.findings
            if (
                item.severity
                == FindingSeverity.BLOCKER
            )
        )


@dataclass(frozen=True)
class PdfDocumentEvidence:
    document_id: str
    file_name: str
    sha256: str
    file_size_bytes: int
    pages: tuple[PdfPageEvidence, ...]
    findings: tuple[PdfFinding, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def blockers(self) -> tuple[PdfFinding, ...]:
        return tuple(
            [
                item
                for item in self.findings
                if (
                    item.severity
                    == FindingSeverity.BLOCKER
                )
            ]
            + [
                item
                for page in self.pages
                for item in page.blockers
            ]
        )

    @property
    def vector_page_count(self) -> int:
        return sum(
            page.has_vectors
            for page in self.pages
        )

    @property
    def ready_for_vector_takeoff(self) -> bool:
        return (
            self.vector_page_count > 0
            and not self.blockers
        )

    @property
    def raw_pages(self) -> tuple[RawPage, ...]:
        return tuple(
            RawPage(
                page_number=page.page_number,
                text=page.text,
                source_ref=page.source_ref,
            )
            for page in self.pages
        )


SHEET_RE = re.compile(
    r"\b(?:SHEET\s+)?"
    r"(?P<sheet>[A-Z]{1,3}\d{1,3}(?:\.\d{1,3})?)\b",
    re.I,
)


ARCH_SCALE_RE = re.compile(
    r'(?P<paper>\d+/\d+|\d+(?:\.\d+)?)'
    r'\s*["”]\s*=\s*'
    r'(?P<feet>\d+(?:\.\d+)?)'
    r"\s*['’]"
    r'(?:\s*-\s*(?P<inches>\d+(?:\.\d+)?)\s*["”])?',
    re.I,
)


def detect_sheet_hint(
    text: str,
) -> str | None:
    match = SHEET_RE.search(
        text or ""
    )

    if not match:
        return None

    return (
        match.group("sheet")
        .upper()
    )


def detect_scale_text(
    text: str,
) -> str | None:
    source = text or ""

    upper = source.upper()

    if (
        "NOT TO SCALE" in upper
        or "N.T.S." in upper
    ):
        return None

    match = ARCH_SCALE_RE.search(
        source
    )

    if not match:
        return None

    return match.group(0).strip()


def _finite(
    value: Any,
) -> float:
    result = float(value)

    if not math.isfinite(result):
        raise ValueError(
            "non-finite PDF coordinate"
        )

    return result


def _point(
    value: Any,
) -> tuple[float, float]:
    if hasattr(value, "x"):
        return (
            _finite(value.x),
            _finite(value.y),
        )

    return (
        _finite(value[0]),
        _finite(value[1]),
    )


def _rect(
    value: Any,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    if hasattr(value, "x0"):
        return (
            _finite(value.x0),
            _finite(value.y0),
            _finite(value.x1),
            _finite(value.y1),
        )

    return (
        _finite(value[0]),
        _finite(value[1]),
        _finite(value[2]),
        _finite(value[3]),
    )


class PdfIngestEngine:
    """
    Native PDF evidence boundary.

    Unsupported geometry remains unresolved.
    Raster-only pages are not treated as native vector evidence.
    Scale is never invented.
    """

    def __init__(
        self,
        policy: PdfIngestPolicy | None = None,
    ) -> None:
        self.policy = (
            policy
            or PdfIngestPolicy()
        )

    def _require_dependency(self) -> None:
        if fitz is None:
            raise PdfDependencyError(
                "PyMuPDF is required for "
                "native PDF ingestion"
            )

    @staticmethod
    def fingerprint(
        path: Path,
    ) -> str:
        digest = hashlib.sha256()

        with path.open(
            "rb"
        ) as handle:
            for chunk in iter(
                lambda: handle.read(
                    1024 * 1024
                ),
                b"",
            ):
                digest.update(
                    chunk
                )

        return digest.hexdigest()

    def _validate_file(
        self,
        path: Path,
    ) -> int:
        if not path.exists():
            raise FileNotFoundError(
                str(path)
            )

        if not path.is_file():
            raise PdfIngestError(
                "PDF source must be a file"
            )

        size = path.stat().st_size

        if size <= 0:
            raise PdfIngestError(
                "PDF source is empty"
            )

        if (
            size
            > self.policy.max_file_bytes
        ):
            raise PdfLimitError(
                "PDF exceeds size limit"
            )

        with path.open(
            "rb"
        ) as handle:
            if handle.read(5) != b"%PDF-":
                raise PdfIngestError(
                    "invalid PDF header"
                )

        return size

    def _text(
        self,
        page: Any,
        page_number: int,
    ) -> tuple[
        str,
        tuple[PdfTextSpan, ...],
    ]:
        text = (
            page.get_text("text")
            or ""
        )

        if (
            len(text)
            > self.policy
            .max_text_chars_per_page
        ):
            raise PdfLimitError(
                f"page {page_number} "
                "text limit exceeded"
            )

        spans: list[
            PdfTextSpan
        ] = []

        raw = (
            page.get_text("dict")
            or {}
        )

        for block in raw.get(
            "blocks",
            (),
        ):
            if block.get(
                "type",
                0,
            ) != 0:
                continue

            for line in block.get(
                "lines",
                (),
            ):
                for span in line.get(
                    "spans",
                    (),
                ):
                    value = str(
                        span.get(
                            "text",
                            "",
                        )
                    )

                    if not value:
                        continue

                    spans.append(
                        PdfTextSpan(
                            text=value,
                            bbox=_rect(
                                span.get(
                                    "bbox",
                                    (
                                        0,
                                        0,
                                        0,
                                        0,
                                    ),
                                )
                            ),
                            font=(
                                str(
                                    span.get(
                                        "font"
                                    )
                                )
                                if span.get(
                                    "font"
                                )
                                is not None
                                else None
                            ),
                            size=(
                                _finite(
                                    span.get(
                                        "size"
                                    )
                                )
                                if span.get(
                                    "size"
                                )
                                is not None
                                else None
                            ),
                        )
                    )

                    if (
                        len(spans)
                        > self.policy
                        .max_text_spans_per_page
                    ):
                        raise PdfLimitError(
                            f"page {page_number} "
                            "span limit exceeded"
                        )

        return (
            text,
            tuple(spans),
        )

    def _vectors(
        self,
        page: Any,
        page_number: int,
        source_ref: str,
    ) -> tuple[
        tuple[PdfVectorSegment, ...],
        tuple[PdfVectorRectangle, ...],
        int,
    ]:
        segments: list[
            PdfVectorSegment
        ] = []

        rectangles: list[
            PdfVectorRectangle
        ] = []

        unresolved = 0
        count = 0

        drawings = (
            page.get_drawings()
            or ()
        )

        for drawing_index, drawing in enumerate(
            drawings
        ):
            width = _finite(
                drawing.get(
                    "width",
                    0,
                )
            )

            for item_index, item in enumerate(
                drawing.get(
                    "items",
                    (),
                )
            ):
                if not item:
                    continue

                primitive = str(
                    item[0]
                ).lower()

                try:
                    if (
                        primitive == "l"
                        and len(item) >= 3
                    ):
                        segments.append(
                            PdfVectorSegment(
                                segment_id=(
                                    f"p{page_number}"
                                    f"-d{drawing_index}"
                                    f"-i{item_index}"
                                ),
                                page_number=(
                                    page_number
                                ),
                                start=_point(
                                    item[1]
                                ),
                                end=_point(
                                    item[2]
                                ),
                                width_points=(
                                    width
                                ),
                                source_ref=(
                                    source_ref
                                ),
                            )
                        )

                        count += 1

                    elif (
                        primitive == "re"
                        and len(item) >= 2
                    ):
                        rectangles.append(
                            PdfVectorRectangle(
                                rectangle_id=(
                                    f"p{page_number}"
                                    f"-d{drawing_index}"
                                    f"-i{item_index}"
                                ),
                                page_number=(
                                    page_number
                                ),
                                bbox=_rect(
                                    item[1]
                                ),
                                width_points=(
                                    width
                                ),
                                source_ref=(
                                    source_ref
                                ),
                            )
                        )

                        count += 1

                    else:
                        unresolved += 1

                except (
                    TypeError,
                    ValueError,
                    IndexError,
                ):
                    unresolved += 1

                if (
                    count
                    > self.policy
                    .max_vectors_per_page
                ):
                    raise PdfLimitError(
                        f"page {page_number} "
                        "vector limit exceeded"
                    )

        return (
            tuple(segments),
            tuple(rectangles),
            unresolved,
        )

    @staticmethod
    def _kind(
        *,
        text: str,
        vectors: int,
        images: int,
    ) -> PdfPageKind:
        has_text = bool(
            text.strip()
        )

        if (
            vectors > 0
            and images > 0
        ):
            return PdfPageKind.HYBRID

        if vectors > 0:
            return PdfPageKind.VECTOR

        if images > 0:
            return PdfPageKind.RASTER

        if has_text:
            return PdfPageKind.TEXT_ONLY

        return PdfPageKind.EMPTY

    def ingest(
        self,
        path: str | Path,
        *,
        password: str | None = None,
    ) -> PdfDocumentEvidence:
        self._require_dependency()

        source = (
            Path(path)
            .expanduser()
            .resolve()
        )

        size = self._validate_file(
            source
        )

        fingerprint = (
            self.fingerprint(
                source
            )
        )

        try:
            document = fitz.open(
                str(source)
            )

        except Exception as exc:
            raise PdfIngestError(
                "unable to open PDF"
            ) from exc

        pages: list[
            PdfPageEvidence
        ] = []

        findings: list[
            PdfFinding
        ] = []

        try:
            if getattr(
                document,
                "needs_pass",
                False,
            ):
                if not password:
                    raise PdfSecurityError(
                        "encrypted PDF "
                        "requires password"
                    )

                if not document.authenticate(
                    password
                ):
                    raise PdfSecurityError(
                        "PDF password invalid"
                    )

            page_count = int(
                document.page_count
            )

            if page_count <= 0:
                raise PdfIngestError(
                    "PDF contains no pages"
                )

            if (
                page_count
                > self.policy.max_pages
            ):
                raise PdfLimitError(
                    "PDF page limit exceeded"
                )

            for index in range(
                page_count
            ):
                page = document[
                    index
                ]

                page_number = (
                    index + 1
                )

                source_ref = (
                    f"{source.name}"
                    f"#sha256="
                    f"{fingerprint[:16]}"
                    f"&page={page_number}"
                )

                text, spans = (
                    self._text(
                        page,
                        page_number,
                    )
                )

                (
                    segments,
                    rectangles,
                    unresolved,
                ) = self._vectors(
                    page,
                    page_number,
                    source_ref,
                )

                try:
                    image_count = len(
                        page.get_images(
                            full=True
                        )
                        or ()
                    )

                except Exception:
                    image_count = 0

                page_findings: list[
                    PdfFinding
                ] = []

                kind = self._kind(
                    text=text,
                    vectors=(
                        len(segments)
                        + len(rectangles)
                    ),
                    images=image_count,
                )

                scale_text = (
                    detect_scale_text(
                        text
                    )
                )

                if (
                    kind
                    == PdfPageKind.RASTER
                ):
                    page_findings.append(
                        PdfFinding(
                            code=(
                                "RASTER_ONLY_PAGE"
                            ),
                            severity=(
                                FindingSeverity
                                .BLOCKER
                            ),
                            message=(
                                "Raster-only page "
                                "requires reviewed "
                                "raster processing."
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
                    (
                        segments
                        or rectangles
                    )
                    and scale_text is None
                ):
                    page_findings.append(
                        PdfFinding(
                            code=(
                                "SCALE_NOT_CONFIRMED"
                            ),
                            severity=(
                                FindingSeverity
                                .WARNING
                            ),
                            message=(
                                "Native vectors exist "
                                "but scale is unresolved."
                            ),
                            page_number=(
                                page_number
                            ),
                            source_ref=(
                                source_ref
                            ),
                        )
                    )

                if unresolved:
                    page_findings.append(
                        PdfFinding(
                            code=(
                                "UNSUPPORTED_VECTOR_PRIMITIVES"
                            ),
                            severity=(
                                FindingSeverity
                                .WARNING
                            ),
                            message=(
                                f"{unresolved} vector "
                                "primitive(s) left "
                                "unresolved."
                            ),
                            page_number=(
                                page_number
                            ),
                            source_ref=(
                                source_ref
                            ),
                        )
                    )

                rect = page.rect

                pages.append(
                    PdfPageEvidence(
                        page_number=(
                            page_number
                        ),
                        width_points=(
                            _finite(
                                rect.width
                            )
                        ),
                        height_points=(
                            _finite(
                                rect.height
                            )
                        ),
                        rotation=int(
                            getattr(
                                page,
                                "rotation",
                                0,
                            )
                            or 0
                        ),
                        text=text,
                        text_spans=spans,
                        segments=segments,
                        rectangles=(
                            rectangles
                        ),
                        image_count=(
                            image_count
                        ),
                        page_kind=kind,
                        source_ref=(
                            source_ref
                        ),
                        sheet_hint=(
                            detect_sheet_hint(
                                text
                            )
                        ),
                        scale_text=(
                            scale_text
                        ),
                        findings=tuple(
                            page_findings
                        ),
                    )
                )

        finally:
            document.close()

        return PdfDocumentEvidence(
            document_id=(
                f"pdf_"
                f"{fingerprint[:24]}"
            ),
            file_name=(
                source.name
            ),
            sha256=fingerprint,
            file_size_bytes=size,
            pages=tuple(
                pages
            ),
            findings=tuple(
                findings
            ),
        )
