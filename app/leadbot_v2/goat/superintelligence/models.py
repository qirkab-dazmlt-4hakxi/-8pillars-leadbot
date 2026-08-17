from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any


class IntelligenceError(RuntimeError):
    pass


class InvariantViolation(IntelligenceError):
    pass


class AutonomyLevel(IntEnum):
    OBSERVE = 0
    RECOMMEND = 1
    PREPARE = 2
    EXECUTE_REVERSIBLE = 3
    EXECUTE_BOUNDED = 4
    HUMAN_APPROVAL_REQUIRED = 5


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceBand(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str

    source: str
    claim: str

    value: Any

    observed_at: datetime

    confidence: float
    authority: float

    payload_hash: str
    previous_chain_hash: str
    chain_hash: str

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str

    statement: str

    prior: float
    posterior: float

    supporting_evidence: tuple[str, ...]
    opposing_evidence: tuple[str, ...]

    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Goal:
    goal_id: str

    description: str

    priority: float

    deadline: datetime | None = None

    constraints: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpertOpinion:
    expert_id: str

    answer: Any

    confidence: float

    risk: RiskLevel

    reasoning_summary: str

    evidence_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    latency_ms: float = 0.0


@dataclass(frozen=True)
class Critique:
    critic_id: str

    severity: RiskLevel

    issue: str
    recommendation: str

    confidence: float


@dataclass(frozen=True)
class SimulationSummary:
    simulations: int

    mean: float

    p05: float
    p50: float
    p95: float

    minimum: float
    maximum: float

    probability_below_zero: float

    seed: int


@dataclass(frozen=True)
class Decision:
    decision_id: str

    recommendation: Any

    confidence: float

    risk: RiskLevel

    autonomy_level: AutonomyLevel

    requires_human_approval: bool

    expert_opinions: tuple[
        ExpertOpinion,
        ...,
    ]

    critiques: tuple[
        Critique,
        ...,
    ]

    alternatives: tuple[
        Any,
        ...,
    ] = ()

    unknowns: tuple[
        str,
        ...,
    ] = ()

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class Outcome:
    decision_id: str

    actual_value: float | None

    success: bool

    observed_at: datetime

    notes: str = ""


@dataclass(frozen=True)
class LatencyBudget:
    operation: str

    p50_target_ms: float
    p95_target_ms: float
    p99_target_ms: float


@dataclass(frozen=True)
class LatencySnapshot:
    operation: str

    samples: int

    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float

    within_budget: bool


@dataclass(frozen=True)
class QualificationResult:
    name: str

    passed: bool

    details: str

    duration_ms: float


def utcnow() -> datetime:
    return datetime.now(
        timezone.utc
    )


def ensure_utc(
    value: datetime | None,
) -> datetime:
    result = (
        value
        or utcnow()
    )

    if result.tzinfo is None:
        raise InvariantViolation(
            "timestamp must be timezone-aware"
        )

    return result.astimezone(
        timezone.utc
    )


def clamp01(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(
                value
            ),
        ),
    )


def confidence_band(
    value: float,
) -> ConfidenceBand:
    value = clamp01(
        value
    )

    if value < 0.20:
        return (
            ConfidenceBand.UNKNOWN
        )

    if value < 0.45:
        return (
            ConfidenceBand.LOW
        )

    if value < 0.70:
        return (
            ConfidenceBand.MEDIUM
        )

    if value < 0.90:
        return (
            ConfidenceBand.HIGH
        )

    return ConfidenceBand.VERY_HIGH
