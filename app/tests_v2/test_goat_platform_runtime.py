import unittest

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from leadbot_v2.goat.platform.runtime import (
    ApiBoundary,
    ApiVersionError,
    ApiVersionRegistry,
    AuditIntegrityError,
    AuthStrength,
    CacheDisposition,
    ClientPlatformRegistry,
    ClientSurface,
    ConflictDisposition,
    ConflictPolicy,
    DataClassification,
    DeterministicConflictResolver,
    DevicePlatform,
    DeviceRegistry,
    DeviceTrust,
    DeviceTrustEngine,
    FormFactor,
    NotificationVisibility,
    OfflineMutationQueue,
    PlatformAccessDenied,
    PushMessage,
    PushPrivacyPolicy,
    ReplayDetected,
    ReplayProtector,
    RuntimeAuditLog,
    RuntimeCapabilityGate,
    SecureCachePolicyEngine,
    SemanticVersion,
    SessionPrincipal,
    SyncMutationState,
    SyncQueueError,
    UnsupportedClient,
    universal_runtime_manifest,
)


UTC = timezone.utc


def fixed_now():
    return datetime(
        2026,
        8,
        15,
        18,
        0,
        tzinfo=UTC,
    )


def device(
    registry,
    *,
    platform=DevicePlatform.IOS,
    form_factor=FormFactor.PHONE,
    tenant_id="tenant",
    user_id="user",
    managed=True,
    attested=True,
    rooted=False,
    emulator=False,
    public_network=False,
    anonymizer=False,
    impossible_travel=False,
    version="1.0.0",
):
    return registry.register(
        tenant_id=tenant_id,
        user_id=user_id,
        platform=platform,
        form_factor=form_factor,
        app_version=version,
        os_version="test-os",
        managed=managed,
        attested=attested,
        jailbroken_or_rooted=rooted,
        emulator_or_virtualized=emulator,
        biometric_available=True,
        passkey_available=True,
        public_network=public_network,
        anonymizer_detected=anonymizer,
        impossible_travel_signal=impossible_travel,
    )


class SemanticVersionTests(
    unittest.TestCase
):

    def test_version_order(self):
        self.assertLess(
            SemanticVersion.parse(
                "1.2.3"
            ),
            SemanticVersion.parse(
                "1.3.0"
            ),
        )

    def test_release_beats_prerelease(self):
        self.assertGreater(
            SemanticVersion.parse(
                "1.0.0"
            ),
            SemanticVersion.parse(
                "1.0.0-beta.1"
            ),
        )

    def test_invalid_version_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            SemanticVersion.parse(
                "one.two.three"
            )


class PlatformMatrixTests(
    unittest.TestCase
):

    def test_iphone_supported(self):
        registry = (
            ClientPlatformRegistry()
        )

        profile = registry.profile(
            platform=(
                DevicePlatform.IOS
            ),
            form_factor=(
                FormFactor.PHONE
            ),
        )

        self.assertTrue(
            profile.capabilities
            .passkeys
        )

    def test_ipad_supported(self):
        registry = (
            ClientPlatformRegistry()
        )

        profile = registry.profile(
            platform=(
                DevicePlatform.IPADOS
            ),
            form_factor=(
                FormFactor.TABLET
            ),
        )

        self.assertTrue(
            profile.capabilities
            .stylus
        )

    def test_android_phone_supported(self):
        registry = (
            ClientPlatformRegistry()
        )

        profile = registry.profile(
            platform=(
                DevicePlatform.ANDROID
            ),
            form_factor=(
                FormFactor.PHONE
            ),
        )

        self.assertTrue(
            profile.capabilities
            .offline_storage
        )

    def test_android_tablet_supported(self):
        registry = (
            ClientPlatformRegistry()
        )

        registry.profile(
            platform=(
                DevicePlatform.ANDROID
            ),
            form_factor=(
                FormFactor.TABLET
            ),
        )

    def test_macos_supported(self):
        registry = (
            ClientPlatformRegistry()
        )

        registry.profile(
            platform=(
                DevicePlatform.MACOS
            ),
            form_factor=(
                FormFactor.DESKTOP
            ),
        )

    def test_windows_supported(self):
        registry = (
            ClientPlatformRegistry()
        )

        profile = registry.profile(
            platform=(
                DevicePlatform.WINDOWS
            ),
            form_factor=(
                FormFactor.DESKTOP
            ),
        )

        self.assertTrue(
            profile.capabilities
            .desktop_windows
        )

    def test_web_supported(self):
        registry = (
            ClientPlatformRegistry()
        )

        registry.profile(
            platform=(
                DevicePlatform.WEB
            ),
            form_factor=(
                FormFactor.BROWSER
            ),
        )

    def test_wrong_form_factor_rejected(self):
        registry = (
            ClientPlatformRegistry()
        )

        with self.assertRaises(
            UnsupportedClient
        ):
            registry.profile(
                platform=(
                    DevicePlatform.IOS
                ),
                form_factor=(
                    FormFactor.DESKTOP
                ),
            )

    def test_manifest_has_all_required_platforms(self):
        manifest = (
            universal_runtime_manifest()
        )

        expected = {
            DevicePlatform.IOS,
            DevicePlatform.IPADOS,
            DevicePlatform.ANDROID,
            DevicePlatform.MACOS,
            DevicePlatform.WINDOWS,
            DevicePlatform.WEB,
        }

        self.assertEqual(
            set(
                manifest
                .supported_platforms
            ),
            expected,
        )


class DeviceTrustTests(
    unittest.TestCase
):

    def test_clean_device_is_trusted(self):
        registry = DeviceRegistry()

        d = device(
            registry
        )

        result = (
            DeviceTrustEngine()
            .assess(
                d
            )
        )

        self.assertEqual(
            result.trust,
            DeviceTrust.TRUSTED,
        )

    def test_rooted_device_blocked(self):
        registry = DeviceRegistry()

        d = device(
            registry,
            rooted=True,
        )

        result = (
            DeviceTrustEngine()
            .assess(
                d
            )
        )

        self.assertEqual(
            result.trust,
            DeviceTrust.BLOCKED,
        )

    def test_revoked_device_blocked(self):
        registry = DeviceRegistry()

        d = device(
            registry
        )

        d = registry.revoke(
            d.device_id,
            reason="lost device",
        )

        result = (
            DeviceTrustEngine()
            .assess(
                d
            )
        )

        self.assertEqual(
            result.trust,
            DeviceTrust.BLOCKED,
        )

    def test_multiple_risk_signals_degrade(self):
        registry = DeviceRegistry()

        d = device(
            registry,
            managed=False,
            attested=False,
            emulator=True,
            public_network=True,
            anonymizer=True,
        )

        result = (
            DeviceTrustEngine()
            .assess(
                d
            )
        )

        self.assertNotEqual(
            result.trust,
            DeviceTrust.TRUSTED,
        )

    def test_key_epoch_rotates(self):
        registry = DeviceRegistry()

        d = device(
            registry
        )

        rotated = (
            registry
            .rotate_key_epoch(
                d.device_id
            )
        )

        self.assertEqual(
            rotated.key_epoch,
            d.key_epoch + 1,
        )


class CapabilityGateTests(
    unittest.TestCase
):

    def setUp(self):
        self.registry = (
            DeviceRegistry()
        )

        self.device = device(
            self.registry
        )

        self.gate = (
            RuntimeCapabilityGate(
                devices=(
                    self.registry
                )
            )
        )

    def principal(
        self,
        *,
        role="sales",
        surface=(
            ClientSurface.SALES
        ),
        auth=(
            AuthStrength.MFA
        ),
        tenant="tenant",
        user="user",
    ):
        return SessionPrincipal(
            user_id=user,
            tenant_id=tenant,
            role=role,
            surface=surface,
            auth_strength=auth,
            device_id=(
                self.device.device_id
            ),
        )

    def test_sales_can_view_crm(self):
        decision = (
            self.gate.authorize(
                principal=(
                    self.principal()
                ),
                capability=(
                    "crm.view"
                ),
                classification=(
                    DataClassification
                    .CONFIDENTIAL
                ),
                online=True,
            )
        )

        self.assertTrue(
            decision.allowed
        )

    def test_sales_cannot_view_finance(self):
        decision = (
            self.gate.authorize(
                principal=(
                    self.principal()
                ),
                capability=(
                    "finance.view"
                ),
                classification=(
                    DataClassification
                    .FINANCIAL
                ),
                online=True,
            )
        )

        self.assertFalse(
            decision.allowed
        )

    def test_finance_requires_passkey(self):
        decision = (
            self.gate.authorize(
                principal=(
                    self.principal(
                        role="president",
                        surface=(
                            ClientSurface
                            .FINANCE
                        ),
                        auth=(
                            AuthStrength.MFA
                        ),
                    )
                ),
                capability=(
                    "finance.view"
                ),
                classification=(
                    DataClassification
                    .FINANCIAL
                ),
                online=True,
            )
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertTrue(
            decision.step_up_required
        )

    def test_finance_passkey_allowed(self):
        decision = (
            self.gate.authorize(
                principal=(
                    self.principal(
                        role="president",
                        surface=(
                            ClientSurface
                            .FINANCE
                        ),
                        auth=(
                            AuthStrength
                            .PASSKEY
                        ),
                    )
                ),
                capability=(
                    "finance.view"
                ),
                classification=(
                    DataClassification
                    .FINANCIAL
                ),
                online=True,
            )
        )

        self.assertTrue(
            decision.allowed
        )

    def test_finance_offline_denied(self):
        decision = (
            self.gate.authorize(
                principal=(
                    self.principal(
                        role="president",
                        surface=(
                            ClientSurface
                            .FINANCE
                        ),
                        auth=(
                            AuthStrength
                            .PASSKEY
                        ),
                    )
                ),
                capability=(
                    "finance.view"
                ),
                classification=(
                    DataClassification
                    .FINANCIAL
                ),
                online=False,
            )
        )

        self.assertFalse(
            decision.allowed
        )

    def test_finance_requires_managed_device(self):
        registry = DeviceRegistry()

        d = device(
            registry,
            managed=False,
        )

        gate = (
            RuntimeCapabilityGate(
                devices=registry
            )
        )

        principal = SessionPrincipal(
            user_id="user",
            tenant_id="tenant",
            role="president",
            surface=(
                ClientSurface.FINANCE
            ),
            auth_strength=(
                AuthStrength.PASSKEY
            ),
            device_id=d.device_id,
        )

        decision = gate.authorize(
            principal=principal,
            capability="finance.view",
            classification=(
                DataClassification
                .FINANCIAL
            ),
            online=True,
        )

        self.assertFalse(
            decision.allowed
        )

    def test_tenant_mismatch_denied(self):
        decision = (
            self.gate.authorize(
                principal=(
                    self.principal(
                        tenant="other"
                    )
                ),
                capability="crm.view",
                classification=(
                    DataClassification
                    .INTERNAL
                ),
                online=True,
            )
        )

        self.assertFalse(
            decision.allowed
        )

    def test_user_device_mismatch_denied(self):
        decision = (
            self.gate.authorize(
                principal=(
                    self.principal(
                        user="different"
                    )
                ),
                capability="crm.view",
                classification=(
                    DataClassification
                    .INTERNAL
                ),
                online=True,
            )
        )

        self.assertFalse(
            decision.allowed
        )

    def test_estimate_approval_requires_stepup(self):
        principal = (
            self.principal(
                role="senior_estimator",
                surface=(
                    ClientSurface
                    .ESTIMATING
                ),
                auth=(
                    AuthStrength.PASSKEY
                ),
            )
        )

        decision = (
            self.gate.authorize(
                principal=principal,
                capability=(
                    "estimating.approve"
                ),
                classification=(
                    DataClassification
                    .RESTRICTED
                ),
                online=True,
            )
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertTrue(
            decision.step_up_required
        )

    def test_estimate_approval_stepup_allowed(self):
        principal = (
            self.principal(
                role="senior_estimator",
                surface=(
                    ClientSurface
                    .ESTIMATING
                ),
                auth=(
                    AuthStrength.STEP_UP
                ),
            )
        )

        decision = (
            self.gate.authorize(
                principal=principal,
                capability=(
                    "estimating.approve"
                ),
                classification=(
                    DataClassification
                    .RESTRICTED
                ),
                online=True,
            )
        )

        self.assertTrue(
            decision.allowed
        )


class CachePolicyTests(
    unittest.TestCase
):

    def test_confidential_cache_allowed_encrypted(self):
        engine = (
            SecureCachePolicyEngine()
        )

        policy = engine.policy(
            DataClassification
            .CONFIDENTIAL
        )

        self.assertEqual(
            policy.disposition,
            CacheDisposition.ALLOW,
        )

        self.assertTrue(
            policy
            .encryption_required
        )

    def test_restricted_is_memory_only(self):
        engine = (
            SecureCachePolicyEngine()
        )

        policy = engine.policy(
            DataClassification
            .RESTRICTED
        )

        self.assertEqual(
            policy.disposition,
            CacheDisposition
            .MEMORY_ONLY,
        )

    def test_financial_persistence_denied(self):
        engine = (
            SecureCachePolicyEngine()
        )

        self.assertFalse(
            engine
            .can_persist_offline(
                DataClassification
                .FINANCIAL
            )
        )


class OfflineQueueTests(
    unittest.TestCase
):

    def setUp(self):
        self.queue = (
            OfflineMutationQueue(
                max_retries=2
            )
        )

    def enqueue(self):
        return self.queue.enqueue(
            tenant_id="tenant",
            user_id="user",
            device_id="device",
            aggregate_type="lead",
            aggregate_id="lead-1",
            command="update_note",
            base_version=3,
            classification=(
                DataClassification
                .CONFIDENTIAL
            ),
            idempotency_key="key-1",
            payload={
                "note":
                    "customer called"
            },
        )

    def test_enqueue(self):
        mutation = self.enqueue()

        self.assertEqual(
            mutation.state,
            SyncMutationState.PENDING,
        )

    def test_idempotent_enqueue(self):
        first = self.enqueue()
        second = self.enqueue()

        self.assertEqual(
            first.mutation_id,
            second.mutation_id,
        )

    def test_idempotency_payload_change_blocked(self):
        self.enqueue()

        with self.assertRaises(
            SyncQueueError
        ):
            self.queue.enqueue(
                tenant_id="tenant",
                user_id="user",
                device_id="device",
                aggregate_type="lead",
                aggregate_id="lead-1",
                command="update_note",
                base_version=3,
                classification=(
                    DataClassification
                    .CONFIDENTIAL
                ),
                idempotency_key="key-1",
                payload={
                    "note":
                        "different"
                },
            )

    def test_financial_offline_mutation_blocked(self):
        with self.assertRaises(
            SyncQueueError
        ):
            self.queue.enqueue(
                tenant_id="tenant",
                user_id="user",
                device_id="device",
                aggregate_type="ledger",
                aggregate_id="entry-1",
                command="post",
                base_version=0,
                classification=(
                    DataClassification
                    .FINANCIAL
                ),
                idempotency_key="ledger-1",
                payload={
                    "amount":
                        100
                },
            )

    def test_acknowledge(self):
        mutation = self.enqueue()

        result = (
            self.queue.acknowledge(
                mutation.mutation_id,
                server_version=4,
            )
        )

        self.assertEqual(
            result.state,
            SyncMutationState
            .ACKNOWLEDGED,
        )

    def test_conflict(self):
        mutation = self.enqueue()

        result = (
            self.queue.conflict(
                mutation.mutation_id,
                server_version=5,
                reason=(
                    "server changed"
                ),
            )
        )

        self.assertEqual(
            result.state,
            SyncMutationState
            .CONFLICT,
        )

    def test_retry_limit_rejects(self):
        mutation = self.enqueue()

        self.queue.retry(
            mutation.mutation_id
        )

        self.queue.retry(
            mutation.mutation_id
        )

        result = self.queue.retry(
            mutation.mutation_id
        )

        self.assertEqual(
            result.state,
            SyncMutationState
            .REJECTED,
        )

    def test_batch_is_scoped_to_tenant_device(self):
        self.enqueue()

        result = (
            self.queue.next_batch(
                tenant_id="other",
                device_id="device",
            )
        )

        self.assertEqual(
            result,
            (),
        )


class ConflictResolverTests(
    unittest.TestCase
):

    def setUp(self):
        self.resolver = (
            DeterministicConflictResolver()
        )

    def test_disjoint_merge(self):
        result = (
            self.resolver.resolve(
                base_document={
                    "name":
                        "A",
                    "phone":
                        "1",
                },
                client_changes={
                    "phone":
                        "2",
                },
                server_changes={
                    "name":
                        "B",
                },
                policy=(
                    ConflictPolicy
                    .MERGE_DISJOINT
                ),
                classification=(
                    DataClassification
                    .CONFIDENTIAL
                ),
            )
        )

        self.assertEqual(
            result.disposition,
            ConflictDisposition
            .RESOLVED,
        )

        self.assertEqual(
            result
            .merged_document[
                "name"
            ],
            "B",
        )

        self.assertEqual(
            result
            .merged_document[
                "phone"
            ],
            "2",
        )

    def test_same_field_requires_review(self):
        result = (
            self.resolver.resolve(
                base_document={
                    "name":
                        "A",
                },
                client_changes={
                    "name":
                        "B",
                },
                server_changes={
                    "name":
                        "C",
                },
                policy=(
                    ConflictPolicy
                    .MERGE_DISJOINT
                ),
                classification=(
                    DataClassification
                    .CONFIDENTIAL
                ),
            )
        )

        self.assertEqual(
            result.disposition,
            ConflictDisposition
            .MANUAL_REVIEW,
        )

    def test_client_wins_restricted_forces_review(self):
        result = (
            self.resolver.resolve(
                base_document={},
                client_changes={
                    "amount":
                        10,
                },
                server_changes={
                    "amount":
                        20,
                },
                policy=(
                    ConflictPolicy
                    .CLIENT_WINS
                ),
                classification=(
                    DataClassification
                    .RESTRICTED
                ),
            )
        )

        self.assertEqual(
            result.disposition,
            ConflictDisposition
            .MANUAL_REVIEW,
        )

    def test_server_wins(self):
        result = (
            self.resolver.resolve(
                base_document={
                    "x":
                        1,
                },
                client_changes={
                    "x":
                        2,
                },
                server_changes={
                    "x":
                        3,
                },
                policy=(
                    ConflictPolicy
                    .SERVER_WINS
                ),
                classification=(
                    DataClassification
                    .CONFIDENTIAL
                ),
            )
        )

        self.assertEqual(
            result
            .merged_document[
                "x"
            ],
            3,
        )


class ApiVersionTests(
    unittest.TestCase
):

    def test_highest_common_version(self):
        versions = (
            ApiVersionRegistry(
                (
                    "2026-07-01",
                    "2026-08-01",
                )
            )
        )

        result = versions.negotiate(
            (
                "2026-06-01",
                "2026-08-01",
            )
        )

        self.assertEqual(
            result,
            "2026-08-01",
        )

    def test_no_common_version_fails(self):
        versions = (
            ApiVersionRegistry(
                (
                    "2026-08-01",
                )
            )
        )

        with self.assertRaises(
            ApiVersionError
        ):
            versions.negotiate(
                (
                    "2025-01-01",
                )
            )


class ReplayProtectionTests(
    unittest.TestCase
):

    def test_nonce_can_be_used_once(self):
        protector = (
            ReplayProtector()
        )

        nonce = (
            protector.new_nonce()
        )

        protector.accept(
            nonce=nonce,
            timestamp=fixed_now(),
            as_of=fixed_now(),
        )

        with self.assertRaises(
            ReplayDetected
        ):
            protector.accept(
                nonce=nonce,
                timestamp=fixed_now(),
                as_of=fixed_now(),
            )

    def test_old_timestamp_rejected(self):
        protector = (
            ReplayProtector(
                ttl_seconds=300
            )
        )

        with self.assertRaises(
            ReplayDetected
        ):
            protector.accept(
                nonce="abc",
                timestamp=(
                    fixed_now()
                    - timedelta(
                        hours=1
                    )
                ),
                as_of=(
                    fixed_now()
                ),
            )


class ApiBoundaryTests(
    unittest.TestCase
):

    def setUp(self):
        self.devices = (
            DeviceRegistry()
        )

        self.device = device(
            self.devices
        )

        self.replay = (
            ReplayProtector()
        )

        self.boundary = (
            ApiBoundary(
                versions=(
                    ApiVersionRegistry(
                        (
                            "2026-08-01",
                        )
                    )
                ),
                replay=(
                    self.replay
                ),
                devices=(
                    self.devices
                ),
            )
        )

    def test_valid_request(self):
        payload = {
            "hello":
                "world"
        }

        envelope = (
            self.boundary
            .build_envelope(
                api_version=(
                    "2026-08-01"
                ),
                tenant_id="tenant",
                user_id="user",
                device_id=(
                    self.device
                    .device_id
                ),
                payload=payload,
                timestamp=(
                    fixed_now()
                ),
            )
        )

        result = (
            self.boundary
            .validate(
                envelope=envelope,
                payload=payload,
                as_of=fixed_now(),
            )
        )

        self.assertTrue(
            result.accepted
        )

    def test_payload_tamper_rejected(self):
        payload = {
            "hello":
                "world"
        }

        envelope = (
            self.boundary
            .build_envelope(
                api_version=(
                    "2026-08-01"
                ),
                tenant_id="tenant",
                user_id="user",
                device_id=(
                    self.device
                    .device_id
                ),
                payload=payload,
                timestamp=(
                    fixed_now()
                ),
            )
        )

        result = (
            self.boundary
            .validate(
                envelope=envelope,
                payload={
                    "hello":
                        "tampered"
                },
                as_of=fixed_now(),
            )
        )

        self.assertFalse(
            result.accepted
        )

    def test_replayed_request_rejected(self):
        payload = {
            "x":
                1
        }

        envelope = (
            self.boundary
            .build_envelope(
                api_version=(
                    "2026-08-01"
                ),
                tenant_id="tenant",
                user_id="user",
                device_id=(
                    self.device
                    .device_id
                ),
                payload=payload,
                timestamp=(
                    fixed_now()
                ),
            )
        )

        first = (
            self.boundary
            .validate(
                envelope=envelope,
                payload=payload,
                as_of=fixed_now(),
            )
        )

        second = (
            self.boundary
            .validate(
                envelope=envelope,
                payload=payload,
                as_of=fixed_now(),
            )
        )

        self.assertTrue(
            first.accepted
        )

        self.assertFalse(
            second.accepted
        )

    def test_revoked_device_request_rejected(self):
        payload = {
            "x":
                1
        }

        envelope = (
            self.boundary
            .build_envelope(
                api_version=(
                    "2026-08-01"
                ),
                tenant_id="tenant",
                user_id="user",
                device_id=(
                    self.device
                    .device_id
                ),
                payload=payload,
                timestamp=(
                    fixed_now()
                ),
            )
        )

        self.devices.revoke(
            self.device.device_id,
            reason="lost",
        )

        result = (
            self.boundary
            .validate(
                envelope=envelope,
                payload=payload,
                as_of=fixed_now(),
            )
        )

        self.assertFalse(
            result.accepted
        )


class PushPrivacyTests(
    unittest.TestCase
):

    def test_public_message_can_show(self):
        result = (
            PushPrivacyPolicy()
            .present(
                PushMessage(
                    title="GOAT",
                    body="Bid reminder",
                    classification=(
                        DataClassification.PUBLIC
                    ),
                ),
                device_locked=True,
            )
        )

        self.assertEqual(
            result.visibility,
            NotificationVisibility
            .FULL,
        )

    def test_confidential_locked_is_generic(self):
        result = (
            PushPrivacyPolicy()
            .present(
                PushMessage(
                    title="Private",
                    body="Confidential project",
                    classification=(
                        DataClassification
                        .CONFIDENTIAL
                    ),
                ),
                device_locked=True,
            )
        )

        self.assertEqual(
            result.visibility,
            NotificationVisibility
            .GENERIC,
        )

        self.assertNotIn(
            "Confidential project",
            result.body,
        )

    def test_financial_notification_hidden(self):
        result = (
            PushPrivacyPolicy()
            .present(
                PushMessage(
                    title="Cash",
                    body="$500000",
                    classification=(
                        DataClassification
                        .FINANCIAL
                    ),
                ),
                device_locked=False,
            )
        )

        self.assertEqual(
            result.visibility,
            NotificationVisibility
            .HIDDEN,
        )

        self.assertNotIn(
            "$500000",
            result.body,
        )


class AuditTests(
    unittest.TestCase
):

    def test_audit_chain_verifies(self):
        log = RuntimeAuditLog()

        log.append(
            tenant_id="tenant",
            actor_id="user",
            device_id="device",
            action="login",
            payload={
                "success":
                    True
            },
        )

        log.append(
            tenant_id="tenant",
            actor_id="user",
            device_id="device",
            action="crm.view",
            payload={
                "lead":
                    "lead-1"
            },
        )

        self.assertTrue(
            log.verify()
        )

    def test_audit_tamper_detected(self):
        log = RuntimeAuditLog()

        log.append(
            tenant_id="tenant",
            actor_id="user",
            device_id="device",
            action="login",
            payload={},
        )

        log._records[0] = replace(
            log._records[0],
            event_hash=(
                "0" * 64
            ),
        )

        with self.assertRaises(
            AuditIntegrityError
        ):
            log.verify()


class RuntimeManifestTests(
    unittest.TestCase
):

    def test_finance_offline_disabled(self):
        manifest = (
            universal_runtime_manifest()
        )

        self.assertFalse(
            manifest
            .finance_offline_allowed
        )

    def test_restricted_offline_mutations_disabled(self):
        manifest = (
            universal_runtime_manifest()
        )

        self.assertFalse(
            manifest
            .restricted_offline_mutations_allowed
        )

    def test_required_security_capabilities_enabled(self):
        manifest = (
            universal_runtime_manifest()
        )

        self.assertTrue(
            manifest
            .supports_passkeys
        )

        self.assertTrue(
            manifest
            .supports_replay_protection
        )

        self.assertTrue(
            manifest
            .supports_device_attestation
        )

        self.assertTrue(
            manifest
            .supports_tenant_isolation
        )


if __name__ == "__main__":
    unittest.main()
