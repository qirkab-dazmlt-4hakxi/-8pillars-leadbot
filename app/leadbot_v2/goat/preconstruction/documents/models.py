from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Discipline(str, Enum):
    GENERAL = "general"
    CIVIL = "civil"
    LANDSCAPE = "landscape"
    ARCHITECTURAL = "architectural"
    STRUCTURAL = "structural"
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    FIRE_PROTECTION = "fire_protection"
    TECHNOLOGY = "technology"
    UNKNOWN = "unknown"


class ScaleState(str, Enum):
    CALIBRATED = "calibrated"
    DECLARED = "declared"
    NTS = "not_to_scale"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SheetScale:
    raw: str
    state: ScaleState
    paper_units: float | None = None
    model_units: float | None = None
    model_unit_name: str | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("scale confidence must be 0-1")


@dataclass(frozen=True)
class DrawingReference:
    detail_number: str
    sheet_number: str
    raw: str
    confidence: float


@dataclass(frozen=True)
class DrawingDimension:
    raw: str
    feet: float | None
    inches: float | None
    confidence: float


@dataclass(frozen=True)
class EngineeringNote:
    text: str
    category: str
    confidence: float


@dataclass(frozen=True)
class RevisionMarker:
    identifier: str
    description: str
    raw: str
    confidence: float


@dataclass(frozen=True)
class SheetRecord:
    page_number: int
    sheet_number: str
    title: str
    discipline: Discipline
    text: str

    scales: tuple[SheetScale, ...] = ()
    dimensions: tuple[DrawingDimension, ...] = ()
    references: tuple[DrawingReference, ...] = ()
    notes: tuple[EngineeringNote, ...] = ()
    revisions: tuple[RevisionMarker, ...] = ()

    confidence: float = 0.0
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must be >= 1")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("sheet confidence must be 0-1")


@dataclass(frozen=True)
class DocumentSet:
    document_id: str
    source_name: str
    sheets: tuple[SheetRecord, ...]

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)

    def by_number(
        self,
        sheet_number: str,
    ) -> SheetRecord | None:
        normalized = sheet_number.upper().strip()

        for sheet in self.sheets:
            if sheet.sheet_number.upper() == normalized:
                return sheet

        return None
