from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MEMORY_VERSION = "2026-08-13"


LOCKED_PILLARS = frozenset({
    "data_spine",
    "crm",
    "follow_through",
    "philippines_operations",
    "executive_reasoning",
    "financials",
    "quantum_estimate",
    "rfi",
    "architecture",
    "engineering",
    "construction_management",
    "marketing",
    "communications",
    "client_portal",
    "land_intelligence",
    "security_team",
    "security_control_plane",
    "double_fail_safe",
    "controlled_self_learning",
    "marissa_sanctuary",
    "apple_platforms",
    "windows",
    "commercialization",
})


CRITICAL_PILLARS = frozenset({
    "crm",
    "follow_through",
    "philippines_operations",
    "executive_reasoning",
    "financials",
    "quantum_estimate",
    "security_team",
    "security_control_plane",
    "double_fail_safe",
})


@dataclass(frozen=True)
class MemoryLockReport:
    healthy: bool
    missing_pillars: tuple[str, ...]
    missing_phrases: tuple[str, ...]


def validate_memory_lock(repo_root: Path) -> MemoryLockReport:
    blueprint = repo_root / "docs" / "GOAT_OS_BUILD_MEMORY.md"

    if not blueprint.exists():
        return MemoryLockReport(
            healthy=False,
            missing_pillars=tuple(sorted(CRITICAL_PILLARS)),
            missing_phrases=("GOAT_OS_BUILD_MEMORY.md",),
        )

    text = blueprint.read_text(encoding="utf-8").lower()

    phrase_checks = {
        "crm": "full proprietary crm",
        "follow_through": "follow-through engine",
        "philippines_operations": "philippines sales / call center",
        "executive_reasoning": "executive reasoning",
        "financials": "financials",
        "quantum_estimate": "goat quantum estimate",
        "security_team": "security team",
        "security_control_plane": "security control plane",
        "double_fail_safe": "double fail-safe",
        "marissa_sanctuary": "marissa sanctuary",
        "architecture": "architecture + engineering",
        "marketing": "marketing + growth",
        "land_intelligence": "land + development intelligence",
        "communications": "communications",
        "client_portal": "client portal",
        "apple_platforms": "macos",
        "windows": "windows",
    }

    missing_phrases = tuple(
        sorted(
            key
            for key, phrase in phrase_checks.items()
            if phrase not in text
        )
    )

    missing_pillars = tuple(
        sorted(CRITICAL_PILLARS - LOCKED_PILLARS)
    )

    return MemoryLockReport(
        healthy=not missing_pillars and not missing_phrases,
        missing_pillars=missing_pillars,
        missing_phrases=missing_phrases,
    )


def require_memory_lock(repo_root: Path) -> None:
    report = validate_memory_lock(repo_root)

    if not report.healthy:
        raise RuntimeError(
            "GOAT PRODUCT MEMORY LOSS DETECTED | "
            f"pillars={report.missing_pillars} | "
            f"phrases={report.missing_phrases}"
        )
