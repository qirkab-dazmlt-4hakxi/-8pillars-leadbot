import hashlib
import unittest

from dataclasses import replace
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from leadbot_v2.goat.gateway import (
    ApiRisk,
    AuthStrength,
    AuthorizationDenied,
    CrossPlatformSyncFeed,
    DataClass,
    DeviceBlocked,
    DeviceSignals,
    DeviceTrustEngine,
    DeviceTrustLevel,
    EndpointSpec,
    GatewayAuditIntegrityError,
    GatewayRequest,
    IdempotencyConflict,
    IdempotencyRequired,
    NotificationChannel,
    NotificationOutbox,
    NotificationStatus,
    ObjectStatus,
    ObjectVisibility,
    PortalAccessDenied,
    PortalAuthorizationService,
    PortalPermission,
    RateLimitExceeded,
    ReplayDetected,
    SecureApplicationGateway,
    SecureObjectRegistry,
    SessionExpired,
    SessionRevoked,
    SessionTokenService,
    StepUpRequired,
    SyncOperation,
    TenantBoundaryViolation,
    UploadIntentError,
)


UTC = timezone.utc


class SessionTests(
    unittest.TestCase
):
    def setUp(self):
        self.service = SessionTokenService(
            secret=(
                b"x" * 64
            )
        )

        self.now = datetime(
            2026,
            8,
            15,
            15,
            0,
            tzinfo=UTC,
        )

    def test_issue_verify(self):
        token, claims = (
            self.service.issue(
                user_id="u1",
                tenant_id="t1",
                role="president",
                device_id="d1",
                auth_strength=(
                    AuthStrength.PASSKEY
                ),
                now=self.now,
            )
        )

        verified = (
            self.service.verify(
                token,
                now=self.now,
            )
        )

        self.assertEqual(
            claims.session_id,
            verified.session_id,
        )

    def test_tamper_fails(self):
        token, _ = (
            self.service.issue(
                user_id="u1",
                tenant_id="t1",
                role="president",
                device_id="d1",
                auth_strength=(
                    AuthStrength.PASSKEY
                ),
                now=self.now,
            )
        )

        version, payload, signature = (
            token.split(
                ".",
                2,
            )
        )

        # Alter a character well inside the HMAC encoding rather than
        # the final Base64URL character, whose unused padding bits can
        # otherwise produce an equivalent byte string.
        index = (
            len(signature)
            // 2
        )

        replacement = (
            "A"
            if signature[index]
            != "A"
            else "B"
        )

        tampered_signature = (
            signature[:index]
            + replacement
            + signature[index + 1:]
        )

        tampered = (
            version
            + "."
            + payload
            + "."
            + tampered_signature
        )

        with self.assertRaises(
            Exception
        ):
            self.service.verify(
                tampered,
                now=self.now,
            )

    def test_expiration(self):
        token, _ = (
            self.service.issue(
                user_id="u1",
                tenant_id="t1",
                role="president",
                device_id="d1",
                auth_strength=(
                    AuthStrength.PASSKEY
                ),
                lifetime=timedelta(
                    minutes=5
                ),
                now=self.now,
            )
        )

        with self.assertRaises(
            SessionExpired
        ):
            self.service.verify(
                token,
                now=(
                    self.now
                    + timedelta(
                        minutes=6
                    )
                ),
            )

    def test_revocation(self):
        token, claims = (
            self.service.issue(
                user_id="u1",
                tenant_id="t1",
                role="president",
                device_id="d1",
                auth_strength=(
                    AuthStrength.PASSKEY
                ),
                now=self.now,
            )
        )

        self.service.revoke(
            claims.session_id
        )

        with self.assertRaises(
            SessionRevoked
        ):
            self.service.verify(
                token,
                now=self.now,
            )


class DeviceTrustTests(
    unittest.TestCase
):
    def test_trusted_device(self):
        result = (
            DeviceTrustEngine.assess(
                DeviceSignals(
                    device_id="d1",
                    platform="ios",
                    known_device=True,
                    attested=True,
                )
            )
        )

        self.assertEqual(
            result.level,
            DeviceTrustLevel.TRUSTED,
        )

    def test_dangerous_device(self):
        result = (
            DeviceTrustEngine.assess(
                DeviceSignals(
                    device_id="d1",
                    platform="android",
                    rooted_or_jailbroken=True,
                    impossible_travel=True,
                    attestation_anomaly=True,
                    tor=True,
                )
            )
        )

        self.assertTrue(
            result.blocked
        )


class GatewayTests(
    unittest.TestCase
):
    def setUp(self):
        self.sessions = (
            SessionTokenService(
                secret=(
                    b"z" * 64
                )
            )
        )

        self.gateway = (
            SecureApplicationGateway(
                sessions=(
                    self.sessions
                )
            )
        )

        self.gateway.register_endpoint(
            EndpointSpec(
                name="project.read",
                method="GET",
                path="/projects/1",
                allowed_roles=(
                    frozenset(
                        {
                            "president",
                            "project_manager",
                        }
                    )
                ),
                data_class=(
                    DataClass.CONFIDENTIAL
                ),
                risk=ApiRisk.READ,
                minimum_auth=(
                    AuthStrength.MFA
                ),
            )
        )

        self.gateway.register_endpoint(
            EndpointSpec(
                name="finance.mutate",
                method="POST",
                path="/finance/adjust",
                allowed_roles=(
                    frozenset(
                        {
                            "president"
                        }
                    )
                ),
                data_class=(
                    DataClass.FINANCIAL
                ),
                risk=(
                    ApiRisk.HIGH_RISK
                ),
                require_idempotency=True,
                minimum_auth=(
                    AuthStrength.PASSKEY
                ),
            )
        )

        self.token, _ = (
            self.sessions.issue(
                user_id="u1",
                tenant_id="t1",
                role="president",
                device_id="d1",
                auth_strength=(
                    AuthStrength.PASSKEY
                ),
            )
        )

    def trusted(self):
        return DeviceSignals(
            device_id="d1",
            platform="ios",
            known_device=True,
            attested=True,
        )

    def test_read(self):
        request = GatewayRequest(
            method="GET",
            path="/projects/1",
            tenant_id="t1",
            bearer_token=self.token,
            device=self.trusted(),
            request_nonce="n1",
        )

        result = (
            self.gateway.execute(
                request,
                handler=lambda decision: {
                    "ok":
                        True
                },
            )
        )

        self.assertTrue(
            result["ok"]
        )

    def test_cross_tenant_block(self):
        request = GatewayRequest(
            method="GET",
            path="/projects/1",
            tenant_id="t2",
            bearer_token=self.token,
            device=self.trusted(),
            request_nonce="n1",
        )

        with self.assertRaises(
            TenantBoundaryViolation
        ):
            self.gateway.authorize(
                request
            )

    def test_device_mismatch(self):
        request = GatewayRequest(
            method="GET",
            path="/projects/1",
            tenant_id="t1",
            bearer_token=self.token,
            device=DeviceSignals(
                device_id="other",
                platform="ios",
                known_device=True,
                attested=True,
            ),
            request_nonce="n1",
        )

        with self.assertRaises(
            AuthorizationDenied
        ):
            self.gateway.authorize(
                request
            )

    def test_replay_block(self):
        request = GatewayRequest(
            method="GET",
            path="/projects/1",
            tenant_id="t1",
            bearer_token=self.token,
            device=self.trusted(),
            request_nonce="same",
        )

        self.gateway.authorize(
            request
        )

        with self.assertRaises(
            ReplayDetected
        ):
            self.gateway.authorize(
                request
            )

    def test_high_risk_requires_idempotency(self):
        request = GatewayRequest(
            method="POST",
            path="/finance/adjust",
            tenant_id="t1",
            bearer_token=self.token,
            device=self.trusted(),
            request_nonce="finance-1",
            body={
                "amount":
                    100
            },
        )

        with self.assertRaises(
            IdempotencyRequired
        ):
            self.gateway.authorize(
                request
            )

    def test_high_risk_idempotent_execution(self):
        request1 = GatewayRequest(
            method="POST",
            path="/finance/adjust",
            tenant_id="t1",
            bearer_token=self.token,
            device=self.trusted(),
            request_nonce="finance-2",
            idempotency_key="idem-1",
            body={
                "amount":
                    100
            },
        )

        calls = {
            "count":
                0
        }

        def handler(decision):
            calls["count"] += 1

            return {
                "result":
                    calls["count"]
            }

        first = self.gateway.execute(
            request1,
            handler=handler,
        )

        request2 = replace(
            request1,
            request_nonce="finance-3",
        )

        second = self.gateway.execute(
            request2,
            handler=handler,
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            calls["count"],
            1,
        )

    def test_idempotency_conflict(self):
        first = GatewayRequest(
            method="POST",
            path="/finance/adjust",
            tenant_id="t1",
            bearer_token=self.token,
            device=self.trusted(),
            request_nonce="finance-4",
            idempotency_key="same-key",
            body={
                "amount":
                    100
            },
        )

        self.gateway.execute(
            first,
            handler=lambda d: {
                "ok":
                    True
            },
        )

        second = replace(
            first,
            request_nonce="finance-5",
            body={
                "amount":
                    200
            },
        )

        with self.assertRaises(
            IdempotencyConflict
        ):
            self.gateway.execute(
                second,
                handler=lambda d: {
                    "ok":
                        True
                },
            )

    def test_risky_device_stepup(self):
        risky = DeviceSignals(
            device_id="d1",
            platform="ios",
            known_device=False,
            attested=False,
            vpn_or_proxy=True,
        )

        request = GatewayRequest(
            method="POST",
            path="/finance/adjust",
            tenant_id="t1",
            bearer_token=self.token,
            device=risky,
            request_nonce="finance-risk",
            idempotency_key="risk",
            body={},
        )

        with self.assertRaises(
            StepUpRequired
        ):
            self.gateway.authorize(
                request
            )

    def test_audit_chain(self):
        request = GatewayRequest(
            method="GET",
            path="/projects/1",
            tenant_id="t1",
            bearer_token=self.token,
            device=self.trusted(),
            request_nonce="audit-1",
        )

        self.gateway.execute(
            request,
            handler=lambda d: {
                "ok":
                    True
            },
        )

        self.assertTrue(
            self.gateway
            .audit
            .verify()
        )


class PortalTests(
    unittest.TestCase
):
    def test_project_scope(self):
        service = (
            PortalAuthorizationService()
        )

        service.grant(
            tenant_id="t1",
            principal_id="client",
            project_ids={
                "p1"
            },
            permissions={
                PortalPermission
                .VIEW_PROJECT
            },
        )

        service.require(
            tenant_id="t1",
            principal_id="client",
            project_id="p1",
            permission=(
                PortalPermission
                .VIEW_PROJECT
            ),
        )

        with self.assertRaises(
            PortalAccessDenied
        ):
            service.require(
                tenant_id="t1",
                principal_id="client",
                project_id="p2",
                permission=(
                    PortalPermission
                    .VIEW_PROJECT
                ),
            )

    def test_tenant_isolation(self):
        service = (
            PortalAuthorizationService()
        )

        service.grant(
            tenant_id="t1",
            principal_id="client",
            project_ids={
                "p1"
            },
            permissions={
                PortalPermission
                .VIEW_DOCUMENTS
            },
        )

        with self.assertRaises(
            PortalAccessDenied
        ):
            service.require(
                tenant_id="t2",
                principal_id="client",
                project_id="p1",
                permission=(
                    PortalPermission
                    .VIEW_DOCUMENTS
                ),
            )


class ObjectTests(
    unittest.TestCase
):
    def test_verified_upload(self):
        registry = (
            SecureObjectRegistry()
        )

        content = (
            b"GOAT PLAN FILE"
        )

        digest = (
            hashlib.sha256(
                content
            ).hexdigest()
        )

        intent = (
            registry
            .create_upload_intent(
                tenant_id="t1",
                project_id="p1",
                filename="plans.pdf",
                mime_type="application/pdf",
                size_bytes=len(
                    content
                ),
                expected_sha256=(
                    digest
                ),
                visibility=(
                    ObjectVisibility
                    .PROJECT_TEAM
                ),
                created_by="u1",
            )
        )

        record = (
            registry.verify_upload(
                intent_id=(
                    intent.intent_id
                ),
                upload_token=(
                    intent.upload_token
                ),
                content=content,
            )
        )

        self.assertEqual(
            record.status,
            ObjectStatus.VERIFIED,
        )

    def test_hash_mismatch_quarantine(self):
        registry = (
            SecureObjectRegistry()
        )

        expected = (
            hashlib.sha256(
                b"expected"
            ).hexdigest()
        )

        intent = (
            registry
            .create_upload_intent(
                tenant_id="t1",
                project_id="p1",
                filename="x.pdf",
                mime_type="application/pdf",
                size_bytes=5,
                expected_sha256=(
                    expected
                ),
                visibility=(
                    ObjectVisibility
                    .PROJECT_TEAM
                ),
                created_by="u1",
            )
        )

        with self.assertRaises(
            UploadIntentError
        ):
            registry.verify_upload(
                intent_id=(
                    intent.intent_id
                ),
                upload_token=(
                    intent.upload_token
                ),
                content=b"wrong",
            )

        record = (
            registry.objects[
                intent.object_id
            ]
        )

        self.assertEqual(
            record.status,
            ObjectStatus.QUARANTINED,
        )

    def test_one_time_upload_token(self):
        registry = (
            SecureObjectRegistry()
        )

        content = b"abc"

        intent = (
            registry
            .create_upload_intent(
                tenant_id="t1",
                project_id="p1",
                filename="x",
                mime_type="text/plain",
                size_bytes=3,
                expected_sha256=(
                    hashlib.sha256(
                        content
                    ).hexdigest()
                ),
                visibility=(
                    ObjectVisibility
                    .PROJECT_TEAM
                ),
                created_by="u1",
            )
        )

        registry.verify_upload(
            intent_id=(
                intent.intent_id
            ),
            upload_token=(
                intent.upload_token
            ),
            content=content,
        )

        with self.assertRaises(
            UploadIntentError
        ):
            registry.verify_upload(
                intent_id=(
                    intent.intent_id
                ),
                upload_token=(
                    intent.upload_token
                ),
                content=content,
            )


class NotificationTests(
    unittest.TestCase
):
    def test_dedupe(self):
        outbox = (
            NotificationOutbox()
        )

        first = outbox.enqueue(
            tenant_id="t1",
            recipient_id="u1",
            channel=(
                NotificationChannel
                .PUSH
            ),
            event_type="rfi.overdue",
            payload={
                "rfi":
                    10
            },
            dedupe_key="rfi-10",
        )

        second = outbox.enqueue(
            tenant_id="t1",
            recipient_id="u1",
            channel=(
                NotificationChannel
                .PUSH
            ),
            event_type="rfi.overdue",
            payload={
                "rfi":
                    10
            },
            dedupe_key="rfi-10",
        )

        self.assertEqual(
            first.notification_id,
            second.notification_id,
        )

    def test_retry_dead_letter(self):
        outbox = (
            NotificationOutbox(
                max_attempts=2
            )
        )

        item = outbox.enqueue(
            tenant_id="t1",
            recipient_id="u1",
            channel=(
                NotificationChannel
                .EMAIL
            ),
            event_type="test",
            payload={},
        )

        item = outbox.fail(
            item.notification_id
        )

        self.assertEqual(
            item.status,
            NotificationStatus.FAILED,
        )

        item = outbox.fail(
            item.notification_id
        )

        self.assertEqual(
            item.status,
            NotificationStatus.DEAD,
        )


class SyncTests(
    unittest.TestCase
):
    def test_project_filtered_feed(self):
        feed = (
            CrossPlatformSyncFeed()
        )

        feed.append(
            tenant_id="t1",
            project_id="p1",
            entity_type="rfi",
            entity_id="1",
            operation=(
                SyncOperation.CREATE
            ),
            payload={
                "x":
                    1
            },
        )

        feed.append(
            tenant_id="t1",
            project_id="p2",
            entity_type="rfi",
            entity_id="2",
            operation=(
                SyncOperation.CREATE
            ),
            payload={
                "x":
                    2
            },
        )

        page = feed.page(
            tenant_id="t1",
            cursor=0,
            allowed_project_ids={
                "p1"
            },
        )

        self.assertEqual(
            len(page.changes),
            1,
        )

        self.assertEqual(
            page.changes[0]
            .project_id,
            "p1",
        )

    def test_cross_tenant_feed_isolation(self):
        feed = (
            CrossPlatformSyncFeed()
        )

        feed.append(
            tenant_id="t2",
            project_id="p1",
            entity_type="secret",
            entity_id="1",
            operation=(
                SyncOperation.CREATE
            ),
            payload={
                "secret":
                    True
            },
        )

        page = feed.page(
            tenant_id="t1",
            cursor=0,
            allowed_project_ids={
                "p1"
            },
        )

        self.assertEqual(
            page.changes,
            (),
        )


if __name__ == "__main__":
    unittest.main()
