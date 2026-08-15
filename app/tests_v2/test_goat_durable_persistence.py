import os
import sqlite3
import tempfile
import unittest

from pathlib import Path

from leadbot_v2.goat.persistence.durable import (
    BackupIntegrityError,
    DurableStore,
    IdempotencyConflict,
    InboxConflict,
    MigrationDriftError,
    OptimisticConcurrencyError,
    OutboxLeaseError,
    OutboxState,
    PendingEvent,
    PersistenceIntegrityError,
    SnapshotIntegrityError,
)


class DurableStoreTestCase(
    unittest.TestCase
):

    def setUp(self):
        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.db_path = (
            Path(
                self.temp.name
            )
            / "goat.db"
        )

        self.store = DurableStore(
            self.db_path
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def append_one(
        self,
        *,
        tenant="tenant",
        stream="project-1",
        expected=0,
        payload=None,
    ):
        return self.store.append(
            tenant_id=tenant,
            stream_id=stream,
            expected_version=expected,
            event_type="project.created",
            payload=(
                payload
                or {
                    "name":
                        "Project"
                }
            ),
            topic="project.events",
            actor_id="user",
            device_id="device",
        )


class MigrationTests(
    DurableStoreTestCase
):

    def test_initialize_is_idempotent(self):
        self.store.initialize()
        self.store.initialize()

        self.assertTrue(
            self.store.migrations()
        )

    def test_migration_drift_detected(self):
        self.store._conn.execute(
            """
            UPDATE goat_migrations
            SET checksum = 'tampered'
            """
        )

        with self.assertRaises(
            MigrationDriftError
        ):
            self.store.initialize()


class EventStoreTests(
    DurableStoreTestCase
):

    def test_append_event(self):
        event = self.append_one()

        self.assertEqual(
            event.version,
            1,
        )

        self.assertEqual(
            self.store.current_version(
                tenant_id="tenant",
                stream_id="project-1",
            ),
            1,
        )

    def test_batch_append_versions(self):
        events = self.store.append_many(
            tenant_id="tenant",
            stream_id="estimate-1",
            expected_version=0,
            events=(
                PendingEvent(
                    event_type="created",
                    payload={"x": 1},
                    topic="estimate.events",
                ),
                PendingEvent(
                    event_type="line.added",
                    payload={"x": 2},
                    topic="estimate.events",
                ),
                PendingEvent(
                    event_type="approved",
                    payload={"x": 3},
                    topic="estimate.events",
                ),
            ),
            actor_id="estimator",
        )

        self.assertEqual(
            tuple(
                event.version
                for event
                in events
            ),
            (
                1,
                2,
                3,
            ),
        )

    def test_optimistic_concurrency(self):
        self.append_one()

        with self.assertRaises(
            OptimisticConcurrencyError
        ):
            self.append_one(
                expected=0
            )

    def test_correct_next_version(self):
        self.append_one()

        second = self.append_one(
            expected=1,
            payload={
                "name":
                    "Updated"
            },
        )

        self.assertEqual(
            second.version,
            2,
        )

    def test_tenant_isolation(self):
        self.append_one(
            tenant="tenant-a"
        )

        self.append_one(
            tenant="tenant-b"
        )

        a = self.store.read_stream(
            tenant_id="tenant-a",
            stream_id="project-1",
        )

        b = self.store.read_stream(
            tenant_id="tenant-b",
            stream_id="project-1",
        )

        self.assertEqual(
            len(a),
            1,
        )

        self.assertEqual(
            len(b),
            1,
        )

        self.assertEqual(
            a[0].tenant_id,
            "tenant-a",
        )

    def test_event_integrity_tamper_detected(self):
        self.append_one()

        self.store._conn.execute(
            """
            UPDATE goat_events
            SET payload_json =
                '{"name":"tampered"}'
            """
        )

        with self.assertRaises(
            PersistenceIntegrityError
        ):
            self.store.read_stream(
                tenant_id="tenant",
                stream_id="project-1",
            )

    def test_event_and_outbox_are_atomic(self):
        event = self.append_one()

        row = self.store._conn.execute(
            """
            SELECT event_id
            FROM goat_outbox
            WHERE event_id = ?
            """,
            (
                event.event_id,
            ),
        ).fetchone()

        self.assertIsNotNone(
            row
        )


class IdempotencyTests(
    DurableStoreTestCase
):

    def test_new_idempotency_key(self):
        result = (
            self.store
            .begin_idempotent(
                tenant_id="tenant",
                scope="invoice.create",
                key="abc",
                request={
                    "amount":
                        100
                },
            )
        )

        self.assertFalse(
            result.existing
        )

    def test_same_request_replays(self):
        self.store.begin_idempotent(
            tenant_id="tenant",
            scope="invoice.create",
            key="abc",
            request={
                "amount":
                    100
            },
        )

        self.store.complete_idempotent(
            tenant_id="tenant",
            scope="invoice.create",
            key="abc",
            response={
                "invoice_id":
                    "i1"
            },
        )

        result = (
            self.store
            .begin_idempotent(
                tenant_id="tenant",
                scope="invoice.create",
                key="abc",
                request={
                    "amount":
                        100
                },
            )
        )

        self.assertTrue(
            result.existing
        )

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            result.response[
                "invoice_id"
            ],
            "i1",
        )

    def test_same_key_different_request_rejected(self):
        self.store.begin_idempotent(
            tenant_id="tenant",
            scope="invoice.create",
            key="abc",
            request={
                "amount":
                    100
            },
        )

        with self.assertRaises(
            IdempotencyConflict
        ):
            self.store.begin_idempotent(
                tenant_id="tenant",
                scope="invoice.create",
                key="abc",
                request={
                    "amount":
                        200
                },
            )

    def test_same_key_different_tenant_isolated(self):
        first = (
            self.store
            .begin_idempotent(
                tenant_id="a",
                scope="x",
                key="same",
                request={"x": 1},
            )
        )

        second = (
            self.store
            .begin_idempotent(
                tenant_id="b",
                scope="x",
                key="same",
                request={"x": 2},
            )
        )

        self.assertFalse(
            first.existing
        )

        self.assertFalse(
            second.existing
        )


class InboxTests(
    DurableStoreTestCase
):

    def test_first_message_processed(self):
        self.assertTrue(
            self.store
            .register_inbox_message(
                tenant_id="tenant",
                message_id="m1",
                payload={"x": 1},
            )
        )

    def test_duplicate_message_ignored(self):
        self.store.register_inbox_message(
            tenant_id="tenant",
            message_id="m1",
            payload={"x": 1},
        )

        self.assertFalse(
            self.store
            .register_inbox_message(
                tenant_id="tenant",
                message_id="m1",
                payload={"x": 1},
            )
        )

    def test_message_id_payload_conflict(self):
        self.store.register_inbox_message(
            tenant_id="tenant",
            message_id="m1",
            payload={"x": 1},
        )

        with self.assertRaises(
            InboxConflict
        ):
            self.store.register_inbox_message(
                tenant_id="tenant",
                message_id="m1",
                payload={"x": 999},
            )


class SnapshotTests(
    DurableStoreTestCase
):

    def test_snapshot_round_trip(self):
        self.store.save_snapshot(
            tenant_id="tenant",
            stream_id="project",
            version=10,
            payload={
                "name":
                    "GOAT"
            },
        )

        snapshot = (
            self.store.load_snapshot(
                tenant_id="tenant",
                stream_id="project",
            )
        )

        self.assertEqual(
            snapshot.version,
            10,
        )

        self.assertEqual(
            snapshot.payload[
                "name"
            ],
            "GOAT",
        )

    def test_older_snapshot_rejected(self):
        self.store.save_snapshot(
            tenant_id="tenant",
            stream_id="project",
            version=10,
            payload={"x": 1},
        )

        with self.assertRaises(
            OptimisticConcurrencyError
        ):
            self.store.save_snapshot(
                tenant_id="tenant",
                stream_id="project",
                version=9,
                payload={"x": 2},
            )

    def test_snapshot_tamper_detected(self):
        self.store.save_snapshot(
            tenant_id="tenant",
            stream_id="project",
            version=1,
            payload={"x": 1},
        )

        self.store._conn.execute(
            """
            UPDATE goat_snapshots
            SET payload_json =
                '{"x":999}'
            """
        )

        with self.assertRaises(
            SnapshotIntegrityError
        ):
            self.store.load_snapshot(
                tenant_id="tenant",
                stream_id="project",
            )


class OutboxTests(
    DurableStoreTestCase
):

    def setUp(self):
        super().setUp()
        self.append_one()

    def test_claim(self):
        claimed = (
            self.store.claim_outbox(
                worker_id="worker-1"
            )
        )

        self.assertEqual(
            len(claimed),
            1,
        )

        self.assertEqual(
            claimed[0].state,
            OutboxState.PROCESSING,
        )

        self.assertEqual(
            claimed[0].attempts,
            1,
        )

    def test_second_worker_cannot_claim_active_lease(self):
        first = (
            self.store.claim_outbox(
                worker_id="worker-1"
            )
        )

        second = (
            self.store.claim_outbox(
                worker_id="worker-2"
            )
        )

        self.assertEqual(
            len(first),
            1,
        )

        self.assertEqual(
            second,
            (),
        )

    def test_acknowledge(self):
        claimed = (
            self.store.claim_outbox(
                worker_id="worker-1"
            )[0]
        )

        sent = (
            self.store
            .acknowledge_outbox(
                outbox_id=(
                    claimed.outbox_id
                ),
                worker_id="worker-1",
            )
        )

        self.assertEqual(
            sent.state,
            OutboxState.SENT,
        )

        self.assertIsNotNone(
            sent.sent_at
        )

    def test_wrong_worker_cannot_ack(self):
        claimed = (
            self.store.claim_outbox(
                worker_id="worker-1"
            )[0]
        )

        with self.assertRaises(
            OutboxLeaseError
        ):
            self.store.acknowledge_outbox(
                outbox_id=(
                    claimed.outbox_id
                ),
                worker_id="worker-2",
            )

    def test_failure_schedules_retry(self):
        claimed = (
            self.store.claim_outbox(
                worker_id="worker-1"
            )[0]
        )

        failed = (
            self.store.fail_outbox(
                outbox_id=(
                    claimed.outbox_id
                ),
                worker_id="worker-1",
                retry_delay_seconds=0,
            )
        )

        self.assertEqual(
            failed.state,
            OutboxState.RETRY,
        )

    def test_max_attempts_dead_letters(self):
        claimed = (
            self.store.claim_outbox(
                worker_id="worker-1"
            )[0]
        )

        failed = (
            self.store.fail_outbox(
                outbox_id=(
                    claimed.outbox_id
                ),
                worker_id="worker-1",
                retry_delay_seconds=0,
                max_attempts=1,
            )
        )

        self.assertEqual(
            failed.state,
            OutboxState.DEAD,
        )


class BackupTests(
    DurableStoreTestCase
):

    def test_backup_verifies(self):
        self.append_one()

        destination = (
            Path(
                self.temp.name
            )
            / "backup.db"
        )

        manifest = (
            self.store.create_backup(
                destination
            )
        )

        self.assertTrue(
            DurableStore
            .verify_backup(
                manifest
            )
        )

    def test_backup_contains_events(self):
        self.append_one()

        destination = (
            Path(
                self.temp.name
            )
            / "backup.db"
        )

        manifest = (
            self.store.create_backup(
                destination
            )
        )

        restored = DurableStore(
            destination
        )

        try:
            events = (
                restored.read_stream(
                    tenant_id="tenant",
                    stream_id="project-1",
                )
            )

            self.assertEqual(
                len(events),
                1,
            )

        finally:
            restored.close()

    def test_backup_checksum_tamper_detected(self):
        self.append_one()

        destination = (
            Path(
                self.temp.name
            )
            / "backup.db"
        )

        manifest = (
            self.store.create_backup(
                destination
            )
        )

        with destination.open(
            "ab"
        ) as fh:
            fh.write(
                b"TAMPER"
            )

        with self.assertRaises(
            BackupIntegrityError
        ):
            DurableStore.verify_backup(
                manifest
            )


class HealthTests(
    DurableStoreTestCase
):

    def test_health(self):
        self.append_one()

        health = self.store.health()

        self.assertEqual(
            health.integrity,
            "ok",
        )

        self.assertEqual(
            health.event_count,
            1,
        )

        self.assertEqual(
            health.stream_count,
            1,
        )

        self.assertEqual(
            health
            .pending_outbox_count,
            1,
        )


if __name__ == "__main__":
    unittest.main()
