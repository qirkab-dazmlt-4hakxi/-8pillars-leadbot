import unittest
from pathlib import Path

from leadbot_v2.goat.memory_lock import (
    CRITICAL_PILLARS,
    LOCKED_PILLARS,
    require_memory_lock,
    validate_memory_lock,
)


class GoatMemoryLockTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]

    def test_memory_file_is_healthy(self):
        report = validate_memory_lock(self.root)
        self.assertTrue(report.healthy, report)

    def test_critical_pillars_cannot_disappear(self):
        self.assertTrue(
            CRITICAL_PILLARS.issubset(LOCKED_PILLARS)
        )

    def test_required_memory_lock(self):
        require_memory_lock(self.root)

    def test_business_brain_is_locked(self):
        required = {
            "crm",
            "follow_through",
            "philippines_operations",
            "executive_reasoning",
            "financials",
            "quantum_estimate",
        }
        self.assertTrue(required.issubset(LOCKED_PILLARS))

    def test_security_is_locked(self):
        required = {
            "security_team",
            "security_control_plane",
            "double_fail_safe",
        }
        self.assertTrue(required.issubset(LOCKED_PILLARS))

    def test_platform_and_special_systems_are_locked(self):
        required = {
            "marissa_sanctuary",
            "apple_platforms",
            "windows",
            "marketing",
            "land_intelligence",
            "client_portal",
            "architecture",
            "engineering",
        }
        self.assertTrue(required.issubset(LOCKED_PILLARS))


if __name__ == "__main__":
    unittest.main()
