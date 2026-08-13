from __future__ import annotations

from dataclasses import dataclass


BLUEPRINT_VERSION = "2026-08-13"
PRODUCT = "GOAT OS"
OWNER = "Twins Development"


MANDATORY_DOMAINS = frozenset({
    "executive_intelligence",
    "crm",
    "sales",
    "philippines_call_center",
    "communications",
    "company_knowledge",
    "client_portal",
    "construction_operations",
    "preconstruction",
    "estimating",
    "takeoff",
    "rfi",
    "architecture",
    "structural_engineering",
    "civil_engineering",
    "electrical",
    "plumbing",
    "mep",
    "earthwork",
    "finance",
    "accounting",
    "payments",
    "materials",
    "procurement",
    "land_intelligence",
    "development",
    "marketing",
    "marissa_sanctuary",
    "security_team",
    "security_control_plane",
    "fail_safe",
    "self_learning",
    "private_projects",
    "multi_tenant_saas",
    "apple_platforms",
    "windows",
})


MANDATORY_SAFETY = frozenset({
    "default_deny",
    "least_privilege",
    "passkeys",
    "biometric_platform_auth",
    "device_trust",
    "tenant_isolation",
    "business_unit_isolation",
    "project_isolation",
    "secret_isolation",
    "encryption",
    "audit",
    "rate_limiting",
    "replay_protection",
    "prompt_injection_defense",
    "tool_allowlists",
    "sandboxing",
    "anomaly_detection",
    "circuit_breakers",
    "quarantine",
    "safe_mode",
    "halt",
    "human_override",
    "backup_restore",
    "secret_scanning",
    "supply_chain_security",
})


@dataclass(frozen=True)
class ProductIdentity:
    name: str = PRODUCT
    owner: str = OWNER
    version: str = BLUEPRINT_VERSION


def validate_master_manifest() -> None:
    required = {
        "crm",
        "preconstruction",
        "estimating",
        "rfi",
        "architecture",
        "structural_engineering",
        "electrical",
        "plumbing",
        "earthwork",
        "finance",
        "marketing",
        "land_intelligence",
        "security_team",
        "security_control_plane",
        "fail_safe",
        "philippines_call_center",
        "marissa_sanctuary",
        "client_portal",
        "apple_platforms",
        "windows",
    }

    missing = required - MANDATORY_DOMAINS

    if missing:
        raise RuntimeError(
            f"GOAT master capability loss detected: {sorted(missing)}"
        )


validate_master_manifest()
