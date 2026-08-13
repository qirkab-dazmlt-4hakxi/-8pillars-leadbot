import unittest

from leadbot_v2.goat.master_manifest import (
    MANDATORY_DOMAINS,
    MANDATORY_SAFETY,
    OWNER,
    PRODUCT,
    validate_master_manifest,
)


class GoatMasterManifestTests(unittest.TestCase):

    def test_product_identity(self):
        self.assertEqual(PRODUCT, "GOAT OS")
        self.assertEqual(OWNER, "Twins Development")

    def test_master_manifest_validates(self):
        validate_master_manifest()

    def test_core_company_systems_cannot_disappear(self):
        required = {
            "crm",
            "preconstruction",
            "estimating",
            "architecture",
            "structural_engineering",
            "electrical",
            "plumbing",
            "earthwork",
            "finance",
            "marketing",
            "land_intelligence",
            "security_team",
            "philippines_call_center",
            "marissa_sanctuary",
            "client_portal",
        }
        self.assertTrue(required.issubset(MANDATORY_DOMAINS))

    def test_security_baseline_cannot_disappear(self):
        required = {
            "default_deny",
            "least_privilege",
            "device_trust",
            "tenant_isolation",
            "secret_isolation",
            "prompt_injection_defense",
            "circuit_breakers",
            "quarantine",
            "safe_mode",
            "halt",
            "human_override",
            "backup_restore",
        }
        self.assertTrue(required.issubset(MANDATORY_SAFETY))


if __name__ == "__main__":
    unittest.main()
