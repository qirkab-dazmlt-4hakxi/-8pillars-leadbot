import unittest

from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)

from leadbot_v2.goat.preconstruction.bid_packages.control import (
    BidPackageControlService,
    ControlSeverity,
    Discipline,
    DocumentKind,
    DuplicateDocumentError,
    FrozenRevisionError,
    PackageSource,
)


UTC = timezone.utc


def sha(
    char,
):
    return char * 64


def future_due():
    return datetime(
        2026,
        8,
        20,
        17,
        0,
        tzinfo=UTC,
    )


def as_of():
    return datetime(
        2026,
        8,
        15,
        11,
        0,
        tzinfo=UTC,
    )


def create_package(
    service,
    *,
    due_at=None,
):
    return (
        service
        .create_package(
            tenant_id="tenant",
            business_unit_id="twins",
            opportunity_id="opp-1",
            project_name=(
                "Medical Office"
            ),
            city="Dallas",
            source=(
                PackageSource
                .BUILDING_CONNECTED
            ),
            invited_by=(
                "General Contractor"
            ),
            gc_name=(
                "Example GC"
            ),
            client_name=(
                "Owner"
            ),
            due_at=(
                due_at
                if due_at
                is not None
                else future_due()
            ),
            created_by="franz",
        )
    )


def ingest_plans(
    service,
    package_id,
    *,
    hash_char="a",
    file_name="plans.pdf",
    logical_key=(
        "CURRENT PLAN SET"
    ),
):
    return (
        service
        .ingest_document(
            package_id=(
                package_id
            ),
            actor_id="estimator",
            file_name=(
                file_name
            ),
            sha256=sha(
                hash_char
            ),
            size_bytes=(
                2_000_000
            ),
            kind=(
                DocumentKind.PLANS
            ),
            discipline=(
                Discipline.GENERAL
            ),
            logical_key=(
                logical_key
            ),
            source_ref=(
                f"upload:{file_name}"
            ),
            revision_label="IFB",
            issue_date=date(
                2026,
                8,
                10,
            ),
            sheet_count=42,
        )
    )


def ingest_specs(
    service,
    package_id,
):
    return (
        service
        .ingest_document(
            package_id=(
                package_id
            ),
            actor_id="estimator",
            file_name=(
                "specifications.pdf"
            ),
            sha256=sha(
                "b"
            ),
            size_bytes=(
                1_000_000
            ),
            kind=(
                DocumentKind
                .SPECIFICATIONS
            ),
            discipline=(
                Discipline.GENERAL
            ),
            logical_key=(
                "PROJECT SPECIFICATIONS"
            ),
            source_ref=(
                "upload:specifications"
            ),
        )
    )


class PackageCreationTests(
    unittest.TestCase
):

    def test_package_creates_initial_revision(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        revision = (
            service
            .current_revision(
                package.package_id
            )
        )

        self.assertEqual(
            revision.label,
            "INITIAL",
        )

        self.assertEqual(
            revision.document_ids,
            (),
        )

    def test_package_preserves_project_links(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        self.assertEqual(
            package.opportunity_id,
            "opp-1",
        )

        self.assertEqual(
            package.gc_name,
            "Example GC",
        )

        self.assertEqual(
            package.source,
            PackageSource
            .BUILDING_CONNECTED,
        )

    def test_naive_due_date_rejected(self):
        service = (
            BidPackageControlService()
        )

        with self.assertRaises(
            ValueError
        ):
            (
                service.create_package(
                    tenant_id="tenant",
                    business_unit_id="bu",
                    project_name="Project",
                    city="Dallas",
                    source=(
                        PackageSource
                        .DIRECT_GC
                    ),
                    created_by="user",
                    due_at=datetime(
                        2026,
                        8,
                        20,
                    ),
                )
            )


class DocumentIntakeTests(
    unittest.TestCase
):

    def test_plan_ingest_becomes_current(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        document = ingest_plans(
            service,
            package.package_id,
        )

        current = (
            service
            .current_documents(
                package.package_id
            )
        )

        self.assertEqual(
            current,
            (
                document,
            ),
        )

    def test_invalid_hash_rejected(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        with self.assertRaises(
            ValueError
        ):
            (
                service.ingest_document(
                    package_id=(
                        package.package_id
                    ),
                    actor_id="user",
                    file_name="plans.pdf",
                    sha256="bad-hash",
                    size_bytes=100,
                    kind=(
                        DocumentKind.PLANS
                    ),
                    logical_key="plans",
                    source_ref="upload",
                )
            )

    def test_duplicate_content_is_blocked(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        with self.assertRaises(
            DuplicateDocumentError
        ):
            (
                service.ingest_document(
                    package_id=(
                        package.package_id
                    ),
                    actor_id="user",
                    file_name="duplicate.pdf",
                    sha256=sha(
                        "a"
                    ),
                    size_bytes=500,
                    kind=(
                        DocumentKind.PLANS
                    ),
                    logical_key=(
                        "OTHER PLANS"
                    ),
                    source_ref=(
                        "upload:duplicate"
                    ),
                )
            )

    def test_new_same_logical_key_supersedes_old(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        old = ingest_plans(
            service,
            package.package_id,
            hash_char="a",
        )

        new = ingest_plans(
            service,
            package.package_id,
            hash_char="c",
            file_name=(
                "plans-revised.pdf"
            ),
        )

        self.assertEqual(
            new
            .supersedes_document_id,
            old.document_id,
        )

        current_ids = {
            document.document_id
            for document
            in service
            .current_documents(
                package.package_id
            )
        }

        self.assertNotIn(
            old.document_id,
            current_ids,
        )

        self.assertIn(
            new.document_id,
            current_ids,
        )

    def test_file_path_not_accepted_as_filename(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        with self.assertRaises(
            ValueError
        ):
            (
                service.ingest_document(
                    package_id=(
                        package.package_id
                    ),
                    actor_id="user",
                    file_name=(
                        "../plans.pdf"
                    ),
                    sha256=sha(
                        "d"
                    ),
                    size_bytes=100,
                    kind=(
                        DocumentKind.PLANS
                    ),
                    logical_key="plans",
                    source_ref="upload",
                )
            )


class RevisionControlTests(
    unittest.TestCase
):

    def test_new_revision_inherits_documents(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        plan = ingest_plans(
            service,
            package.package_id,
        )

        revision = (
            service
            .create_revision(
                package_id=(
                    package.package_id
                ),
                actor_id="estimator",
                label="ADDENDUM-1",
                reason=(
                    "Owner issued "
                    "Addendum 1"
                ),
            )
        )

        self.assertEqual(
            revision.document_ids,
            (
                plan.document_id,
            ),
        )

    def test_historical_revision_is_not_rewritten(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        old_plan = ingest_plans(
            service,
            package.package_id,
            hash_char="a",
        )

        old_revision = (
            service
            .current_revision(
                package.package_id
            )
        )

        service.create_revision(
            package_id=(
                package.package_id
            ),
            actor_id="estimator",
            label="ADDENDUM-1",
            reason="revision",
        )

        ingest_plans(
            service,
            package.package_id,
            hash_char="c",
            file_name=(
                "plans-addendum1.pdf"
            ),
        )

        historical = (
            service
            .get_revision(
                old_revision
                .revision_id
            )
        )

        self.assertEqual(
            historical
            .document_ids,
            (
                old_plan
                .document_id,
            ),
        )

    def test_revision_diff_detects_replacement(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        old = ingest_plans(
            service,
            package.package_id,
            hash_char="a",
        )

        first_revision = (
            service
            .current_revision(
                package.package_id
            )
        )

        service.create_revision(
            package_id=(
                package.package_id
            ),
            actor_id="estimator",
            label="ADDENDUM-1",
            reason="revision",
        )

        new = ingest_plans(
            service,
            package.package_id,
            hash_char="c",
            file_name=(
                "revised-plans.pdf"
            ),
        )

        second_revision = (
            service
            .current_revision(
                package.package_id
            )
        )

        diff = (
            service
            .diff_revisions(
                old_revision_id=(
                    first_revision
                    .revision_id
                ),
                new_revision_id=(
                    second_revision
                    .revision_id
                ),
            )
        )

        self.assertEqual(
            diff
            .replaced_document_pairs,
            (
                (
                    old.document_id,
                    new.document_id,
                ),
            ),
        )

        self.assertTrue(
            diff.changed
        )

    def test_revision_diff_detects_added_document(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        first = (
            service
            .current_revision(
                package.package_id
            )
        )

        service.create_revision(
            package_id=(
                package.package_id
            ),
            actor_id="user",
            label="ADDENDUM-1",
            reason="new specs",
        )

        specs = ingest_specs(
            service,
            package.package_id,
        )

        second = (
            service
            .current_revision(
                package.package_id
            )
        )

        diff = (
            service
            .diff_revisions(
                old_revision_id=(
                    first
                    .revision_id
                ),
                new_revision_id=(
                    second
                    .revision_id
                ),
            )
        )

        self.assertEqual(
            diff
            .added_document_ids,
            (
                specs.document_id,
            ),
        )

    def test_document_removal_is_revision_scoped(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        specs = ingest_specs(
            service,
            package.package_id,
        )

        old = (
            service
            .current_revision(
                package.package_id
            )
        )

        service.create_revision(
            package_id=(
                package.package_id
            ),
            actor_id="user",
            label="REV-2",
            reason="spec withdrawal",
        )

        service.remove_document(
            package_id=(
                package.package_id
            ),
            document_id=(
                specs.document_id
            ),
            actor_id="user",
            reason=(
                "GC withdrew "
                "specification set"
            ),
        )

        self.assertIn(
            specs.document_id,
            service
            .get_revision(
                old.revision_id
            )
            .document_ids,
        )

        self.assertNotIn(
            specs.document_id,
            service
            .current_revision(
                package.package_id
            )
            .document_ids,
        )


class FreezeTests(
    unittest.TestCase
):

    def test_frozen_revision_blocks_document_mutation(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        service.freeze_current_revision(
            package_id=(
                package.package_id
            ),
            actor_id="estimator",
            note=(
                "Estimate basis "
                "locked"
            ),
        )

        with self.assertRaises(
            FrozenRevisionError
        ):
            (
                service.ingest_document(
                    package_id=(
                        package.package_id
                    ),
                    actor_id="user",
                    file_name=(
                        "extra.pdf"
                    ),
                    sha256=sha(
                        "e"
                    ),
                    size_bytes=500,
                    kind=(
                        DocumentKind.OTHER
                    ),
                    logical_key=(
                        "EXTRA"
                    ),
                    source_ref="upload",
                )
            )

    def test_new_revision_can_follow_frozen_revision(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        frozen = (
            service.freeze_current_revision(
                package_id=(
                    package.package_id
                ),
                actor_id="estimator",
                note="basis locked",
            )
        )

        new_revision = (
            service
            .create_revision(
                package_id=(
                    package.package_id
                ),
                actor_id="estimator",
                label="ADDENDUM-2",
                reason=(
                    "New owner changes"
                ),
            )
        )

        self.assertEqual(
            new_revision
            .parent_revision_id,
            frozen.revision_id,
        )

        self.assertFalse(
            new_revision.frozen
        )


class ReadinessTests(
    unittest.TestCase
):

    def test_ready_with_plans_and_due_date(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        result = (
            service.readiness(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        self.assertTrue(
            result.ready
        )

        self.assertFalse(
            result.blockers
        )

    def test_missing_plans_blocks_execution(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        result = (
            service.readiness(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        codes = {
            finding.code
            for finding
            in result.blockers
        }

        self.assertIn(
            "PLAN_SET_MISSING",
            codes,
        )

    def test_missing_specs_is_review_not_blocker(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        result = (
            service.readiness(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        self.assertIn(
            "SPECIFICATIONS_MISSING",
            {
                finding.code
                for finding
                in result
                .review_items
            },
        )

        self.assertTrue(
            result.ready
        )

    def test_missing_due_date_blocks(self):
        service = (
            BidPackageControlService()
        )

        package = (
            service
            .create_package(
                tenant_id="tenant",
                business_unit_id="bu",
                project_name="Project",
                city="Dallas",
                source=(
                    PackageSource
                    .DIRECT_GC
                ),
                created_by="user",
                due_at=None,
            )
        )

        ingest_plans(
            service,
            package.package_id,
        )

        result = (
            service.readiness(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        self.assertIn(
            "BID_DUE_DATE_MISSING",
            {
                finding.code
                for finding
                in result.blockers
            },
        )

    def test_past_due_blocks(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service,
            due_at=(
                as_of()
                - timedelta(
                    hours=1
                )
            ),
        )

        ingest_plans(
            service,
            package.package_id,
        )

        result = (
            service.readiness(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        self.assertIn(
            "BID_DUE_DATE_PASSED",
            {
                finding.code
                for finding
                in result.blockers
            },
        )

    def test_due_within_24_hours_generates_review(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service,
            due_at=(
                as_of()
                + timedelta(
                    hours=12
                )
            ),
        )

        ingest_plans(
            service,
            package.package_id,
        )

        result = (
            service.readiness(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        self.assertIn(
            "BID_DUE_WITHIN_24_HOURS",
            {
                finding.code
                for finding
                in result
                .review_items
            },
        )


class ManifestTests(
    unittest.TestCase
):

    def test_manifest_is_authoritative_current_package(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        plan = ingest_plans(
            service,
            package.package_id,
        )

        specs = ingest_specs(
            service,
            package.package_id,
        )

        manifest = (
            service
            .execution_manifest(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        self.assertEqual(
            manifest
            .revision_id,
            service
            .current_revision(
                package.package_id
            )
            .revision_id,
        )

        self.assertEqual(
            manifest
            .plan_document_ids,
            (
                plan.document_id,
            ),
        )

        self.assertEqual(
            manifest
            .specification_document_ids,
            (
                specs.document_id,
            ),
        )

        self.assertTrue(
            manifest
            .ready_for_execution
        )

    def test_manifest_tracks_previous_revision(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        old = (
            service
            .current_revision(
                package.package_id
            )
        )

        service.create_revision(
            package_id=(
                package.package_id
            ),
            actor_id="user",
            label="ADDENDUM-3",
            reason="revision",
        )

        manifest = (
            service
            .execution_manifest(
                package_id=(
                    package.package_id
                ),
                as_of=as_of(),
            )
        )

        self.assertEqual(
            manifest
            .previous_revision_id,
            old.revision_id,
        )


class AuditTests(
    unittest.TestCase
):

    def test_chronology_records_control_events(self):
        service = (
            BidPackageControlService()
        )

        package = create_package(
            service
        )

        ingest_plans(
            service,
            package.package_id,
        )

        service.create_revision(
            package_id=(
                package.package_id
            ),
            actor_id="user",
            label="ADDENDUM-4",
            reason="revision",
        )

        events = (
            service.chronology(
                package_id=(
                    package.package_id
                )
            )
        )

        event_types = {
            event.event_type
            for event
            in events
        }

        self.assertIn(
            "bid_package.created",
            event_types,
        )

        self.assertIn(
            "bid_document.ingested",
            event_types,
        )

        self.assertIn(
            "bid_package.revision_created",
            event_types,
        )


if __name__ == "__main__":
    unittest.main()
