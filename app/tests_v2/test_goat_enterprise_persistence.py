import os
import sqlite3
import tempfile
import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from leadbot_v2.goat.enterprise_persistence import (
    DataIntegrityError,
    DuplicateMessageConflict,
    EnterprisePersistenceStore,
    IdempotencyConflict,
    LeaseBusy,
    LeaseLost,
    OptimisticConcurrencyError,
    OutboxStatus,
)


UTC = timezone.utc


class PersistenceBase(
    unittest.TestCase
):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        self.path = os.path.join(
            self.tmp.name,
            "goat.db",
        )

        self.store = (
            EnterprisePersistenceStore(
                self.path
            )
        )

    def tearDown(self):
        self.store.close()

        self.tmp.cleanup()


class MigrationTests(
    PersistenceBase
):
    def test_schema_version(self):
        self.assertEqual(
            self.store.schema_version(),
            self.store.SCHEMA_VERSION,
        )

    def test_wal_and_integrity(self):
        health = (
            self.store.health()
        )

        self.assertTrue(
            health.integrity_ok
        )

        self.assertTrue(
            health.quick_check_ok
        )

        self.assertEqual(
            health.journal_mode,
            "wal",
        )


class EntityTests(
    PersistenceBase
):
    def test_create_update(self):
        created = (
            self.store.put_entity(
                tenant_id="t1",
                entity_type="project",
                entity_id="p1",
                payload={
                    "name":
                        "GOAT Project"
                },
                actor_id="president",
            )
        )

        self.assertEqual(
            created.version,
            1,
        )

        updated = (
            self.store.put_entity(
                tenant_id="t1",
                entity_type="project",
                entity_id="p1",
                payload={
                    "name":
                        "Updated"
                },
                expected_version=1,
                actor_id="president",
            )
        )

        self.assertEqual(
            updated.version,
            2,
        )

    def test_stale_write_rejected(self):
        self.store.put_entity(
            tenant_id="t1",
            entity_type="project",
            entity_id="p1",
            payload={
                "x":
                    1
            },
            actor_id="u1",
        )

        self.store.put_entity(
            tenant_id="t1",
            entity_type="project",
            entity_id="p1",
            payload={
                "x":
                    2
            },
            expected_version=1,
            actor_id="u1",
        )

        with self.assertRaises(
            OptimisticConcurrencyError
        ):
            self.store.put_entity(
                tenant_id="t1",
                entity_type="project",
                entity_id="p1",
                payload={
                    "x":
                        3
                },
                expected_version=1,
                actor_id="u2",
            )

    def test_tenant_isolation(self):
        self.store.put_entity(
            tenant_id="tenant-a",
            entity_type="project",
            entity_id="same-id",
            payload={
                "secret":
                    "A"
            },
            actor_id="u",
        )

        self.store.put_entity(
            tenant_id="tenant-b",
            entity_type="project",
            entity_id="same-id",
            payload={
                "secret":
                    "B"
            },
            actor_id="u",
        )

        a = self.store.get_entity(
            tenant_id="tenant-a",
            entity_type="project",
            entity_id="same-id",
        )

        b = self.store.get_entity(
            tenant_id="tenant-b",
            entity_type="project",
            entity_id="same-id",
        )

        self.assertEqual(
            a.payload["secret"],
            "A",
        )

        self.assertEqual(
            b.payload["secret"],
            "B",
        )

    def test_tombstone(self):
        created = (
            self.store.put_entity(
                tenant_id="t1",
                entity_type="rfi",
                entity_id="r1",
                payload={
                    "subject":
                        "Test"
                },
                actor_id="pm",
            )
        )

        deleted = (
            self.store.delete_entity(
                tenant_id="t1",
                entity_type="rfi",
                entity_id="r1",
                expected_version=(
                    created.version
                ),
                actor_id="pm",
            )
        )

        self.assertIsNotNone(
            deleted.deleted_at
        )

        self.assertIsNone(
            self.store.get_entity(
                tenant_id="t1",
                entity_type="rfi",
                entity_id="r1",
            )
        )


class MultiConnectionTests(
    PersistenceBase
):
    def test_two_process_style_occ(self):
        self.store.put_entity(
            tenant_id="t1",
            entity_type="estimate",
            entity_id="e1",
            payload={
                "value":
                    100
            },
            actor_id="a",
        )

        second = (
            EnterprisePersistenceStore(
                self.path
            )
        )

        try:
            first_read = (
                self.store.get_entity(
                    tenant_id="t1",
                    entity_type="estimate",
                    entity_id="e1",
                )
            )

            second_read = (
                second.get_entity(
                    tenant_id="t1",
                    entity_type="estimate",
                    entity_id="e1",
                )
            )

            self.store.put_entity(
                tenant_id="t1",
                entity_type="estimate",
                entity_id="e1",
                payload={
                    "value":
                        200
                },
                expected_version=(
                    first_read.version
                ),
                actor_id="a",
            )

            with self.assertRaises(
                OptimisticConcurrencyError
            ):
                second.put_entity(
                    tenant_id="t1",
                    entity_type="estimate",
                    entity_id="e1",
                    payload={
                        "value":
                            300
                    },
                    expected_version=(
                        second_read.version
                    ),
                    actor_id="b",
                )

        finally:
            second.close()


class EventTests(
    PersistenceBase
):
    def test_event_chain(self):
        for number in range(
            3
        ):
            if number == 0:
                expected = None
            else:
                expected = number

            self.store.put_entity(
                tenant_id="t1",
                entity_type="project",
                entity_id="p1",
                payload={
                    "value":
                        number
                },
                expected_version=(
                    expected
                ),
                actor_id="president",
            )

        self.assertTrue(
            self.store.verify_event_chain(
                tenant_id="t1"
            )
        )

    def test_event_tamper_detected(self):
        self.store.put_entity(
            tenant_id="t1",
            entity_type="project",
            entity_id="p1",
            payload={
                "value":
                    1
            },
            actor_id="president",
        )

        self.store._connection.execute(
            """
            UPDATE durable_events
            SET payload_json = '{"tampered":true}'
            WHERE tenant_id = 't1'
            """
        )

        with self.assertRaises(
            DataIntegrityError
        ):
            self.store.verify_event_chain(
                tenant_id="t1"
            )


class OutboxTests(
    PersistenceBase
):
    def test_claim_complete(self):
        message_id = (
            self.store.enqueue_outbox(
                tenant_id="t1",
                topic="rfi.created",
                payload={
                    "rfi":
                        "r1"
                },
            )
        )

        claimed = (
            self.store.claim_outbox(
                worker_id="worker-1"
            )
        )

        self.assertEqual(
            claimed[0].outbox_id,
            message_id,
        )

        self.assertEqual(
            claimed[0].status,
            OutboxStatus.CLAIMED,
        )

        self.store.complete_outbox(
            outbox_id=message_id,
            worker_id="worker-1",
        )

    def test_dedupe(self):
        first = (
            self.store.enqueue_outbox(
                tenant_id="t1",
                topic="invoice.sent",
                payload={
                    "invoice":
                        1
                },
                dedupe_key="invoice-1",
            )
        )

        second = (
            self.store.enqueue_outbox(
                tenant_id="t1",
                topic="invoice.sent",
                payload={
                    "invoice":
                        1
                },
                dedupe_key="invoice-1",
            )
        )

        self.assertEqual(
            first,
            second,
        )

    def test_retry_dead_letter(self):
        base = datetime(
            2026,
            8,
            15,
            12,
            tzinfo=UTC,
        )

        message_id = (
            self.store.enqueue_outbox(
                tenant_id="t1",
                topic="test",
                payload={},
                available_at=base,
            )
        )

        claimed = self.store.claim_outbox(
            worker_id="w",
            now=base,
        )

        self.assertEqual(
            len(claimed),
            1,
        )

        self.assertEqual(
            claimed[0].outbox_id,
            message_id,
        )

        self.store.fail_outbox(
            outbox_id=message_id,
            worker_id="w",
            max_attempts=1,
            now=base,
        )

        row = (
            self.store
            ._connection
            .execute(
                """
                SELECT status
                FROM outbox
                WHERE outbox_id = ?
                """,
                (
                    message_id,
                ),
            )
            .fetchone()
        )

        self.assertEqual(
            row["status"],
            OutboxStatus.DEAD.value,
        )


class InboxTests(
    PersistenceBase
):
    def test_duplicate_same_payload(self):
        first = (
            self.store.record_inbox(
                tenant_id="t1",
                consumer="billing",
                message_id="m1",
                payload={
                    "x":
                        1
                },
            )
        )

        second = (
            self.store.record_inbox(
                tenant_id="t1",
                consumer="billing",
                message_id="m1",
                payload={
                    "x":
                        1
                },
            )
        )

        self.assertTrue(
            first
        )

        self.assertFalse(
            second
        )

    def test_duplicate_different_payload_fails(self):
        self.store.record_inbox(
            tenant_id="t1",
            consumer="billing",
            message_id="m1",
            payload={
                "x":
                    1
            },
        )

        with self.assertRaises(
            DuplicateMessageConflict
        ):
            self.store.record_inbox(
                tenant_id="t1",
                consumer="billing",
                message_id="m1",
                payload={
                    "x":
                        2
                },
            )


class IdempotencyTests(
    PersistenceBase
):
    def test_replay(self):
        request = {
            "amount":
                100
        }

        response = {
            "transaction_id":
                "tx1"
        }

        self.store.save_idempotency(
            tenant_id="t1",
            scope="payments",
            key="k1",
            request_payload=request,
            response_payload=response,
        )

        replay = (
            self.store.get_idempotency(
                tenant_id="t1",
                scope="payments",
                key="k1",
                request_payload=request,
            )
        )

        self.assertEqual(
            replay,
            response,
        )

    def test_key_reuse_conflict(self):
        self.store.save_idempotency(
            tenant_id="t1",
            scope="payments",
            key="k1",
            request_payload={
                "amount":
                    100
            },
            response_payload={
                "ok":
                    True
            },
        )

        with self.assertRaises(
            IdempotencyConflict
        ):
            self.store.get_idempotency(
                tenant_id="t1",
                scope="payments",
                key="k1",
                request_payload={
                    "amount":
                        200
                },
            )


class LeaseTests(
    PersistenceBase
):
    def test_fencing_tokens(self):
        base = datetime(
            2026,
            8,
            15,
            12,
            tzinfo=UTC,
        )

        first = (
            self.store.acquire_lease(
                lease_name="scheduler",
                owner_id="node-a",
                ttl=timedelta(
                    seconds=30
                ),
                now=base,
            )
        )

        with self.assertRaises(
            LeaseBusy
        ):
            self.store.acquire_lease(
                lease_name="scheduler",
                owner_id="node-b",
                ttl=timedelta(
                    seconds=30
                ),
                now=(
                    base
                    + timedelta(
                        seconds=5
                    )
                ),
            )

        second = (
            self.store.acquire_lease(
                lease_name="scheduler",
                owner_id="node-b",
                ttl=timedelta(
                    seconds=30
                ),
                now=(
                    base
                    + timedelta(
                        seconds=31
                    )
                ),
            )
        )

        self.assertGreater(
            second.fencing_token,
            first.fencing_token,
        )

    def test_stale_renew_rejected(self):
        base = datetime(
            2026,
            8,
            15,
            12,
            tzinfo=UTC,
        )

        lease = (
            self.store.acquire_lease(
                lease_name="worker",
                owner_id="a",
                ttl=timedelta(
                    seconds=10
                ),
                now=base,
            )
        )

        with self.assertRaises(
            LeaseLost
        ):
            self.store.renew_lease(
                lease_name="worker",
                owner_id="a",
                fencing_token=(
                    lease.fencing_token
                ),
                ttl=timedelta(
                    seconds=10
                ),
                now=(
                    base
                    + timedelta(
                        seconds=11
                    )
                ),
            )


class SnapshotTests(
    PersistenceBase
):
    def test_snapshot(self):
        self.store.put_entity(
            tenant_id="t1",
            entity_type="project",
            entity_id="p1",
            payload={
                "name":
                    "Project"
            },
            actor_id="u",
        )

        snapshot = (
            self.store.create_snapshot(
                tenant_id="t1",
                entity_type="project",
                entity_id="p1",
            )
        )

        latest = (
            self.store.latest_snapshot(
                tenant_id="t1",
                entity_type="project",
                entity_id="p1",
            )
        )

        self.assertEqual(
            snapshot.snapshot_id,
            latest.snapshot_id,
        )


class BackupTests(
    PersistenceBase
):
    def test_backup_restore(self):
        self.store.put_entity(
            tenant_id="t1",
            entity_type="project",
            entity_id="p1",
            payload={
                "name":
                    "Survives"
            },
            actor_id="u",
        )

        backup_path = os.path.join(
            self.tmp.name,
            "backup.db",
        )

        result = (
            self.store.backup(
                backup_path
            )
        )

        self.assertTrue(
            self.store.verify_backup(
                backup_path,
                expected_sha256=(
                    result.sha256
                ),
            )
        )

        restored = (
            EnterprisePersistenceStore(
                backup_path
            )
        )

        try:
            entity = (
                restored.get_entity(
                    tenant_id="t1",
                    entity_type="project",
                    entity_id="p1",
                )
            )

            self.assertEqual(
                entity.payload["name"],
                "Survives",
            )

        finally:
            restored.close()


if __name__ == "__main__":
    unittest.main()
