from __future__ import annotations

import re

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.preconstruction.documents.models import (
    DocumentSet,
    DrawingReference,
    SheetRecord,
)
from leadbot_v2.goat.preconstruction.rfi.engine import (
    RFICandidate,
    RFISeverity,
)


class DetailResolutionError(RuntimeError):
    pass


class DetailResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    SHEET_MISSING = "sheet_missing"
    DETAIL_MISSING = "detail_missing"


@dataclass(frozen=True)
class DetailResolution:
    status: DetailResolutionStatus
    source_sheet: str
    source_page: int
    target_sheet: str
    detail_number: str
    source_ref: str
    target_ref: str | None
    reason: str
    confidence: float

    @property
    def resolved(self) -> bool:
        return (
            self.status
            == DetailResolutionStatus.RESOLVED
        )


class DrawingDetailResolver:
    """
    Resolves drawing references such as:

        4/S5.2

    against the actual plan set.

    GOAT does not silently assume that an existing sheet
    necessarily contains the referenced detail.
    """

    @staticmethod
    def _normalize_sheet(
        value: str,
    ) -> str:
        return (
            value
            .upper()
            .strip()
            .replace(" ", "")
        )

    @classmethod
    def build_sheet_index(
        cls,
        document: DocumentSet,
    ) -> dict[str, SheetRecord]:
        index: dict[
            str,
            SheetRecord,
        ] = {}

        for sheet in document.sheets:
            if sheet.sheet_number == "UNKNOWN":
                continue

            key = cls._normalize_sheet(
                sheet.sheet_number
            )

            if key in index:
                raise DetailResolutionError(
                    f"duplicate sheet number: "
                    f"{sheet.sheet_number}"
                )

            index[key] = sheet

        return index

    @staticmethod
    def _contains_detail(
        *,
        text: str,
        detail_number: str,
    ) -> bool:
        escaped = re.escape(
            detail_number.strip()
        )

        patterns = (
            re.compile(
                rf"\bDETAIL\s*{escaped}\b",
                re.I,
            ),
            re.compile(
                rf"\bDET\.?\s*{escaped}\b",
                re.I,
            ),
            re.compile(
                rf"(?:^|\n)\s*{escaped}\s*"
                r"(?:\n|DETAIL|SECTION|$)",
                re.I,
            ),
        )

        return any(
            pattern.search(text)
            for pattern in patterns
        )

    @classmethod
    def resolve_reference(
        cls,
        *,
        document: DocumentSet,
        source_sheet: SheetRecord,
        reference: DrawingReference,
    ) -> DetailResolution:
        index = cls.build_sheet_index(
            document
        )

        target_key = cls._normalize_sheet(
            reference.sheet_number
        )

        source_ref = (
            source_sheet.source_ref
            or (
                f"{document.source_name}"
                f"#page={source_sheet.page_number}"
            )
        )

        target = index.get(
            target_key
        )

        if target is None:
            return DetailResolution(
                status=(
                    DetailResolutionStatus
                    .SHEET_MISSING
                ),
                source_sheet=(
                    source_sheet.sheet_number
                ),
                source_page=(
                    source_sheet.page_number
                ),
                target_sheet=(
                    reference.sheet_number
                ),
                detail_number=(
                    reference.detail_number
                ),
                source_ref=source_ref,
                target_ref=None,
                reason=(
                    "Referenced target sheet is "
                    "not present in the plan set."
                ),
                confidence=0.99,
            )

        target_ref = (
            target.source_ref
            or (
                f"{document.source_name}"
                f"#page={target.page_number}"
            )
        )

        if not cls._contains_detail(
            text=target.text,
            detail_number=(
                reference.detail_number
            ),
        ):
            return DetailResolution(
                status=(
                    DetailResolutionStatus
                    .DETAIL_MISSING
                ),
                source_sheet=(
                    source_sheet.sheet_number
                ),
                source_page=(
                    source_sheet.page_number
                ),
                target_sheet=(
                    target.sheet_number
                ),
                detail_number=(
                    reference.detail_number
                ),
                source_ref=source_ref,
                target_ref=target_ref,
                reason=(
                    "Referenced sheet exists, but "
                    "the referenced detail could not "
                    "be verified on that sheet."
                ),
                confidence=0.95,
            )

        return DetailResolution(
            status=(
                DetailResolutionStatus.RESOLVED
            ),
            source_sheet=(
                source_sheet.sheet_number
            ),
            source_page=(
                source_sheet.page_number
            ),
            target_sheet=(
                target.sheet_number
            ),
            detail_number=(
                reference.detail_number
            ),
            source_ref=source_ref,
            target_ref=target_ref,
            reason=(
                "Referenced sheet and detail "
                "were both verified."
            ),
            confidence=min(
                reference.confidence,
                0.99,
            ),
        )

    @classmethod
    def resolve_all(
        cls,
        document: DocumentSet,
    ) -> tuple[
        DetailResolution,
        ...
    ]:
        results: list[
            DetailResolution
        ] = []

        for sheet in document.sheets:
            for reference in sheet.references:
                results.append(
                    cls.resolve_reference(
                        document=document,
                        source_sheet=sheet,
                        reference=reference,
                    )
                )

        return tuple(results)

    @staticmethod
    def unresolved_to_rfis(
        resolutions: tuple[
            DetailResolution,
            ...
        ],
    ) -> tuple[
        RFICandidate,
        ...
    ]:
        rfis: list[
            RFICandidate
        ] = []

        for resolution in resolutions:
            if resolution.resolved:
                continue

            if (
                resolution.status
                == DetailResolutionStatus
                .SHEET_MISSING
            ):
                title = (
                    "Missing referenced drawing sheet"
                )
                severity = RFISeverity.HIGH

            else:
                title = (
                    "Referenced detail not verified"
                )
                severity = RFISeverity.REVIEW

            evidence = [
                resolution.source_ref,
            ]

            if resolution.target_ref:
                evidence.append(
                    resolution.target_ref
                )

            rfis.append(
                RFICandidate(
                    rfi_id=(
                        f"rfi_{uuid4().hex}"
                    ),
                    severity=severity,
                    discipline="coordination",
                    sheet_numbers=tuple(
                        dict.fromkeys(
                            (
                                resolution.source_sheet,
                                resolution.target_sheet,
                            )
                        )
                    ),
                    title=title,
                    conflict=(
                        f"Reference "
                        f"{resolution.detail_number}/"
                        f"{resolution.target_sheet}: "
                        f"{resolution.reason}"
                    ),
                    request=(
                        "Confirm and provide the "
                        "governing drawing/detail."
                    ),
                    estimate_treatment=(
                        "Do not silently assume the "
                        "missing detail requirements. "
                        "Carry an explicit allowance, "
                        "qualification or exclusion "
                        "until resolved."
                    ),
                    confidence=(
                        resolution.confidence
                    ),
                    evidence_refs=tuple(
                        evidence
                    ),
                )
            )

        return tuple(rfis)
