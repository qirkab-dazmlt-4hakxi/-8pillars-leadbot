from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.preconstruction.documents.models import (
    DocumentSet,
    ScaleState,
)


class RFISeverity(str, Enum):
    INFORMATION = "information"
    REVIEW = "review"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RFICandidate:
    rfi_id: str
    severity: RFISeverity
    discipline: str
    sheet_numbers: tuple[str, ...]
    title: str
    conflict: str
    request: str
    estimate_treatment: str
    confidence: float
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "RFI confidence must be 0-1"
            )

        if not self.evidence_refs:
            raise ValueError(
                "RFI candidate requires evidence"
            )


class PreconstructionRFIEngine:

    def analyze(
        self,
        document: DocumentSet,
    ) -> tuple[RFICandidate, ...]:
        candidates: list[
            RFICandidate
        ] = []

        known_sheets = {
            sheet.sheet_number.upper()
            for sheet in document.sheets
            if sheet.sheet_number
            != "UNKNOWN"
        }

        for sheet in document.sheets:
            source = (
                sheet.source_ref
                or (
                    f"{document.source_name}"
                    f"#page={sheet.page_number}"
                )
            )

            if sheet.sheet_number == "UNKNOWN":
                candidates.append(
                    RFICandidate(
                        rfi_id=(
                            f"rfi_{uuid4().hex}"
                        ),
                        severity=(
                            RFISeverity.REVIEW
                        ),
                        discipline=(
                            sheet.discipline.value
                        ),
                        sheet_numbers=(
                            f"PAGE-{sheet.page_number}",
                        ),
                        title=(
                            "Unidentified drawing sheet"
                        ),
                        conflict=(
                            "GOAT could not establish "
                            "a reliable sheet number."
                        ),
                        request=(
                            "Confirm the drawing sheet "
                            "number and current revision."
                        ),
                        estimate_treatment=(
                            "Do not rely on sheet-specific "
                            "quantities until identified."
                        ),
                        confidence=0.95,
                        evidence_refs=(source,),
                    )
                )

            states = {
                scale.state
                for scale in sheet.scales
            }

            if ScaleState.CONFLICT in states:
                candidates.append(
                    RFICandidate(
                        rfi_id=(
                            f"rfi_{uuid4().hex}"
                        ),
                        severity=RFISeverity.HIGH,
                        discipline=(
                            sheet.discipline.value
                        ),
                        sheet_numbers=(
                            sheet.sheet_number,
                        ),
                        title=(
                            "Conflicting drawing scales"
                        ),
                        conflict=(
                            "Multiple incompatible scales "
                            "were detected on the sheet."
                        ),
                        request=(
                            "Confirm the applicable scale "
                            "for each plan/detail region."
                        ),
                        estimate_treatment=(
                            "Require region-specific "
                            "calibration before automated "
                            "measurement."
                        ),
                        confidence=0.95,
                        evidence_refs=(source,),
                    )
                )

            if (
                ScaleState.NTS in states
                and not any(
                    scale.state
                    == ScaleState.DECLARED
                    for scale in sheet.scales
                )
            ):
                candidates.append(
                    RFICandidate(
                        rfi_id=(
                            f"rfi_{uuid4().hex}"
                        ),
                        severity=(
                            RFISeverity.REVIEW
                        ),
                        discipline=(
                            sheet.discipline.value
                        ),
                        sheet_numbers=(
                            sheet.sheet_number,
                        ),
                        title=(
                            "Not-to-scale drawing"
                        ),
                        conflict=(
                            "The sheet is marked NTS and "
                            "cannot be safely measured "
                            "using printed geometry."
                        ),
                        request=(
                            "Provide governing dimensions "
                            "or a measurable reference."
                        ),
                        estimate_treatment=(
                            "Use written dimensions only; "
                            "do not infer scaled quantity."
                        ),
                        confidence=1.0,
                        evidence_refs=(source,),
                    )
                )

            for reference in sheet.references:
                if (
                    reference.sheet_number
                    not in known_sheets
                ):
                    candidates.append(
                        RFICandidate(
                            rfi_id=(
                                f"rfi_{uuid4().hex}"
                            ),
                            severity=(
                                RFISeverity.HIGH
                            ),
                            discipline=(
                                sheet.discipline.value
                            ),
                            sheet_numbers=(
                                sheet.sheet_number,
                                reference.sheet_number,
                            ),
                            title=(
                                "Missing referenced detail"
                            ),
                            conflict=(
                                f"{sheet.sheet_number} "
                                f"references detail "
                                f"{reference.detail_number}/"
                                f"{reference.sheet_number}, "
                                "but that referenced sheet "
                                "is not in the plan set."
                            ),
                            request=(
                                "Provide the missing "
                                "referenced sheet/detail."
                            ),
                            estimate_treatment=(
                                "Carry an allowance or "
                                "exclude affected scope "
                                "pending clarification."
                            ),
                            confidence=0.98,
                            evidence_refs=(source,),
                        )
                    )

        return tuple(candidates)
