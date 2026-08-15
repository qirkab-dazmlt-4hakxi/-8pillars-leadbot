import tempfile
import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from pathlib import Path

from leadbot_v2.goat.infrastructure.control_plane import (
    CircuitBreaker,
    CircuitOpen,
    CircuitState,
    FeatureContext,
    FeatureFlag,
    FeatureFlagEngine,
    HandlerSpec,
    MutationCommit,
    RateLimitExceeded,
    ServiceGateway,
    TelemetryRegistry,
    FixedWindowRateLimiter,
    service_request,
)

from leadbot_v2.goat.infrastructure.jobs import (
    DurableJobQueue,
    JobIdempotencyConflict,
    JobIntegrityError,
    JobLeaseError,
    JobState,
)

from leadbot_v2.goat.infrastructure.vault import (
    LocalDocumentVault,
    VaultIntegrityError,
    VaultLegalHoldError,
    VaultPolicyError,
    VaultState,
)

from leadbot_v2.goat.persistence.durable import (
    DurableStore,
    PendingEvent,
)

from leadbot_v2.goat.platform.runtime import (
    AuthStrength,
    ClientSurface,
    DataClassification,
    DevicePlatform,
    DeviceRegistry,
    FormFactor,
    RuntimeCapabilityGate,
    SessionPrincipal,
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


# ============================================================
# VAULT
# ============================================================


class VaultTests(
    unittest.TestCase
):

    def setUp(self):
        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.vault = (
            LocalDocumentVault(
                Path(
                    self.temp.name
                )
                / "vault"
            )
        )

    def tearDown(self):
        self.vault.close()
        self.temp.cleanup()

    def put(
        self,
        *,
        tenant="tenant",
        logical="plans/current",
        data=b"GOAT PLAN",
        classification=(
            DataClassification
            .CONFIDENTIAL
        ),
    ):
        return self.vault.put(
            tenant_id=tenant,
            logical_name=logical,
            original_filename="plans.pdf",
            data=data,
            mime_type="application/pdf",
            classification=(
                classification
            ),
            created_by="estimator",
            storage_encryption_confirmed=(
                classification
                >= DataClassification
                .RESTRICTED
            ),
        )

    def test_round_trip(self):
        obj = self.put()

        result = self.vault.get_bytes(
            tenant_id="tenant",
            object_id=obj.object_id,
        )

        self.assertEqual(
            result,
            b"GOAT PLAN",
        )

    def test_integrity_verification(self):
        obj = self.put()

        result = self.vault.verify(
            tenant_id="tenant",
            object_id=obj.object_id,
        )

        self.assertTrue(
            result.valid
        )

    def test_version_history(self):
        first = self.put(
            data=b"REV 1"
        )

        second = self.put(
            data=b"REV 2"
        )

        self.assertEqual(
            first.version,
            1,
        )

        self.assertEqual(
            second.version,
            2,
        )

        versions = (
            self.vault.versions(
                tenant_id="tenant",
                logical_name=(
                    "plans/current"
                ),
            )
        )

        self.assertEqual(
            len(versions),
            2,
        )

    def test_latest(self):
        self.put(
            data=b"A"
        )

        second = self.put(
            data=b"B"
        )

        latest = self.vault.latest(
            tenant_id="tenant",
            logical_name="plans/current",
        )

        self.assertEqual(
            latest.object_id,
            second.object_id,
        )

    def test_tenant_isolation(self):
        obj = self.put(
            tenant="tenant-a"
        )

        with self.assertRaises(
            Exception
        ):
            self.vault.get_bytes(
                tenant_id="tenant-b",
                object_id=obj.object_id,
            )

    def test_quarantine_blocks_read(self):
        obj = self.vault.put(
            tenant_id="tenant",
            logical_name="upload",
            original_filename="x.pdf",
            data=b"unsafe",
            mime_type="application/pdf",
            classification=(
                DataClassification
                .CONFIDENTIAL
            ),
            created_by="user",
            scanner=lambda _: False,
        )

        self.assertEqual(
            obj.state,
            VaultState.QUARANTINED,
        )

        with self.assertRaises(
            VaultPolicyError
        ):
            self.vault.get_bytes(
                tenant_id="tenant",
                object_id=obj.object_id,
            )

    def test_restricted_requires_encryption_confirmation(self):
        with self.assertRaises(
            VaultPolicyError
        ):
            self.vault.put(
                tenant_id="tenant",
                logical_name="restricted",
                original_filename="x.pdf",
                data=b"data",
                mime_type="application/pdf",
                classification=(
                    DataClassification
                    .RESTRICTED
                ),
                created_by="user",
                storage_encryption_confirmed=False,
            )

    def test_legal_hold_blocks_delete(self):
        obj = self.put()

        self.vault.set_legal_hold(
            tenant_id="tenant",
            object_id=obj.object_id,
            enabled=True,
        )

        with self.assertRaises(
            VaultLegalHoldError
        ):
            self.vault.delete(
                tenant_id="tenant",
                object_id=obj.object_id,
            )

    def test_logical_delete(self):
        obj = self.put()

        deleted = self.vault.delete(
            tenant_id="tenant",
            object_id=obj.object_id,
        )

        self.assertEqual(
            deleted.state,
            VaultState.DELETED,
        )

    def test_blob_tamper_detected(self):
        obj = self.put()

        path = self.vault._blob_path(
            tenant_id="tenant",
            content_hash=(
                obj.content_hash
            ),
        )

        path.write_bytes(
            b"TAMPERED"
        )

        with self.assertRaises(
            VaultIntegrityError
        ):
            self.vault.get_bytes(
                tenant_id="tenant",
                object_id=obj.object_id,
            )


# ============================================================
# JOB QUEUE
# ============================================================


class JobQueueTests(
    unittest.TestCase
):

    def setUp(self):
        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.queue = (
            DurableJobQueue(
                Path(
                    self.temp.name
                )
                / "jobs.db"
            )
        )

    def tearDown(self):
        self.queue.close()
        self.temp.cleanup()

    def enqueue(
        self,
        *,
        key="job-key",
        max_attempts=3,
        priority=0,
        available_at=None,
    ):
        return self.queue.enqueue(
            tenant_id="tenant",
            queue="plans",
            task_type="analyze_pdf",
            idempotency_key=key,
            payload={
                "document_id":
                    "doc-1"
            },
            max_attempts=max_attempts,
            priority=priority,
            available_at=(
                available_at
            ),
        )

    def test_enqueue(self):
        job = self.enqueue()

        self.assertEqual(
            job.state,
            JobState.PENDING,
        )

    def test_enqueue_idempotent(self):
        first = self.enqueue()
        second = self.enqueue()

        self.assertEqual(
            first.job_id,
            second.job_id,
        )

    def test_idempotency_conflict(self):
        self.enqueue()

        with self.assertRaises(
            JobIdempotencyConflict
        ):
            self.queue.enqueue(
                tenant_id="tenant",
                queue="plans",
                task_type="other_task",
                idempotency_key="job-key",
                payload={"x": 1},
            )

    def test_claim(self):
        self.enqueue()

        claimed = self.queue.claim(
            queue="plans",
            worker_id="worker-1",
        )

        self.assertEqual(
            len(claimed),
            1,
        )

        self.assertEqual(
            claimed[0].state,
            JobState.RUNNING,
        )

    def test_priority(self):
        low = self.enqueue(
            key="low",
            priority=1,
        )

        high = self.enqueue(
            key="high",
            priority=100,
        )

        claimed = self.queue.claim(
            queue="plans",
            worker_id="worker",
            limit=1,
        )

        self.assertEqual(
            claimed[0].job_id,
            high.job_id,
        )

    def test_future_job_not_claimed(self):
        self.enqueue(
            available_at=(
                fixed_now()
                + timedelta(
                    hours=10
                )
            )
        )

        claimed = self.queue.claim(
            queue="plans",
            worker_id="worker",
            as_of=fixed_now(),
        )

        self.assertEqual(
            claimed,
            (),
        )

    def test_second_worker_cannot_claim(self):
        self.enqueue()

        first = self.queue.claim(
            queue="plans",
            worker_id="worker-a",
        )

        second = self.queue.claim(
            queue="plans",
            worker_id="worker-b",
        )

        self.assertEqual(
            len(first),
            1,
        )

        self.assertEqual(
            second,
            (),
        )

    def test_heartbeat(self):
        self.enqueue()

        job = self.queue.claim(
            queue="plans",
            worker_id="worker",
        )[0]

        updated = self.queue.heartbeat(
            job_id=job.job_id,
            worker_id="worker",
        )

        self.assertGreater(
            updated.lease_until,
            job.lease_until,
        )

    def test_wrong_worker_cannot_complete(self):
        self.enqueue()

        job = self.queue.claim(
            queue="plans",
            worker_id="worker-a",
        )[0]

        with self.assertRaises(
            JobLeaseError
        ):
            self.queue.succeed(
                job_id=job.job_id,
                worker_id="worker-b",
            )

    def test_success(self):
        self.enqueue()

        job = self.queue.claim(
            queue="plans",
            worker_id="worker",
        )[0]

        result = self.queue.succeed(
            job_id=job.job_id,
            worker_id="worker",
        )

        self.assertEqual(
            result.state,
            JobState.SUCCEEDED,
        )

    def test_retry(self):
        self.enqueue()

        job = self.queue.claim(
            queue="plans",
            worker_id="worker",
        )[0]

        result = self.queue.fail(
            job_id=job.job_id,
            worker_id="worker",
            error="temporary",
            retry_delay_seconds=0,
        )

        self.assertEqual(
            result.state,
            JobState.RETRY,
        )

    def test_dead_letter(self):
        self.enqueue(
            max_attempts=1
        )

        job = self.queue.claim(
            queue="plans",
            worker_id="worker",
        )[0]

        result = self.queue.fail(
            job_id=job.job_id,
            worker_id="worker",
            error="permanent",
            retry_delay_seconds=0,
        )

        self.assertEqual(
            result.state,
            JobState.DEAD,
        )

    def test_stats(self):
        self.enqueue(
            key="a"
        )

        self.enqueue(
            key="b"
        )

        stats = self.queue.stats(
            queue="plans"
        )

        self.assertEqual(
            stats.pending,
            2,
        )

    def test_payload_tamper_detected(self):
        job = self.enqueue()

        self.queue._conn.execute(
            """
            UPDATE goat_jobs
            SET payload_json =
                '{"document_id":"evil"}'
            WHERE job_id = ?
            """,
            (
                job.job_id,
            ),
        )

        with self.assertRaises(
            JobIntegrityError
        ):
            self.queue.get(
                job.job_id
            )


# ============================================================
# CIRCUIT BREAKER
# ============================================================


class CircuitBreakerTests(
    unittest.TestCase
):

    def test_opens_after_threshold(self):
        breaker = CircuitBreaker(
            "test",
            failure_threshold=2,
            recovery_seconds=30,
        )

        breaker.failure(
            as_of=fixed_now()
        )

        breaker.failure(
            as_of=fixed_now()
        )

        self.assertEqual(
            breaker.snapshot().state,
            CircuitState.OPEN,
        )

    def test_open_rejects_call(self):
        breaker = CircuitBreaker(
            "test",
            failure_threshold=1,
            recovery_seconds=30,
        )

        breaker.failure(
            as_of=fixed_now()
        )

        with self.assertRaises(
            CircuitOpen
        ):
            breaker.before_call(
                as_of=(
                    fixed_now()
                    + timedelta(
                        seconds=10
                    )
                )
            )

    def test_half_open_after_timeout(self):
        breaker = CircuitBreaker(
            "test",
            failure_threshold=1,
            recovery_seconds=30,
        )

        breaker.failure(
            as_of=fixed_now()
        )

        breaker.before_call(
            as_of=(
                fixed_now()
                + timedelta(
                    seconds=31
                )
            )
        )

        self.assertEqual(
            breaker.snapshot().state,
            CircuitState.HALF_OPEN,
        )

    def test_success_closes(self):
        breaker = CircuitBreaker(
            "test",
            failure_threshold=1,
            recovery_seconds=1,
        )

        breaker.failure(
            as_of=fixed_now()
        )

        breaker.before_call(
            as_of=(
                fixed_now()
                + timedelta(
                    seconds=2
                )
            )
        )

        breaker.success()

        self.assertEqual(
            breaker.snapshot().state,
            CircuitState.CLOSED,
        )


# ============================================================
# FEATURE FLAGS
# ============================================================


class FeatureFlagTests(
    unittest.TestCase
):

    def context(
        self,
        *,
        tenant="tenant",
        role="sales",
        platform=DevicePlatform.IOS,
    ):
        return FeatureContext(
            tenant_id=tenant,
            user_id="user",
            role=role,
            device_id="device",
            platform=platform,
        )

    def test_enabled(self):
        engine = FeatureFlagEngine()

        engine.set_flag(
            FeatureFlag(
                name="new-ui"
            )
        )

        result = engine.evaluate(
            name="new-ui",
            context=self.context(),
        )

        self.assertTrue(
            result.enabled
        )

    def test_kill_switch(self):
        engine = FeatureFlagEngine()

        engine.set_flag(
            FeatureFlag(
                name="payments",
                kill_switch=True,
            )
        )

        result = engine.evaluate(
            name="payments",
            context=self.context(),
        )

        self.assertFalse(
            result.enabled
        )

    def test_role_gate(self):
        engine = FeatureFlagEngine()

        engine.set_flag(
            FeatureFlag(
                name="executive",
                allowed_roles=(
                    frozenset(
                        {
                            "president"
                        }
                    )
                ),
            )
        )

        result = engine.evaluate(
            name="executive",
            context=self.context(
                role="sales"
            ),
        )

        self.assertFalse(
            result.enabled
        )

    def test_platform_gate(self):
        engine = FeatureFlagEngine()

        engine.set_flag(
            FeatureFlag(
                name="ipad-feature",
                allowed_platforms=(
                    frozenset(
                        {
                            DevicePlatform
                            .IPADOS
                        }
                    )
                ),
            )
        )

        result = engine.evaluate(
            name="ipad-feature",
            context=self.context(
                platform=(
                    DevicePlatform.IOS
                )
            ),
        )

        self.assertFalse(
            result.enabled
        )

    def test_bucket_is_deterministic(self):
        engine = FeatureFlagEngine()

        engine.set_flag(
            FeatureFlag(
                name="rollout",
                rollout_percent=50,
            )
        )

        first = engine.evaluate(
            name="rollout",
            context=self.context(),
        )

        second = engine.evaluate(
            name="rollout",
            context=self.context(),
        )

        self.assertEqual(
            first.bucket,
            second.bucket,
        )


# ============================================================
# RATE LIMIT
# ============================================================


class RateLimiterTests(
    unittest.TestCase
):

    def test_limit(self):
        limiter = (
            FixedWindowRateLimiter()
        )

        limiter.require(
            key="x",
            limit=2,
            window_seconds=60,
            as_of=fixed_now(),
        )

        limiter.require(
            key="x",
            limit=2,
            window_seconds=60,
            as_of=fixed_now(),
        )

        with self.assertRaises(
            RateLimitExceeded
        ):
            limiter.require(
                key="x",
                limit=2,
                window_seconds=60,
                as_of=fixed_now(),
            )


# ============================================================
# TELEMETRY
# ============================================================


class TelemetryTests(
    unittest.TestCase
):

    def test_metrics(self):
        telemetry = (
            TelemetryRegistry()
        )

        telemetry.record(
            operation="crm.view",
            success=True,
            latency_ms=10,
        )

        telemetry.record(
            operation="crm.view",
            success=False,
            latency_ms=20,
        )

        result = telemetry.operation(
            "crm.view"
        )

        self.assertEqual(
            result.request_count,
            2,
        )

        self.assertEqual(
            result.error_count,
            1,
        )

    def test_slo(self):
        telemetry = (
            TelemetryRegistry()
        )

        for _ in range(100):
            telemetry.record(
                operation="api",
                success=True,
                latency_ms=50,
            )

        assessment = (
            telemetry.assess_slo(
                operation="api",
                success_target=0.99,
                latency_target_p95_ms=100,
            )
        )

        self.assertTrue(
            assessment.healthy
        )


# ============================================================
# SERVICE GATEWAY
# ============================================================


class ServiceGatewayTests(
    unittest.TestCase
):

    def setUp(self):
        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.store = DurableStore(
            Path(
                self.temp.name
            )
            / "data.db"
        )

        self.devices = (
            DeviceRegistry()
        )

        self.device = (
            self.devices.register(
                tenant_id="tenant",
                user_id="user",
                platform=(
                    DevicePlatform.IOS
                ),
                form_factor=(
                    FormFactor.PHONE
                ),
                app_version="1.0.0",
                os_version="test",
                managed=True,
                attested=True,
                biometric_available=True,
                passkey_available=True,
            )
        )

        self.gate = (
            RuntimeCapabilityGate(
                devices=(
                    self.devices
                )
            )
        )

        self.telemetry = (
            TelemetryRegistry()
        )

        self.flags = (
            FeatureFlagEngine()
        )

        self.flags.set_flag(
            FeatureFlag(
                name="crm-v2"
            )
        )

        self.gateway = (
            ServiceGateway(
                store=self.store,
                capability_gate=(
                    self.gate
                ),
                telemetry=(
                    self.telemetry
                ),
                feature_flags=(
                    self.flags
                ),
            )
        )

        def mutate(
            request,
            principal,
        ):
            return MutationCommit(
                stream_id="lead-1",
                expected_version=(
                    self.store
                    .current_version(
                        tenant_id=(
                            request
                            .tenant_id
                        ),
                        stream_id="lead-1",
                    )
                ),
                events=(
                    PendingEvent(
                        event_type=(
                            "lead.note_updated"
                        ),
                        payload={
                            "note":
                                request
                                .payload[
                                    "note"
                                ]
                        },
                        topic="crm.events",
                    ),
                ),
                response={
                    "lead_id":
                        "lead-1",
                    "saved":
                        True,
                },
            )

        def query(
            request,
            principal,
        ):
            return {
                "lead_id":
                    "lead-1",
                "name":
                    "Customer",
            }

        self.gateway.register(
            HandlerSpec(
                operation=(
                    "crm.note.update"
                ),
                capability=(
                    "crm.mutate"
                ),
                classification=(
                    DataClassification
                    .CONFIDENTIAL
                ),
                mutation=True,
                rate_limit=100,
                rate_window_seconds=60,
                circuit_name="crm",
                feature_flag="crm-v2",
                handler=mutate,
            )
        )

        self.gateway.register(
            HandlerSpec(
                operation="crm.lead.get",
                capability="crm.view",
                classification=(
                    DataClassification
                    .CONFIDENTIAL
                ),
                mutation=False,
                rate_limit=100,
                rate_window_seconds=60,
                circuit_name="crm",
                feature_flag=None,
                handler=query,
            )
        )

        self.principal = (
            SessionPrincipal(
                user_id="user",
                tenant_id="tenant",
                role="sales",
                surface=(
                    ClientSurface.SALES
                ),
                auth_strength=(
                    AuthStrength.MFA
                ),
                device_id=(
                    self.device
                    .device_id
                ),
            )
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_query(self):
        response = (
            self.gateway.execute(
                request=(
                    service_request(
                        tenant_id="tenant",
                        user_id="user",
                        operation=(
                            "crm.lead.get"
                        ),
                        payload={},
                    )
                ),
                principal=(
                    self.principal
                ),
                platform=(
                    DevicePlatform.IOS
                ),
            )
        )

        self.assertTrue(
            response.data[
                "lead_id"
            ]
        )

    def test_mutation_commits_event(self):
        response = (
            self.gateway.execute(
                request=(
                    service_request(
                        tenant_id="tenant",
                        user_id="user",
                        operation=(
                            "crm.note.update"
                        ),
                        payload={
                            "note":
                                "Called customer"
                        },
                        idempotency_key=(
                            "request-1"
                        ),
                    )
                ),
                principal=(
                    self.principal
                ),
                platform=(
                    DevicePlatform.IOS
                ),
            )
        )

        self.assertTrue(
            response.data[
                "saved"
            ]
        )

        events = (
            self.store.read_stream(
                tenant_id="tenant",
                stream_id="lead-1",
            )
        )

        self.assertEqual(
            len(events),
            1,
        )

    def test_mutation_creates_outbox(self):
        self.gateway.execute(
            request=(
                service_request(
                    tenant_id="tenant",
                    user_id="user",
                    operation=(
                        "crm.note.update"
                    ),
                    payload={
                        "note":
                            "Called"
                    },
                    idempotency_key=(
                        "request-2"
                    ),
                )
            ),
            principal=(
                self.principal
            ),
            platform=(
                DevicePlatform.IOS
            ),
        )

        health = (
            self.store.health()
        )

        self.assertEqual(
            health
            .pending_outbox_count,
            1,
        )

    def test_mutation_replay_is_cached(self):
        request = service_request(
            tenant_id="tenant",
            user_id="user",
            operation=(
                "crm.note.update"
            ),
            payload={
                "note":
                    "Same"
            },
            idempotency_key="same-key",
        )

        first = self.gateway.execute(
            request=request,
            principal=(
                self.principal
            ),
            platform=(
                DevicePlatform.IOS
            ),
        )

        second = (
            self.gateway.execute(
                request=request,
                principal=(
                    self.principal
                ),
                platform=(
                    DevicePlatform.IOS
                ),
            )
        )

        self.assertFalse(
            first.cached
        )

        self.assertTrue(
            second.cached
        )

        events = (
            self.store.read_stream(
                tenant_id="tenant",
                stream_id="lead-1",
            )
        )

        self.assertEqual(
            len(events),
            1,
        )

    def test_telemetry_recorded(self):
        self.gateway.execute(
            request=(
                service_request(
                    tenant_id="tenant",
                    user_id="user",
                    operation=(
                        "crm.lead.get"
                    ),
                    payload={},
                )
            ),
            principal=(
                self.principal
            ),
            platform=(
                DevicePlatform.IOS
            ),
        )

        metrics = (
            self.telemetry
            .operation(
                "crm.lead.get"
            )
        )

        self.assertEqual(
            metrics.request_count,
            1,
        )

        self.assertEqual(
            metrics.success_count,
            1,
        )

    def test_tenant_mismatch_blocked(self):
        request = service_request(
            tenant_id="wrong",
            user_id="user",
            operation="crm.lead.get",
            payload={},
        )

        with self.assertRaises(
            Exception
        ):
            self.gateway.execute(
                request=request,
                principal=(
                    self.principal
                ),
                platform=(
                    DevicePlatform.IOS
                ),
            )

    def test_user_mismatch_blocked(self):
        request = service_request(
            tenant_id="tenant",
            user_id="wrong",
            operation="crm.lead.get",
            payload={},
        )

        with self.assertRaises(
            Exception
        ):
            self.gateway.execute(
                request=request,
                principal=(
                    self.principal
                ),
                platform=(
                    DevicePlatform.IOS
                ),
            )

    def test_missing_idempotency_key_blocked(self):
        request = service_request(
            tenant_id="tenant",
            user_id="user",
            operation=(
                "crm.note.update"
            ),
            payload={
                "note":
                    "x"
            },
        )

        with self.assertRaises(
            Exception
        ):
            self.gateway.execute(
                request=request,
                principal=(
                    self.principal
                ),
                platform=(
                    DevicePlatform.IOS
                ),
            )

    def test_feature_kill_switch_blocks(self):
        self.flags.set_flag(
            FeatureFlag(
                name="crm-v2",
                kill_switch=True,
            )
        )

        request = service_request(
            tenant_id="tenant",
            user_id="user",
            operation=(
                "crm.note.update"
            ),
            payload={
                "note":
                    "x"
            },
            idempotency_key="kill",
        )

        with self.assertRaises(
            Exception
        ):
            self.gateway.execute(
                request=request,
                principal=(
                    self.principal
                ),
                platform=(
                    DevicePlatform.IOS
                ),
            )


if __name__ == "__main__":
    unittest.main()
