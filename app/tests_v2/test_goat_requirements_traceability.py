import unittest
from pathlib import Path

from leadbot_v2.goat.requirements_registry import (
    CRITICAL_REQUIREMENTS,
    MANDATORY_REQUIREMENTS,
    OWNER,
    PRODUCT,
    validate_registry,
)


class GoatRequirementsTraceabilityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.blueprint = (
            cls.root / "docs" / "GOAT_OS_MASTER_BLUEPRINT.md"
        ).read_text().lower()

    def test_registry_integrity(self):
        validate_registry()

    def test_product_is_twins_development_goat(self):
        self.assertEqual(PRODUCT, "GOAT OS")
        self.assertEqual(OWNER, "Twins Development")

    def test_all_critical_capabilities_registered(self):
        missing = CRITICAL_REQUIREMENTS - MANDATORY_REQUIREMENTS
        self.assertEqual(missing, set())

    def test_blueprint_contains_core_company_systems(self):
        required_phrases = (
            "goat crm",
            "philippines call center",
            "communications",
            "client portal",
            "goat quantum estimate",
            "rfi engine",
            "architecture + engineering studio",
            "financial + accounting intelligence",
            "land + development intelligence",
            "marketing + growth engine",
            "marissa sanctuary",
            "security team",
            "security control plane",
            "fail-safe system",
            "self-learning",
        )

        missing = [
            phrase
            for phrase in required_phrases
            if phrase not in self.blueprint
        ]

        self.assertEqual(
            missing,
            [],
            f"Missing blueprint sections: {missing}",
        )

    def test_blueprint_contains_recovered_requirements(self):
        required_phrases = (
            "gc / cm",
            "estimator",
            "procurement contact",
            "google business profile",
            "sales-to-operations handoff",
            "nda workflows",
            "hvac",
            "fire/life-safety",
            "quality control",
            "as-built documentation",
        )

        missing = [
            phrase
            for phrase in required_phrases
            if phrase not in self.blueprint
        ]

        self.assertEqual(
            missing,
            [],
            f"Recovered requirements missing: {missing}",
        )

    def test_security_baseline_present(self):
        required = {
            "zero_trust",
            "default_deny",
            "least_privilege",
            "passkeys",
            "device_trust",
            "tenant_isolation",
            "secret_isolation",
            "rate_limiting",
            "prompt_injection_defense",
            "anomaly_detection",
            "quarantine",
            "safe_mode",
            "halt",
            "double_fail_safe",
            "backup_restore",
        }

        missing = required - MANDATORY_REQUIREMENTS
        self.assertEqual(missing, set())

    def test_major_platforms_present(self):
        required = {
            "macos",
            "ios",
            "ipados",
            "windows",
            "web",
        }

        missing = required - MANDATORY_REQUIREMENTS
        self.assertEqual(missing, set())

    def test_scope_is_large_enough_to_detect_accidental_truncation(self):
        self.assertGreaterEqual(
            len(MANDATORY_REQUIREMENTS),
            150,
            "GOAT registry unexpectedly lost major requirements",
        )


if __name__ == "__main__":
    unittest.main()
