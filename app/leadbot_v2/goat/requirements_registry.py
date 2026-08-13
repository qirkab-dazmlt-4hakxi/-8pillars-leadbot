from __future__ import annotations

PRODUCT = "GOAT OS"
OWNER = "Twins Development"

# This registry is deliberately machine-readable.
# Removing a mandatory capability should break the assurance tests.

MANDATORY_REQUIREMENTS = frozenset({
    # Executive / company
    "executive_command_center",
    "executive_intelligence",
    "multi_company_operations",
    "authority_matrix",
    "executive_escalation",
    "dashboards",

    # CRM / sales
    "crm",
    "lead_management",
    "contact_management",
    "opportunity_management",
    "sales_pipeline",
    "follow_up",
    "sales_ops_handoff",
    "proposal_management",
    "bid_no_bid",
    "gatekeeper_mapping",
    "nda_confidentiality",

    # Communications
    "business_phone",
    "voice_ai",
    "sms",
    "email",
    "web_chat",
    "call_transcription",
    "human_handoff",
    "appointment_scheduling",

    # Workforce
    "philippines_call_center",
    "texas_operations",
    "timezone_aware_queues",
    "role_scoped_sales_team",

    # Client
    "client_portal",
    "project_manager_messaging",
    "project_documents",
    "project_photos",
    "client_approvals",

    # Lead intelligence
    "lead_discovery",
    "buyer_intent",
    "contactability",
    "geographic_intelligence",
    "commercial_leads",
    "multifamily_leads",
    "government_leads",
    "residential_leads",
    "public_contact_intelligence",

    # Preconstruction
    "quantum_estimate",
    "plan_ingestion",
    "specification_ingestion",
    "vector_pdf",
    "computer_vision",
    "scale_calibration",
    "measurement",
    "takeoff",
    "rfi",
    "bid_risk",
    "proposal_generation",
    "estimate_provenance",
    "estimate_learning",

    # Trades
    "concrete",
    "structural_concrete",
    "rebar",
    "formwork",
    "earthwork",
    "excavation",
    "grading",
    "trenching",
    "electrical",
    "plumbing",
    "mechanical",
    "hvac",
    "mep",
    "waterproofing",
    "drainage",
    "fire_life_safety",

    # Design / engineering
    "architecture",
    "structural_engineering",
    "civil_engineering",
    "electrical_engineering",
    "plumbing_engineering",
    "mep_engineering",
    "cad_bim_interoperability",
    "drawing_qa_qc",
    "constructability_review",
    "value_engineering",

    # Construction operations
    "project_management",
    "scheduling",
    "crews",
    "subcontractors",
    "vendors",
    "materials",
    "procurement",
    "daily_reports",
    "inspections",
    "quality_control",
    "change_orders",
    "punch_lists",
    "as_builts",
    "closeout",
    "warranties",

    # Financial
    "accounting",
    "job_costing",
    "ar",
    "ap",
    "invoicing",
    "collections",
    "wip",
    "profit_loss",
    "cash_flow",
    "forecasting",
    "budgets",
    "profit_sharing",
    "financial_permissions",

    # Payments
    "ach",
    "credit_cards",
    "debit_cards",
    "zelle_workflow",
    "bitcoin",
    "wallet_isolation",

    # Growth
    "marketing_intelligence",
    "seo",
    "local_seo",
    "google_business_profile",
    "social_media",
    "campaigns",
    "attribution",
    "ab_testing",
    "brand_governance",
    "marketing_roi",

    # Land / development
    "land_intelligence",
    "county_records",
    "deeds",
    "parcel_gis",
    "tax_records",
    "zoning",
    "future_land_use",
    "floodplain",
    "utilities",
    "development_scoring",
    "assemblage",

    # Company knowledge
    "company_knowledge",
    "website_guidance",
    "approved_document_delivery",

    # Marissa
    "marissa_sanctuary",
    "buddhist_reflection",
    "love_notes",
    "quiet_hours",

    # Security
    "security_team",
    "security_console",
    "zero_trust",
    "default_deny",
    "least_privilege",
    "rbac",
    "abac",
    "passkeys",
    "face_id",
    "touch_id",
    "windows_hello",
    "device_trust",
    "network_risk",
    "tenant_isolation",
    "business_unit_isolation",
    "project_isolation",
    "encryption",
    "secret_isolation",
    "secret_rotation",
    "rate_limiting",
    "replay_protection",
    "prompt_injection_defense",
    "sandboxing",
    "tool_allowlists",
    "anomaly_detection",
    "tamper_evident_audit",
    "secret_scanning",
    "dependency_scanning",
    "sbom",
    "supply_chain_security",

    # Safety / resilience
    "circuit_breakers",
    "failover",
    "quarantine",
    "rollback",
    "safe_mode",
    "halt",
    "human_override",
    "incident_escalation",
    "double_fail_safe",
    "backup_restore",
    "disaster_recovery",

    # Learning
    "controlled_self_learning",
    "performance_drift",
    "fault_learning",
    "historical_replay",
    "adversarial_testing",
    "canary_deployment",

    # Platforms / commercialization
    "apple_products",
    "macos",
    "ios",
    "ipados",
    "windows",
    "web",
    "multi_tenant_saas",
    "server_side_ip_protection",
})


CRITICAL_REQUIREMENTS = frozenset({
    "crm",
    "lead_discovery",
    "quantum_estimate",
    "rfi",
    "concrete",
    "earthwork",
    "electrical",
    "plumbing",
    "architecture",
    "structural_engineering",
    "financial_permissions",
    "marketing_intelligence",
    "land_intelligence",
    "philippines_call_center",
    "client_portal",
    "marissa_sanctuary",
    "security_team",
    "zero_trust",
    "double_fail_safe",
    "controlled_self_learning",
    "apple_products",
    "windows",
})


def validate_registry() -> None:
    missing = CRITICAL_REQUIREMENTS - MANDATORY_REQUIREMENTS

    if missing:
        raise RuntimeError(
            "GOAT REQUIREMENT LOSS DETECTED: "
            + ", ".join(sorted(missing))
        )
