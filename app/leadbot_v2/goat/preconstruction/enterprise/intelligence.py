from __future__ import annotations

import hashlib
import math
import re
import uuid

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum, IntEnum
from typing import Iterable, Sequence


# ============================================================
# ERRORS
# ============================================================


class PreconstructionIntelligenceError(RuntimeError):
    pass


class ScheduleCycleError(
    PreconstructionIntelligenceError
):
    pass


class MissingEvidenceError(
    PreconstructionIntelligenceError
):
    pass


class InvalidScheduleError(
    PreconstructionIntelligenceError
):
    pass


# ============================================================
# ENUMS
# ============================================================


class EvidenceKind(str, Enum):
    SPECIFICATION = "specification"
    DRAWING = "drawing"
    ADDENDUM = "addendum"
    RFI = "rfi"
    CONTRACT = "contract"
    ESTIMATE = "estimate"
    QUOTE = "quote"
    SCHEDULE = "schedule"
    SUBMITTAL = "submittal"
    OTHER = "other"


class RequirementCategory(str, Enum):
    SUBMITTAL = "submittal"
    PRODUCT = "product"
    EXECUTION = "execution"
    TESTING = "testing"
    QUALITY = "quality"
    WARRANTY = "warranty"
    MOCKUP = "mockup"
    CLOSEOUT = "closeout"
    DELIVERY = "delivery"
    COORDINATION = "coordination"
    SAFETY_REVIEW = "safety_review"
    GENERAL = "general"


class ContractRiskCategory(str, Enum):
    PAYMENT = "payment"
    RETAINAGE = "retainage"
    LIQUIDATED_DAMAGES = "liquidated_damages"
    SCHEDULE = "schedule"
    NOTICE = "notice"
    CHANGE_ORDER = "change_order"
    INDEMNITY = "indemnity"
    INSURANCE = "insurance"
    WARRANTY = "warranty"
    DELAY = "delay"
    TERMINATION = "termination"
    DISPUTE = "dispute"
    FLOW_DOWN = "flow_down"
    UNKNOWN = "unknown"


class RiskSeverity(IntEnum):
    INFO = 10
    REVIEW = 20
    HIGH = 30
    BLOCKER = 40


class DependencyType(str, Enum):
    FS = "finish_to_start"
    SS = "start_to_start"
    FF = "finish_to_finish"
    SF = "start_to_finish"


class ProcurementRisk(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    LONG_LEAD = "long_lead"
    CRITICAL = "critical"


class ComplianceState(str, Enum):
    SATISFIED = "satisfied"
    REVIEW_REQUIRED = "review_required"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


class RFISeverity(str, Enum):
    REVIEW = "review"
    BLOCKING = "blocking"


# ============================================================
# GENERIC EVIDENCE
# ============================================================


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    kind: EvidenceKind
    page: int | None = None
    section: str | None = None
    sheet: str | None = None
    excerpt: str | None = None

    def label(self) -> str:
        parts = [
            self.kind.value,
            self.source_id,
        ]

        if self.sheet:
            parts.append(
                f"sheet={self.sheet}"
            )

        if self.section:
            parts.append(
                f"section={self.section}"
            )

        if self.page is not None:
            parts.append(
                f"page={self.page}"
            )

        return "|".join(
            parts
        )


def _id(prefix: str) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _normalized_text(
    value: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()


def _tokenize(
    value: str,
) -> tuple[str, ...]:
    return tuple(
        token
        for token
        in re.findall(
            r"[A-Za-z0-9][A-Za-z0-9./'-]*",
            value.lower(),
        )
        if token
    )


def _hash_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# SPECIFICATION INTELLIGENCE
# ============================================================


@dataclass(frozen=True)
class SpecificationRequirement:
    requirement_id: str

    section: str | None
    category: RequirementCategory

    text: str

    mandatory: bool

    confidence: float

    source: SourceReference

    keywords: tuple[str, ...] = ()

    numeric_values: tuple[
        str,
        ...
    ] = ()


@dataclass(frozen=True)
class SpecificationAnalysis:
    source_id: str

    requirements: tuple[
        SpecificationRequirement,
        ...
    ]

    sections_seen: tuple[
        str,
        ...
    ]

    mandatory_count: int

    testing_count: int

    submittal_count: int

    warranty_count: int

    mockup_count: int


class SpecificationIntelligence:
    SECTION_PATTERN = re.compile(
        r"\b(?:SECTION\s+)?"
        r"(\d{2}\s?\d{2}\s?\d{2})\b",
        re.IGNORECASE,
    )

    MANDATORY_PATTERNS = (
        re.compile(
            r"\bshall\b",
            re.I,
        ),
        re.compile(
            r"\bmust\b",
            re.I,
        ),
        re.compile(
            r"\brequired\b",
            re.I,
        ),
        re.compile(
            r"\bprovide\b",
            re.I,
        ),
        re.compile(
            r"\bsubmit\b",
            re.I,
        ),
        re.compile(
            r"\binstall\b",
            re.I,
        ),
    )

    CATEGORY_PATTERNS = (
        (
            RequirementCategory.SUBMITTAL,
            re.compile(
                r"\b"
                r"(submittal|shop drawing|"
                r"product data|sample|"
                r"certificate)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.TESTING,
            re.compile(
                r"\b"
                r"(test|testing|inspection|"
                r"laboratory|field test)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.QUALITY,
            re.compile(
                r"\b"
                r"(quality assurance|qa/qc|"
                r"qualification|certified|"
                r"installer qualification)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.WARRANTY,
            re.compile(
                r"\b"
                r"(warranty|guarantee)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.MOCKUP,
            re.compile(
                r"\b"
                r"(mock[- ]?up|sample panel)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.CLOSEOUT,
            re.compile(
                r"\b"
                r"(closeout|record drawing|"
                r"as[- ]built|o&m|"
                r"operation and maintenance)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.DELIVERY,
            re.compile(
                r"\b"
                r"(delivery|storage|handling|"
                r"lead time)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.COORDINATION,
            re.compile(
                r"\b"
                r"(coordinate|coordination|"
                r"interface|conflict)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.PRODUCT,
            re.compile(
                r"\b"
                r"(manufacturer|product|material|"
                r"approved equal)"
                r"\b",
                re.I,
            ),
        ),
        (
            RequirementCategory.EXECUTION,
            re.compile(
                r"\b"
                r"(install|placement|execution|"
                r"preparation|application)"
                r"\b",
                re.I,
            ),
        ),
    )

    NUMERIC_PATTERN = re.compile(
        r"""
        (?:
            \$?\d[\d,]*(?:\.\d+)?
            \s*
            (?:
                psi|ksi|mpa|inch|inches|in\.|
                ft|feet|sf|sq\.?\s*ft|
                cy|cu\.?\s*yd|
                lb|lbs|pound|pounds|
                day|days|week|weeks|
                year|years|percent|%
            )?
        )
        """,
        re.I | re.X,
    )

    @classmethod
    def categorize(
        cls,
        text: str,
    ) -> RequirementCategory:
        normalized = re.sub(
            r"\s+",
            " ",
            (text or "").lower(),
        ).strip()

        # ----------------------------------------------------
        # HIGH-SPECIFICITY SEMANTIC RULES
        # ----------------------------------------------------
        # These MUST execute before broad CATEGORY_PATTERNS.
        #
        # Example:
        #   "sample panel mock-up"
        #
        # contains the generic word "sample", but the governing
        # construction meaning is MOCKUP, not SUBMITTAL.
        # ----------------------------------------------------

        if re.search(
            r"\b(mock[- ]?up|mockup|sample panel)\b",
            normalized,
            re.I,
        ):
            return (
                RequirementCategory
                .MOCKUP
            )

        if re.search(
            r"\b(warranty|guarantee)\b",
            normalized,
            re.I,
        ):
            return (
                RequirementCategory
                .WARRANTY
            )

        if re.search(
            r"\b("
            r"field test|field testing|"
            r"testing laboratory|"
            r"laboratory testing"
            r")\b",
            normalized,
            re.I,
        ):
            return (
                RequirementCategory
                .TESTING
            )

        if re.search(
            r"\b("
            r"record drawing|"
            r"record drawings|"
            r"as[- ]built|"
            r"as[- ]builts|"
            r"operation and maintenance|"
            r"o&m"
            r")\b",
            normalized,
            re.I,
        ):
            return (
                RequirementCategory
                .CLOSEOUT
            )

        # ----------------------------------------------------
        # EXISTING GENERAL CLASSIFIER
        # ----------------------------------------------------

        for (
            category,
            pattern,
        ) in cls.CATEGORY_PATTERNS:
            if pattern.search(
                text
            ):
                return category

        return (
            RequirementCategory
            .GENERAL
        )

    @classmethod
    def analyze(
        cls,
        *,
        source_id: str,
        text: str,
        page: int | None = None,
        default_section: str | None = None,
    ) -> SpecificationAnalysis:
        clean = _normalized_text(
            text
        )

        if not clean:
            raise MissingEvidenceError(
                "specification text is empty"
            )

        sentences = tuple(
            part.strip()
            for part
            in re.split(
                r"(?<=[.;:])\s+"
                r"|(?<=[.!?])\s+",
                clean,
            )
            if part.strip()
        )

        current_section = (
            default_section
        )

        requirements = []

        sections = []

        for sentence in sentences:
            section_match = (
                cls.SECTION_PATTERN
                .search(
                    sentence
                )
            )

            if section_match:
                raw = (
                    section_match
                    .group(1)
                )

                current_section = re.sub(
                    r"\s+",
                    " ",
                    raw,
                )

                sections.append(
                    current_section
                )

            mandatory_hits = sum(
                1
                for pattern
                in cls.MANDATORY_PATTERNS
                if pattern.search(
                    sentence
                )
            )

            category = cls.categorize(
                sentence
            )

            if (
                mandatory_hits == 0
                and category
                == RequirementCategory
                .GENERAL
            ):
                continue

            mandatory = (
                mandatory_hits > 0
            )

            keyword_tokens = tuple(
                sorted(
                    {
                        token
                        for token
                        in _tokenize(
                            sentence
                        )
                        if len(token) >= 4
                    }
                )
            )

            numbers = tuple(
                match.group(0).strip()
                for match
                in cls.NUMERIC_PATTERN
                .finditer(
                    sentence
                )
            )

            confidence = min(
                0.99,
                (
                    0.55
                    + 0.09
                    * mandatory_hits
                    + (
                        0.12
                        if category
                        != RequirementCategory
                        .GENERAL
                        else 0.0
                    )
                    + (
                        0.08
                        if current_section
                        else 0.0
                    )
                ),
            )

            requirements.append(
                SpecificationRequirement(
                    requirement_id=(
                        "spec_"
                        + _hash_text(
                            (
                                source_id
                                + "|"
                                + str(
                                    current_section
                                )
                                + "|"
                                + sentence
                            )
                        )[:20]
                    ),
                    section=(
                        current_section
                    ),
                    category=category,
                    text=sentence,
                    mandatory=mandatory,
                    confidence=confidence,
                    source=(
                        SourceReference(
                            source_id=(
                                source_id
                            ),
                            kind=(
                                EvidenceKind
                                .SPECIFICATION
                            ),
                            page=page,
                            section=(
                                current_section
                            ),
                            excerpt=sentence,
                        )
                    ),
                    keywords=(
                        keyword_tokens
                    ),
                    numeric_values=(
                        numbers
                    ),
                )
            )

        return SpecificationAnalysis(
            source_id=source_id,
            requirements=tuple(
                requirements
            ),
            sections_seen=tuple(
                dict.fromkeys(
                    sections
                )
            ),
            mandatory_count=sum(
                1
                for item
                in requirements
                if item.mandatory
            ),
            testing_count=sum(
                1
                for item
                in requirements
                if item.category
                == RequirementCategory
                .TESTING
            ),
            submittal_count=sum(
                1
                for item
                in requirements
                if item.category
                == RequirementCategory
                .SUBMITTAL
            ),
            warranty_count=sum(
                1
                for item
                in requirements
                if item.category
                == RequirementCategory
                .WARRANTY
            ),
            mockup_count=sum(
                1
                for item
                in requirements
                if item.category
                == RequirementCategory
                .MOCKUP
            ),
        )


# ============================================================
# CONTRACT / DIVISION 00-01 RISK
# ============================================================


@dataclass(frozen=True)
class ContractRiskFinding:
    finding_id: str

    category: ContractRiskCategory

    severity: RiskSeverity

    text: str

    rationale: str

    source: SourceReference

    requires_human_review: bool

    extracted_values: tuple[
        str,
        ...
    ] = ()


@dataclass(frozen=True)
class ContractRiskAnalysis:
    source_id: str

    findings: tuple[
        ContractRiskFinding,
        ...
    ]

    weighted_risk_score: int

    blocker_count: int

    high_count: int

    review_count: int


class ContractRiskEngine:
    RULES = (
        (
            ContractRiskCategory
            .LIQUIDATED_DAMAGES,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(liquidated damages?|"
                r"per day damages?|"
                r"daily damages?)"
                r"\b",
                re.I,
            ),
            (
                "Potential schedule-linked "
                "financial exposure."
            ),
        ),
        (
            ContractRiskCategory
            .PAYMENT,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(pay[- ]if[- ]paid|"
                r"condition precedent to payment)"
                r"\b",
                re.I,
            ),
            (
                "Payment may depend on upstream "
                "payment; legal/commercial review required."
            ),
        ),
        (
            ContractRiskCategory
            .PAYMENT,
            RiskSeverity.REVIEW,
            re.compile(
                r"\b"
                r"(pay[- ]when[- ]paid|"
                r"payment within \d+ days?|"
                r"net \d+)"
                r"\b",
                re.I,
            ),
            (
                "Payment timing requirement identified."
            ),
        ),
        (
            ContractRiskCategory
            .RETAINAGE,
            RiskSeverity.REVIEW,
            re.compile(
                r"\b"
                r"(retainage|retention)"
                r"\b",
                re.I,
            ),
            (
                "Retainage affects cash flow "
                "and closeout exposure."
            ),
        ),
        (
            ContractRiskCategory
            .NOTICE,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(written notice within|"
                r"notice within \d+|"
                r"waive.*claim|"
                r"waiver.*claim)"
                r"\b",
                re.I,
            ),
            (
                "Time-sensitive notice or waiver "
                "language may affect claim preservation."
            ),
        ),
        (
            ContractRiskCategory
            .DELAY,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(no damages? for delay|"
                r"delay damages? waived|"
                r"sole remedy.*extension)"
                r"\b",
                re.I,
            ),
            (
                "Delay-cost recovery may be limited."
            ),
        ),
        (
            ContractRiskCategory
            .CHANGE_ORDER,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(no extra work without written|"
                r"written change order required|"
                r"unauthorized extra work)"
                r"\b",
                re.I,
            ),
            (
                "Change-order authorization "
                "requirement identified."
            ),
        ),
        (
            ContractRiskCategory
            .INDEMNITY,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(indemnif|hold harmless|defend)"
                r"\b",
                re.I,
            ),
            (
                "Indemnity/defense obligation "
                "requires legal and insurance review."
            ),
        ),
        (
            ContractRiskCategory
            .INSURANCE,
            RiskSeverity.REVIEW,
            re.compile(
                r"\b"
                r"(additional insured|"
                r"waiver of subrogation|"
                r"insurance limit|"
                r"umbrella|excess liability)"
                r"\b",
                re.I,
            ),
            (
                "Insurance obligation identified."
            ),
        ),
        (
            ContractRiskCategory
            .WARRANTY,
            RiskSeverity.REVIEW,
            re.compile(
                r"\b"
                r"(warranty period|"
                r"workmanship warranty|"
                r"guarantee period)"
                r"\b",
                re.I,
            ),
            (
                "Warranty obligation affects "
                "post-completion risk."
            ),
        ),
        (
            ContractRiskCategory
            .TERMINATION,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(termination for convenience|"
                r"termination for cause|"
                r"right to terminate)"
                r"\b",
                re.I,
            ),
            (
                "Termination rights identified."
            ),
        ),
        (
            ContractRiskCategory
            .DISPUTE,
            RiskSeverity.REVIEW,
            re.compile(
                r"\b"
                r"(arbitration|venue|jurisdiction|"
                r"forum selection|mediation)"
                r"\b",
                re.I,
            ),
            (
                "Dispute-resolution provision identified."
            ),
        ),
        (
            ContractRiskCategory
            .FLOW_DOWN,
            RiskSeverity.HIGH,
            re.compile(
                r"\b"
                r"(flow[- ]down|"
                r"bound by prime contract|"
                r"incorporated by reference)"
                r"\b",
                re.I,
            ),
            (
                "Upstream terms may be incorporated "
                "into subcontract obligations."
            ),
        ),
    )

    VALUE_PATTERN = re.compile(
        r"""
        (?:
            \$\s*\d[\d,]*(?:\.\d+)?
            |
            \d+(?:\.\d+)?\s*%
            |
            \d+\s*(?:calendar|business|working)?\s*days?
            |
            \d+\s*(?:months?|years?)
        )
        """,
        re.I | re.X,
    )

    @classmethod
    def analyze(
        cls,
        *,
        source_id: str,
        text: str,
        page: int | None = None,
    ) -> ContractRiskAnalysis:
        clean = _normalized_text(
            text
        )

        if not clean:
            raise MissingEvidenceError(
                "contract text is empty"
            )

        clauses = tuple(
            clause.strip()
            for clause
            in re.split(
                r"(?<=[.;])\s+",
                clean,
            )
            if clause.strip()
        )

        findings = []

        seen = set()

        for clause in clauses:
            for (
                category,
                severity,
                pattern,
                rationale,
            ) in cls.RULES:
                if not pattern.search(
                    clause
                ):
                    continue

                fingerprint = (
                    category.value,
                    _hash_text(
                        clause
                    )[:16],
                )

                if fingerprint in seen:
                    continue

                seen.add(
                    fingerprint
                )

                values = tuple(
                    match.group(0).strip()
                    for match
                    in cls.VALUE_PATTERN
                    .finditer(
                        clause
                    )
                )

                findings.append(
                    ContractRiskFinding(
                        finding_id=(
                            "risk_"
                            + _hash_text(
                                source_id
                                + "|"
                                + category.value
                                + "|"
                                + clause
                            )[:20]
                        ),
                        category=category,
                        severity=severity,
                        text=clause,
                        rationale=rationale,
                        source=(
                            SourceReference(
                                source_id=(
                                    source_id
                                ),
                                kind=(
                                    EvidenceKind
                                    .CONTRACT
                                ),
                                page=page,
                                excerpt=clause,
                            )
                        ),
                        requires_human_review=(
                            severity
                            >= RiskSeverity
                            .REVIEW
                        ),
                        extracted_values=(
                            values
                        ),
                    )
                )

        score = min(
            100,
            sum(
                {
                    RiskSeverity.INFO:
                        2,
                    RiskSeverity.REVIEW:
                        7,
                    RiskSeverity.HIGH:
                        15,
                    RiskSeverity.BLOCKER:
                        30,
                }[
                    item.severity
                ]
                for item
                in findings
            ),
        )

        return ContractRiskAnalysis(
            source_id=source_id,
            findings=tuple(
                findings
            ),
            weighted_risk_score=score,
            blocker_count=sum(
                1
                for item
                in findings
                if item.severity
                == RiskSeverity.BLOCKER
            ),
            high_count=sum(
                1
                for item
                in findings
                if item.severity
                == RiskSeverity.HIGH
            ),
            review_count=sum(
                1
                for item
                in findings
                if item.severity
                == RiskSeverity.REVIEW
            ),
        )


# ============================================================
# CPM SCHEDULING
# ============================================================


@dataclass(frozen=True)
class ActivityDependency:
    predecessor_id: str

    relation: DependencyType = (
        DependencyType.FS
    )

    lag_days: float = 0.0


@dataclass(frozen=True)
class ScheduleActivity:
    activity_id: str
    name: str

    duration_days: float

    predecessors: tuple[
        ActivityDependency,
        ...
    ] = ()

    trade: str | None = None

    milestone: bool = False

    required_on_site_date: (
        date
        | None
    ) = None


@dataclass(frozen=True)
class ActivityResult:
    activity_id: str
    name: str

    early_start: float
    early_finish: float

    late_start: float
    late_finish: float

    total_float: float

    critical: bool

    duration_days: float


@dataclass(frozen=True)
class ScheduleAnalysis:
    project_duration_days: float

    activities: tuple[
        ActivityResult,
        ...
    ]

    critical_path: tuple[
        str,
        ...
    ]


class CriticalPathEngine:
    EPSILON = 1e-9

    @staticmethod
    def _constraint_start(
        *,
        predecessor: ActivityResult,
        dependency: ActivityDependency,
        activity_duration: float,
    ) -> float:
        lag = (
            dependency.lag_days
        )

        if (
            dependency.relation
            == DependencyType.FS
        ):
            return (
                predecessor.early_finish
                + lag
            )

        if (
            dependency.relation
            == DependencyType.SS
        ):
            return (
                predecessor.early_start
                + lag
            )

        if (
            dependency.relation
            == DependencyType.FF
        ):
            return (
                predecessor.early_finish
                + lag
                - activity_duration
            )

        if (
            dependency.relation
            == DependencyType.SF
        ):
            return (
                predecessor.early_start
                + lag
                - activity_duration
            )

        raise InvalidScheduleError(
            "unsupported dependency relation"
        )

    @classmethod
    def analyze(
        cls,
        activities: Sequence[
            ScheduleActivity
        ],
    ) -> ScheduleAnalysis:
        if not activities:
            raise InvalidScheduleError(
                "schedule has no activities"
            )

        by_id = {}

        for activity in activities:
            if not activity.activity_id:
                raise InvalidScheduleError(
                    "activity_id is required"
                )

            if activity.activity_id in by_id:
                raise InvalidScheduleError(
                    (
                        "duplicate activity: "
                        + activity.activity_id
                    )
                )

            if activity.duration_days < 0:
                raise InvalidScheduleError(
                    "duration cannot be negative"
                )

            if (
                activity.milestone
                and abs(
                    activity.duration_days
                )
                > cls.EPSILON
            ):
                raise InvalidScheduleError(
                    "milestone duration must be zero"
                )

            by_id[
                activity.activity_id
            ] = activity

        for activity in activities:
            for dependency in (
                activity.predecessors
            ):
                if (
                    dependency
                    .predecessor_id
                    not in by_id
                ):
                    raise InvalidScheduleError(
                        (
                            "unknown predecessor: "
                            + dependency
                            .predecessor_id
                        )
                    )

                if (
                    dependency
                    .predecessor_id
                    == activity.activity_id
                ):
                    raise ScheduleCycleError(
                        "self dependency"
                    )

        indegree = {
            activity.activity_id:
                len(
                    activity.predecessors
                )
            for activity
            in activities
        }

        successors = {
            activity.activity_id:
                []
            for activity
            in activities
        }

        for activity in activities:
            for dependency in (
                activity.predecessors
            ):
                successors[
                    dependency.predecessor_id
                ].append(
                    activity.activity_id
                )

        ready = sorted(
            activity_id
            for (
                activity_id,
                degree,
            )
            in indegree.items()
            if degree == 0
        )

        order = []

        while ready:
            activity_id = (
                ready.pop(0)
            )

            order.append(
                activity_id
            )

            for successor in sorted(
                successors[
                    activity_id
                ]
            ):
                indegree[
                    successor
                ] -= 1

                if (
                    indegree[
                        successor
                    ]
                    == 0
                ):
                    ready.append(
                        successor
                    )

                    ready.sort()

        if (
            len(order)
            != len(activities)
        ):
            raise ScheduleCycleError(
                "schedule dependency cycle detected"
            )

        forward = {}

        for activity_id in order:
            activity = by_id[
                activity_id
            ]

            start = 0.0

            for dependency in (
                activity.predecessors
            ):
                predecessor = (
                    forward[
                        dependency
                        .predecessor_id
                    ]
                )

                start = max(
                    start,
                    cls._constraint_start(
                        predecessor=(
                            predecessor
                        ),
                        dependency=(
                            dependency
                        ),
                        activity_duration=(
                            activity
                            .duration_days
                        ),
                    ),
                )

            finish = (
                start
                + activity.duration_days
            )

            forward[
                activity_id
            ] = ActivityResult(
                activity_id=(
                    activity_id
                ),
                name=activity.name,
                early_start=start,
                early_finish=finish,
                late_start=0.0,
                late_finish=0.0,
                total_float=0.0,
                critical=False,
                duration_days=(
                    activity
                    .duration_days
                ),
            )

        project_duration = max(
            item.early_finish
            for item
            in forward.values()
        )

        late_start = {
            activity_id:
                project_duration
                - by_id[
                    activity_id
                ].duration_days
            for activity_id
            in by_id
        }

        late_finish = {
            activity_id:
                project_duration
            for activity_id
            in by_id
        }

        for activity_id in reversed(
            order
        ):
            activity = by_id[
                activity_id
            ]

            if not successors[
                activity_id
            ]:
                late_finish[
                    activity_id
                ] = project_duration

                late_start[
                    activity_id
                ] = (
                    project_duration
                    - activity.duration_days
                )

                continue

            candidates = []

            for successor_id in (
                successors[
                    activity_id
                ]
            ):
                successor = by_id[
                    successor_id
                ]

                dependencies = [
                    dep
                    for dep
                    in successor.predecessors
                    if (
                        dep.predecessor_id
                        == activity_id
                    )
                ]

                for dependency in (
                    dependencies
                ):
                    lag = (
                        dependency
                        .lag_days
                    )

                    if (
                        dependency.relation
                        == DependencyType.FS
                    ):
                        allowed_finish = (
                            late_start[
                                successor_id
                            ]
                            - lag
                        )

                    elif (
                        dependency.relation
                        == DependencyType.SS
                    ):
                        allowed_start = (
                            late_start[
                                successor_id
                            ]
                            - lag
                        )

                        allowed_finish = (
                            allowed_start
                            + activity.duration_days
                        )

                    elif (
                        dependency.relation
                        == DependencyType.FF
                    ):
                        allowed_finish = (
                            late_finish[
                                successor_id
                            ]
                            - lag
                        )

                    elif (
                        dependency.relation
                        == DependencyType.SF
                    ):
                        allowed_start = (
                            late_finish[
                                successor_id
                            ]
                            - lag
                        )

                        allowed_finish = (
                            allowed_start
                            + activity.duration_days
                        )

                    else:
                        raise (
                            InvalidScheduleError(
                                "unsupported dependency"
                            )
                        )

                    candidates.append(
                        allowed_finish
                    )

            if candidates:
                late_finish[
                    activity_id
                ] = min(
                    candidates
                )

                late_start[
                    activity_id
                ] = (
                    late_finish[
                        activity_id
                    ]
                    - activity
                    .duration_days
                )

        results = []

        for activity_id in order:
            item = forward[
                activity_id
            ]

            total_float = (
                late_start[
                    activity_id
                ]
                - item.early_start
            )

            if abs(
                total_float
            ) < cls.EPSILON:
                total_float = 0.0

            results.append(
                ActivityResult(
                    activity_id=(
                        activity_id
                    ),
                    name=item.name,
                    early_start=(
                        item.early_start
                    ),
                    early_finish=(
                        item.early_finish
                    ),
                    late_start=(
                        late_start[
                            activity_id
                        ]
                    ),
                    late_finish=(
                        late_finish[
                            activity_id
                        ]
                    ),
                    total_float=(
                        total_float
                    ),
                    critical=(
                        abs(
                            total_float
                        )
                        <= cls.EPSILON
                    ),
                    duration_days=(
                        item.duration_days
                    ),
                )
            )

        critical_path = tuple(
            item.activity_id
            for item
            in results
            if item.critical
        )

        return ScheduleAnalysis(
            project_duration_days=(
                project_duration
            ),
            activities=tuple(
                results
            ),
            critical_path=(
                critical_path
            ),
        )


# ============================================================
# PROCUREMENT / LONG LEAD
# ============================================================


@dataclass(frozen=True)
class ProcurementPackage:
    package_id: str
    description: str

    submittal_days: int
    review_days: int
    fabrication_days: int
    transit_days: int
    field_buffer_days: int

    required_on_site: date

    quote_date: date | None = None

    source: SourceReference | None = None

    approved_equal_allowed: bool = False


@dataclass(frozen=True)
class ProcurementAnalysis:
    package_id: str
    description: str

    total_lead_days: int

    latest_release_date: date

    days_until_release: int

    risk: ProcurementRisk

    already_late: bool

    source: SourceReference | None


class ProcurementLeadTimeEngine:
    @staticmethod
    def analyze(
        package: ProcurementPackage,
        *,
        as_of: date,
    ) -> ProcurementAnalysis:
        durations = (
            package.submittal_days,
            package.review_days,
            package.fabrication_days,
            package.transit_days,
            package.field_buffer_days,
        )

        if any(
            value < 0
            for value
            in durations
        ):
            raise ValueError(
                "procurement durations cannot be negative"
            )

        total = sum(
            durations
        )

        release = (
            package.required_on_site
            - timedelta(
                days=total
            )
        )

        days_until_release = (
            release
            - as_of
        ).days

        already_late = (
            days_until_release < 0
        )

        if already_late:
            risk = (
                ProcurementRisk
                .CRITICAL
            )

        elif days_until_release <= 7:
            risk = (
                ProcurementRisk
                .CRITICAL
            )

        elif days_until_release <= 21:
            risk = (
                ProcurementRisk
                .LONG_LEAD
            )

        elif total >= 90:
            risk = (
                ProcurementRisk
                .LONG_LEAD
            )

        elif total >= 45:
            risk = (
                ProcurementRisk
                .WATCH
            )

        else:
            risk = (
                ProcurementRisk
                .NORMAL
            )

        return ProcurementAnalysis(
            package_id=(
                package.package_id
            ),
            description=(
                package.description
            ),
            total_lead_days=total,
            latest_release_date=(
                release
            ),
            days_until_release=(
                days_until_release
            ),
            risk=risk,
            already_late=(
                already_late
            ),
            source=(
                package.source
            ),
        )


# ============================================================
# COMPLIANCE MATRIX
# ============================================================


@dataclass(frozen=True)
class ScopeRequirement:
    scope_id: str
    description: str

    trade: str

    required_evidence: frozenset[
        EvidenceKind
    ]

    mandatory: bool = True

    source_refs: tuple[
        SourceReference,
        ...
    ] = ()


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str

    kind: EvidenceKind

    description: str

    trade: str

    scope_id: str | None

    source: SourceReference

    value_fingerprint: str | None = None


@dataclass(frozen=True)
class ScopeComplianceResult:
    scope_id: str
    description: str
    trade: str

    state: ComplianceState

    found_kinds: frozenset[
        EvidenceKind
    ]

    missing_kinds: frozenset[
        EvidenceKind
    ]

    conflict_fingerprints: tuple[
        str,
        ...
    ]

    evidence_ids: tuple[
        str,
        ...
    ]


class ScopeComplianceEngine:
    @staticmethod
    def evaluate(
        *,
        requirements: Sequence[
            ScopeRequirement
        ],
        evidence: Sequence[
            EvidenceRecord
        ],
    ) -> tuple[
        ScopeComplianceResult,
        ...
    ]:
        results = []

        for requirement in requirements:
            matching = [
                item
                for item
                in evidence
                if (
                    item.scope_id
                    == requirement.scope_id
                    or (
                        item.scope_id
                        is None
                        and item.trade.lower()
                        == requirement
                        .trade
                        .lower()
                    )
                )
            ]

            found = frozenset(
                item.kind
                for item
                in matching
            )

            missing = (
                requirement
                .required_evidence
                - found
            )

            fingerprints = tuple(
                sorted(
                    {
                        item
                        .value_fingerprint
                        for item
                        in matching
                        if item
                        .value_fingerprint
                    }
                )
            )

            conflict = (
                len(
                    fingerprints
                )
                > 1
            )

            if conflict:
                state = (
                    ComplianceState
                    .CONFLICT
                )

            elif missing:
                state = (
                    ComplianceState
                    .UNRESOLVED
                    if requirement
                    .mandatory
                    else ComplianceState
                    .REVIEW_REQUIRED
                )

            else:
                state = (
                    ComplianceState
                    .SATISFIED
                )

            results.append(
                ScopeComplianceResult(
                    scope_id=(
                        requirement
                        .scope_id
                    ),
                    description=(
                        requirement
                        .description
                    ),
                    trade=(
                        requirement.trade
                    ),
                    state=state,
                    found_kinds=found,
                    missing_kinds=(
                        frozenset(
                            missing
                        )
                    ),
                    conflict_fingerprints=(
                        fingerprints
                        if conflict
                        else ()
                    ),
                    evidence_ids=tuple(
                        item.evidence_id
                        for item
                        in matching
                    ),
                )
            )

        return tuple(
            results
        )


# ============================================================
# AUTOMATIC RFI ENGINE
# ============================================================


@dataclass(frozen=True)
class RFICandidate:
    rfi_id: str

    scope_id: str

    trade: str

    subject: str

    question: str

    severity: RFISeverity

    reason_code: str

    evidence_refs: tuple[
        SourceReference,
        ...
    ]


class AutomaticRFIEngine:
    @staticmethod
    def from_compliance(
        *,
        compliance: Sequence[
            ScopeComplianceResult
        ],
        evidence: Sequence[
            EvidenceRecord
        ],
    ) -> tuple[
        RFICandidate,
        ...
    ]:
        by_id = {
            item.evidence_id:
                item
            for item
            in evidence
        }

        rfis = []

        for item in compliance:
            refs = tuple(
                by_id[
                    evidence_id
                ].source
                for evidence_id
                in item.evidence_ids
                if evidence_id
                in by_id
            )

            if (
                item.state
                == ComplianceState
                .CONFLICT
            ):
                rfis.append(
                    RFICandidate(
                        rfi_id=(
                            "rfi_"
                            + _hash_text(
                                item.scope_id
                                + "|conflict"
                            )[:20]
                        ),
                        scope_id=(
                            item.scope_id
                        ),
                        trade=(
                            item.trade
                        ),
                        subject=(
                            "Conflicting requirements: "
                            + item.description
                        ),
                        question=(
                            "Conflicting source information "
                            "was identified for this scope. "
                            "Please identify the governing "
                            "requirement, dimension, material, "
                            "or detail before pricing/execution."
                        ),
                        severity=(
                            RFISeverity
                            .BLOCKING
                        ),
                        reason_code=(
                            "SOURCE_CONFLICT"
                        ),
                        evidence_refs=refs,
                    )
                )

            elif (
                item.state
                == ComplianceState
                .UNRESOLVED
            ):
                missing = ", ".join(
                    sorted(
                        kind.value
                        for kind
                        in item.missing_kinds
                    )
                )

                rfis.append(
                    RFICandidate(
                        rfi_id=(
                            "rfi_"
                            + _hash_text(
                                item.scope_id
                                + "|missing|"
                                + missing
                            )[:20]
                        ),
                        scope_id=(
                            item.scope_id
                        ),
                        trade=(
                            item.trade
                        ),
                        subject=(
                            "Missing governing information: "
                            + item.description
                        ),
                        question=(
                            "The bid documents do not provide "
                            "all required governing evidence "
                            f"for this scope ({missing}). "
                            "Please provide or identify the "
                            "governing information."
                        ),
                        severity=(
                            RFISeverity
                            .BLOCKING
                        ),
                        reason_code=(
                            "MISSING_GOVERNING_EVIDENCE"
                        ),
                        evidence_refs=refs,
                    )
                )

            elif (
                item.state
                == ComplianceState
                .REVIEW_REQUIRED
            ):
                rfis.append(
                    RFICandidate(
                        rfi_id=(
                            "rfi_"
                            + _hash_text(
                                item.scope_id
                                + "|review"
                            )[:20]
                        ),
                        scope_id=(
                            item.scope_id
                        ),
                        trade=(
                            item.trade
                        ),
                        subject=(
                            "Scope clarification: "
                            + item.description
                        ),
                        question=(
                            "Please confirm the intended "
                            "requirement for this scope."
                        ),
                        severity=(
                            RFISeverity.REVIEW
                        ),
                        reason_code=(
                            "REVIEW_REQUIRED"
                        ),
                        evidence_refs=refs,
                    )
                )

        return tuple(
            rfis
        )


# ============================================================
# EXECUTIVE BID READINESS
# ============================================================


@dataclass(frozen=True)
class BidReadinessInput:
    contract_risk: (
        ContractRiskAnalysis
        | None
    )

    compliance: tuple[
        ScopeComplianceResult,
        ...
    ]

    rfis: tuple[
        RFICandidate,
        ...
    ]

    procurement: tuple[
        ProcurementAnalysis,
        ...
    ]

    schedule: (
        ScheduleAnalysis
        | None
    )


@dataclass(frozen=True)
class BidReadinessAssessment:
    score: int

    ready_for_submission: bool

    blocker_count: int

    unresolved_scope_count: int

    critical_procurement_count: int

    high_contract_risk_count: int

    critical_path_activity_count: int

    reasons: tuple[
        str,
        ...
    ]


class BidReadinessEngine:
    @staticmethod
    def assess(
        data: BidReadinessInput,
    ) -> BidReadinessAssessment:
        unresolved = sum(
            1
            for item
            in data.compliance
            if item.state
            in {
                ComplianceState.UNRESOLVED,
                ComplianceState.CONFLICT,
            }
        )

        blocker_rfis = sum(
            1
            for item
            in data.rfis
            if item.severity
            == RFISeverity.BLOCKING
        )

        critical_procurement = sum(
            1
            for item
            in data.procurement
            if item.risk
            == ProcurementRisk
            .CRITICAL
        )

        high_contract = (
            (
                data.contract_risk
                .high_count
                + data.contract_risk
                .blocker_count
            )
            if data.contract_risk
            is not None
            else 0
        )

        critical_path_count = (
            len(
                data.schedule
                .critical_path
            )
            if data.schedule
            is not None
            else 0
        )

        blockers = (
            blocker_rfis
            + critical_procurement
            + (
                data.contract_risk
                .blocker_count
                if data.contract_risk
                is not None
                else 0
            )
        )

        deductions = (
            unresolved * 12
            + blocker_rfis * 10
            + critical_procurement * 12
            + high_contract * 6
        )

        score = max(
            0,
            min(
                100,
                100 - deductions,
            ),
        )

        reasons = []

        if unresolved:
            reasons.append(
                f"{unresolved} unresolved/conflicting scope item(s)"
            )

        if blocker_rfis:
            reasons.append(
                f"{blocker_rfis} blocking RFI candidate(s)"
            )

        if critical_procurement:
            reasons.append(
                f"{critical_procurement} critical procurement item(s)"
            )

        if high_contract:
            reasons.append(
                f"{high_contract} high/blocking contract risk item(s)"
            )

        ready = (
            blockers == 0
            and unresolved == 0
            and score >= 80
        )

        if ready:
            reasons.append(
                "No modeled blocking condition remains."
            )

        return BidReadinessAssessment(
            score=score,
            ready_for_submission=ready,
            blocker_count=blockers,
            unresolved_scope_count=(
                unresolved
            ),
            critical_procurement_count=(
                critical_procurement
            ),
            high_contract_risk_count=(
                high_contract
            ),
            critical_path_activity_count=(
                critical_path_count
            ),
            reasons=tuple(
                reasons
            ),
        )
