from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from leadbot_v2.goat.preconstruction.documents.models import (
    Discipline,
    DocumentSet,
    DrawingDimension,
    DrawingReference,
    EngineeringNote,
    RevisionMarker,
    ScaleState,
    SheetRecord,
    SheetScale,
)


SHEET_NUMBER_PATTERNS = (
    re.compile(
        r"\b(?:SHEET\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*)"
        r"([A-Z]{1,3}[-.]?\d{1,3}(?:\.\d+)?)\b",
        re.I,
    ),
    re.compile(
        r"\b([GCSLAMPETF]{1,3}[-.]?\d{1,3}(?:\.\d+)?)\b",
        re.I,
    ),
)


DISCIPLINE_PREFIXES = {
    "G": Discipline.GENERAL,
    "C": Discipline.CIVIL,
    "L": Discipline.LANDSCAPE,
    "A": Discipline.ARCHITECTURAL,
    "S": Discipline.STRUCTURAL,
    "M": Discipline.MECHANICAL,
    "E": Discipline.ELECTRICAL,
    "P": Discipline.PLUMBING,
    "FP": Discipline.FIRE_PROTECTION,
    "FA": Discipline.FIRE_PROTECTION,
    "T": Discipline.TECHNOLOGY,
}


DISCIPLINE_TEXT = {
    Discipline.STRUCTURAL: (
        "structural",
        "foundation plan",
        "framing plan",
        "reinforcing",
        "rebar",
        "grade beam",
    ),
    Discipline.ARCHITECTURAL: (
        "architectural",
        "floor plan",
        "reflected ceiling",
        "elevation",
        "finish plan",
    ),
    Discipline.CIVIL: (
        "civil",
        "grading",
        "utility plan",
        "erosion control",
        "site plan",
    ),
    Discipline.ELECTRICAL: (
        "electrical",
        "lighting plan",
        "power plan",
        "one-line",
        "one line",
        "panel schedule",
    ),
    Discipline.PLUMBING: (
        "plumbing",
        "sanitary",
        "domestic water",
        "vent plan",
        "plumbing plan",
    ),
    Discipline.MECHANICAL: (
        "mechanical",
        "hvac",
        "ductwork",
        "mechanical plan",
    ),
    Discipline.FIRE_PROTECTION: (
        "fire protection",
        "sprinkler",
        "fire alarm",
    ),
}


ARCH_SCALE = re.compile(
    r'(?P<paper>\d+(?:/\d+)?)\s*"\s*=\s*'
    r"(?P<feet>\d+)\s*'\s*-\s*(?P<inches>\d+)\s*\"",
    re.I,
)

ENGINEERING_SCALE = re.compile(
    r'(?<![\d./])(?P<paper>\d+(?:\.\d+)?)\s*"\s*=\s*'
    r"(?P<feet>\d+(?:\.\d+)?)\s*'",
    re.I,
)

NTS = re.compile(
    r"\b(?:NTS|NOT\s+TO\s+SCALE)\b",
    re.I,
)

DIMENSION_FT_IN = re.compile(
    r"\b(?P<feet>\d{1,4})\s*'\s*-\s*"
    r'(?P<inches>\d{1,2}(?:\s+\d+/\d+)?)\s*"'
)

DIMENSION_FEET = re.compile(
    r"\b(?P<feet>\d{1,4}(?:\.\d+)?)\s*'"
)

DETAIL_REFERENCE = re.compile(
    r"\b(?P<detail>\d{1,3})\s*/\s*"
    r"(?P<sheet>[A-Z]{1,3}[-.]?\d{1,3}(?:\.\d+)?)\b",
    re.I,
)

REVISION = re.compile(
    r"\b(?:REV(?:ISION)?\.?\s*)"
    r"(?P<id>[A-Z0-9]+)"
    r"(?:\s*[-:]\s*(?P<description>[^\n]{2,100}))?",
    re.I,
)


NOTE_RULES = (
    (
        "concrete",
        re.compile(
            r".*\b(?:CONCRETE|PSI|SLAB|FOOTING|"
            r"GRADE BEAM|CURING|ADMIXTURE)\b.*",
            re.I,
        ),
    ),
    (
        "reinforcing",
        re.compile(
            r".*\b(?:REBAR|REINFORC|#\d+\s*@|"
            r"O\.?C\.?|DOWEL|LAP SPLICE)\b.*",
            re.I,
        ),
    ),
    (
        "electrical",
        re.compile(
            r".*\b(?:AMP|AMPS|VOLT|PANEL|FEEDER|"
            r"CONDUIT|GROUNDING|SWITCHGEAR)\b.*",
            re.I,
        ),
    ),
    (
        "plumbing",
        re.compile(
            r".*\b(?:SANITARY|DOMESTIC WATER|VENT|"
            r"STORM|GAS|CLEANOUT|FIXTURE)\b.*",
            re.I,
        ),
    ),
    (
        "earthwork",
        re.compile(
            r".*\b(?:EXCAVAT|CUT|FILL|COMPACTION|"
            r"GRADING|SUBGRADE|TRENCH)\b.*",
            re.I,
        ),
    ),
)


def _fraction(value: str) -> float:
    value = value.strip()

    if "/" in value:
        numerator, denominator = value.split(
            "/",
            1,
        )
        return float(numerator) / float(denominator)

    return float(value)


def _mixed_inches(value: str) -> float:
    value = value.strip()

    if " " in value:
        whole, fraction = value.split(
            " ",
            1,
        )
        return float(whole) + _fraction(fraction)

    if "/" in value:
        return _fraction(value)

    return float(value)


@dataclass(frozen=True)
class RawPage:
    page_number: int
    text: str
    source_ref: str | None = None


class ConstructionDocumentIntelligence:

    def extract_sheet_number(
        self,
        text: str,
    ) -> str:
        for pattern in SHEET_NUMBER_PATTERNS:
            match = pattern.search(text)

            if match:
                return (
                    match.group(1)
                    .upper()
                    .replace(".", ".")
                )

        return "UNKNOWN"

    def detect_discipline(
        self,
        *,
        sheet_number: str,
        text: str,
    ) -> Discipline:
        normalized = (
            sheet_number
            .upper()
            .replace("-", "")
            .replace(".", "")
        )

        for prefix in (
            "FP",
            "FA",
            "G",
            "C",
            "L",
            "A",
            "S",
            "M",
            "E",
            "P",
            "T",
        ):
            if normalized.startswith(prefix):
                return DISCIPLINE_PREFIXES[
                    prefix
                ]

        lowered = text.lower()

        scored: list[
            tuple[int, Discipline]
        ] = []

        for discipline, terms in (
            DISCIPLINE_TEXT.items()
        ):
            score = sum(
                1
                for term in terms
                if term in lowered
            )

            if score:
                scored.append(
                    (score, discipline)
                )

        if not scored:
            return Discipline.UNKNOWN

        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return scored[0][1]

    def extract_title(
        self,
        text: str,
        discipline: Discipline,
    ) -> str:
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        candidates = []

        keywords = (
            "PLAN",
            "SCHEDULE",
            "DETAIL",
            "ELEVATION",
            "SECTION",
            "NOTES",
            "DIAGRAM",
            "RISER",
            "ONE-LINE",
            "ONE LINE",
        )

        for line in lines:
            upper = line.upper()

            if any(
                keyword in upper
                for keyword in keywords
            ):
                if len(line) <= 120:
                    candidates.append(line)

        if candidates:
            return candidates[0]

        return discipline.value.replace(
            "_",
            " ",
        ).title()

    def extract_scales(
        self,
        text: str,
    ) -> tuple[SheetScale, ...]:
        results: list[SheetScale] = []

        for match in ARCH_SCALE.finditer(
            text
        ):
            paper = _fraction(
                match.group("paper")
            )

            feet = float(
                match.group("feet")
            )

            inches = float(
                match.group("inches")
            )

            model_inches = (
                feet * 12.0 + inches
            )

            results.append(
                SheetScale(
                    raw=match.group(0),
                    state=ScaleState.DECLARED,
                    paper_units=paper,
                    model_units=model_inches,
                    model_unit_name="inch",
                    confidence=0.98,
                )
            )

        for match in ENGINEERING_SCALE.finditer(
            text
        ):
            raw = match.group(0)

            if any(
                raw == item.raw
                for item in results
            ):
                continue

            results.append(
                SheetScale(
                    raw=raw,
                    state=ScaleState.DECLARED,
                    paper_units=float(
                        match.group("paper")
                    ),
                    model_units=float(
                        match.group("feet")
                    ),
                    model_unit_name="foot",
                    confidence=0.97,
                )
            )

        if NTS.search(text):
            results.append(
                SheetScale(
                    raw="NTS",
                    state=ScaleState.NTS,
                    confidence=1.0,
                )
            )

        declared = [
            item
            for item in results
            if item.state
            == ScaleState.DECLARED
        ]

        if len(
            {
                (
                    item.paper_units,
                    item.model_units,
                    item.model_unit_name,
                )
                for item in declared
            }
        ) > 1:
            results.append(
                SheetScale(
                    raw="MULTIPLE DECLARED SCALES",
                    state=ScaleState.CONFLICT,
                    confidence=0.95,
                )
            )

        return tuple(results)

    def extract_dimensions(
        self,
        text: str,
    ) -> tuple[DrawingDimension, ...]:
        results: list[
            DrawingDimension
        ] = []

        occupied: list[
            tuple[int, int]
        ] = []

        for match in DIMENSION_FT_IN.finditer(
            text
        ):
            results.append(
                DrawingDimension(
                    raw=match.group(0),
                    feet=float(
                        match.group("feet")
                    ),
                    inches=_mixed_inches(
                        match.group("inches")
                    ),
                    confidence=0.98,
                )
            )

            occupied.append(
                match.span()
            )

        for match in DIMENSION_FEET.finditer(
            text
        ):
            start, end = match.span()

            if any(
                start >= a
                and end <= b
                for a, b in occupied
            ):
                continue

            results.append(
                DrawingDimension(
                    raw=match.group(0),
                    feet=float(
                        match.group("feet")
                    ),
                    inches=0.0,
                    confidence=0.90,
                )
            )

        return tuple(results)

    def extract_references(
        self,
        text: str,
    ) -> tuple[DrawingReference, ...]:
        return tuple(
            DrawingReference(
                detail_number=(
                    match.group("detail")
                ),
                sheet_number=(
                    match.group("sheet")
                    .upper()
                ),
                raw=match.group(0),
                confidence=0.98,
            )
            for match
            in DETAIL_REFERENCE.finditer(
                text
            )
        )

    def extract_notes(
        self,
        text: str,
    ) -> tuple[EngineeringNote, ...]:
        results: list[
            EngineeringNote
        ] = []

        seen: set[
            tuple[str, str]
        ] = set()

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            for category, pattern in NOTE_RULES:
                if pattern.fullmatch(line):
                    key = (
                        category,
                        line,
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    results.append(
                        EngineeringNote(
                            text=line,
                            category=category,
                            confidence=0.90,
                        )
                    )

        return tuple(results)

    def extract_revisions(
        self,
        text: str,
    ) -> tuple[RevisionMarker, ...]:
        results = []

        for match in REVISION.finditer(text):
            results.append(
                RevisionMarker(
                    identifier=(
                        match.group("id")
                    ),
                    description=(
                        match.group(
                            "description"
                        )
                        or ""
                    ).strip(),
                    raw=match.group(0),
                    confidence=0.90,
                )
            )

        return tuple(results)

    def analyze_page(
        self,
        page: RawPage,
    ) -> SheetRecord:
        sheet_number = (
            self.extract_sheet_number(
                page.text
            )
        )

        discipline = (
            self.detect_discipline(
                sheet_number=sheet_number,
                text=page.text,
            )
        )

        scales = self.extract_scales(
            page.text
        )

        references = (
            self.extract_references(
                page.text
            )
        )

        dimensions = (
            self.extract_dimensions(
                page.text
            )
        )

        notes = self.extract_notes(
            page.text
        )

        revisions = (
            self.extract_revisions(
                page.text
            )
        )

        evidence_count = sum(
            (
                sheet_number != "UNKNOWN",
                discipline
                != Discipline.UNKNOWN,
                bool(scales),
                bool(dimensions),
                bool(notes),
            )
        )

        confidence = min(
            0.99,
            0.45
            + evidence_count * 0.10,
        )

        return SheetRecord(
            page_number=page.page_number,
            sheet_number=sheet_number,
            title=self.extract_title(
                page.text,
                discipline,
            ),
            discipline=discipline,
            text=page.text,
            scales=scales,
            dimensions=dimensions,
            references=references,
            notes=notes,
            revisions=revisions,
            confidence=confidence,
            source_ref=page.source_ref,
        )

    def analyze_document(
        self,
        *,
        source_name: str,
        pages: tuple[RawPage, ...],
        document_id: str | None = None,
    ) -> DocumentSet:
        if not pages:
            raise ValueError(
                "document must contain pages"
            )

        ordered = sorted(
            pages,
            key=lambda page:
                page.page_number,
        )

        return DocumentSet(
            document_id=(
                document_id
                or f"doc_{uuid4().hex}"
            ),
            source_name=source_name,
            sheets=tuple(
                self.analyze_page(page)
                for page in ordered
            ),
        )
