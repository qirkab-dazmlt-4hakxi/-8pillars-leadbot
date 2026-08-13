import unittest
from dataclasses import replace

from leadbot_v2.goat.access_control import (
    AuthorizationEngine,
    Permission,
    Principal,
    ResourceContext,
    Role,
)
from leadbot_v2.goat.security.security_team import (
    DualControlError,
    SecurityAction,
    SecurityAuthorizationError,
    SecurityControlPlane,
    SecurityTeamPolicy,
)


TENANT = "twins-development"


def principal(user_id: str, role: Role) -> Principal:
    return Principal(
        user_id=user_id,
        tenant_id=TENANT,
        role=role,
        email=f"{user_id}@example.com",
    )


class SecurityTeamTests(unittest.TestCase):

    def setUp(self):
        self.engine = AuthorizationEngine()
        self.security = SecurityControlPlane()

        self.president = principal(
            "president",
            Role.PRESIDENT,
        )

        self.security_admin = principal(
            "security-admin",
            Role.SECURITY_ADMIN,
        )

        self.analyst = principal(
            "security-analyst",
            Role.SECURITY_ANALYST,
        )

        self.sales = principal(
            "sales-user",
            Role.SALES,
        )

    def test_security_analyst_can_view_console(self):
        self.assertTrue(
            SecurityTeamPolicy.may_view(self.analyst)
        )

    def test_sales_cannot_view_security_console(self):
        with self.assertRaises(
            SecurityAuthorizationError
        ):
            SecurityTeamPolicy.require_view(self.sales)

    def test_security_analyst_cannot_mutate_sessions(self):
        with self.assertRaises(
            SecurityAuthorizationError
        ):
            self.security.revoke_session(
                principal=self.analyst,
                session_id="session-1",
                reason="test",
            )

    def test_security_admin_can_quarantine_session(self):
        self.security.quarantine_session(
            principal=self.security_admin,
            session_id="session-attack",
            reason="suspicious behavior",
        )

        self.assertIn(
            "session-attack",
            self.security.quarantined_sessions,
        )

    def test_security_admin_can_revoke_device(self):
        self.security.revoke_device(
            principal=self.security_admin,
            device_id="device-attack",
            reason="device compromise",
        )

        self.assertIn(
            "device-attack",
            self.security.revoked_devices,
        )

    def test_security_admin_does_not_receive_financial_access(self):
        result = self.engine.authorize(
            self.security_admin,
            Permission.FINANCIAL_READ,
            ResourceContext(
                tenant_id=TENANT,
            ),
        )

        self.assertFalse(result.allowed)

    def test_security_analyst_does_not_receive_financial_access(self):
        result = self.engine.authorize(
            self.analyst,
            Permission.FINANCIAL_READ,
            ResourceContext(
                tenant_id=TENANT,
            ),
        )

        self.assertFalse(result.allowed)

    def test_single_identity_cannot_execute_critical_action(self):
        request = self.security.request_critical_action(
            principal=self.security_admin,
            action=SecurityAction.GLOBAL_HALT,
            target="goat-os",
            reason="critical compromise",
        )

        with self.assertRaises(DualControlError):
            self.security.execute_critical_action(
                principal=self.security_admin,
                request_id=request.request_id,
            )

    def test_same_identity_cannot_approve_twice(self):
        request = self.security.request_critical_action(
            principal=self.security_admin,
            action=SecurityAction.GLOBAL_HALT,
            target="goat-os",
            reason="critical compromise",
        )

        with self.assertRaises(DualControlError):
            self.security.approve_critical_action(
                principal=self.security_admin,
                request_id=request.request_id,
            )

    def test_security_plus_executive_can_authorize_critical_action(self):
        request = self.security.request_critical_action(
            principal=self.security_admin,
            action=SecurityAction.GLOBAL_HALT,
            target="goat-os",
            reason="verified compromise",
        )

        self.security.approve_critical_action(
            principal=self.president,
            request_id=request.request_id,
        )

        result = self.security.execute_critical_action(
            principal=self.security_admin,
            request_id=request.request_id,
        )

        self.assertTrue(result.executed)

    def test_audit_chain_valid(self):
        self.security.revoke_session(
            principal=self.security_admin,
            session_id="bad-session",
            reason="credential anomaly",
        )

        self.security.revoke_device(
            principal=self.security_admin,
            device_id="bad-device",
            reason="device anomaly",
        )

        self.assertTrue(
            self.security.audit.verify()
        )

    def test_audit_tampering_detected(self):
        self.security.revoke_session(
            principal=self.security_admin,
            session_id="bad-session",
            reason="credential anomaly",
        )

        original = self.security.audit._events[0]

        self.security.audit._events[0] = replace(
            original,
            reason="tampered reason",
        )

        self.assertFalse(
            self.security.audit.verify()
        )

    def test_audit_actions_require_reason(self):
        with self.assertRaises(ValueError):
            self.security.revoke_session(
                principal=self.security_admin,
                session_id="session",
                reason="",
            )


if __name__ == "__main__":
    unittest.main()
