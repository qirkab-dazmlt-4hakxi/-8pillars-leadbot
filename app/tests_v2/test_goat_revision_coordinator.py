import unittest

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from leadbot_v2.goat.preconstruction.revisions.coordinator import (
    ApprovalSeverity,
    RevisionExecutionCoordinator,
    RevisionExecutionMode,
)

from leadbot_v2.goat.preconstruction.semantic.geometry import (
    SemanticTakeoff,
)

from leadbot_v2.goat.preconstruction.semantic.pricing_bridge import (
    SemanticPricingResult,
)


@dataclass(frozen=True)
class Page:
    page_number: int


@dataclass(frozen=True)
class Document:
    document_id: str
    file_name: str
    pages: tuple


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    page_number: int


@dataclass
class Delta:
    old_page_number: int | None
    new_page_number: int | None
    old_source_ref: str | None
    new_source_ref: str | None


class Impact:
    def __init__(
        self,
        *,
        no_change=False,
        blockers=(),
        old_pages=(1,),
        new_pages=(1,),
        mode="incremental",
    ):
        self.old_document_id = "old-doc"
        self.new_document_id = "new-doc"
        self.no_change = no_change
        self.blockers = tuple(
            blockers
        )
        self.findings = tuple(
            blockers
        )
        self.impacted_old_pages = tuple(
            old_pages
        )
        self.impacted_new_pages = tuple(
            new_pages
        )
        self.impacted_trades = (
            SimpleNamespace(
                value="concrete"
            ),
        ) if not no_change else ()
        self.invalidated_candidate_ids = (
            "old-candidate",
        ) if not no_change else ()
        self.requires_full_rerun = (
            mode
            == "full_rerun"
        )
        self.changed_sheets = (
            (
                Delta(
                    1,
                    1,
                    "old.pdf#page=1",
                    "new.pdf#page=1",
                ),
            )
            if not no_change
            else ()
        )


class FakeRevisionEngine:
    def __init__(
        self,
        impact,
    ):
        self.impact = impact
        self.calls = []

    def compare(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.impact


class FakeSemanticResolver:
    def __init__(
        self,
        semantic,
    ):
        self.semantic = semantic
        self.calls = []

    def resolve(
        self,
        document,
    ):
        self.calls.append(
            document
        )

        return self.semantic


class FakePricingService:
    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = []

    def price_takeoff(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.result


class FakeLifecycle:
    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = []

    def apply(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.result


class FakePdfIngest:
    def __init__(
        self,
        documents,
    ):
        self.documents = list(
            documents
        )
        self.calls = []

    def ingest(
        self,
        path,
        *,
        password=None,
    ):
        self.calls.append(
            (
                str(path),
                password,
            )
        )

        return self.documents.pop(
            0
        )


def semantic(
    *,
    page=1,
):
    return SemanticTakeoff(
        document_id="semantic-doc",
        candidates=(
            Candidate(
                "new-candidate",
                page,
            ),
        ),
        findings=(),
    )


def pricing(
    *,
    bid=15000,
):
    scope = (
        SimpleNamespace(
            semantic_candidate_id=(
                "new-candidate"
            ),
            bid_price_cents=bid,
        )
    )

    return SemanticPricingResult(
        city="Dallas",
        market=(
            "dallas_fort_worth"
        ),
        as_of=date(
            2026,
            8,
            15,
        ),
        scopes=(
            scope,
        ),
    )


def lifecycle_result(
    *,
    ready=True,
    delta=2000,
    review_queue=(),
):
    financial = (
        SimpleNamespace(
            old_impacted_direct_cost_cents=10000,
            old_impacted_bid_price_cents=13000,
            replacement_direct_cost_cents=12000,
            replacement_bid_price_cents=(
                13000
                + delta
            ),
            direct_cost_delta_cents=2000,
            bid_price_delta_cents=delta,
        )
    )

    return SimpleNamespace(
        proposal_ready=ready,
        review_queue=tuple(
            review_queue
        ),
        invalidated_lines=(
            SimpleNamespace(
                line_id="old-line"
            ),
        ),
        replacement_lines=(
            SimpleNamespace(
                line_id="new-line"
            ),
        ),
        delta=financial,
    )


def coordinator(
    *,
    impact,
    semantic_value=None,
    pricing_value=None,
    lifecycle_value=None,
):
    return (
        RevisionExecutionCoordinator(
            workflow=SimpleNamespace(),
            pricing_service=(
                FakePricingService(
                    pricing_value
                    or pricing()
                )
            ),
            revision_engine=(
                FakeRevisionEngine(
                    impact
                )
            ),
            semantic_resolver=(
                FakeSemanticResolver(
                    semantic_value
                    or semantic()
                )
            ),
            lifecycle=(
                FakeLifecycle(
                    lifecycle_value
                    or lifecycle_result()
                )
            ),
            pdf_ingest=(
                FakePdfIngest(
                    ()
                )
            ),
        )
    )


class CoordinatorTests(
    unittest.TestCase
):

    def test_incremental_reruns_only_impacted_page(self):
        service = coordinator(
            impact=Impact(
                new_pages=(2,),
            ),
            semantic_value=(
                semantic(
                    page=2
                )
            ),
        )

        new_document = Document(
            "new-doc",
            "new.pdf",
            (
                Page(1),
                Page(2),
                Page(3),
            ),
        )

        result = (
            service.execute_documents(
                old_document=(
                    Document(
                        "old-doc",
                        "old.pdf",
                        (
                            Page(1),
                            Page(2),
                            Page(3),
                        ),
                    )
                ),
                new_document=(
                    new_document
                ),
                previous_semantic=(
                    semantic()
                ),
                estimate_id="est",
                actor_id="estimator",
                city="Dallas",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=(
                    SimpleNamespace()
                ),
            )
        )

        sliced = (
            service
            .semantic_resolver
            .calls[0]
        )

        self.assertEqual(
            tuple(
                page.page_number
                for page
                in sliced.pages
            ),
            (
                2,
            ),
        )

        self.assertEqual(
            result
            .approval_packet
            .mode,
            RevisionExecutionMode
            .INCREMENTAL,
        )

    def test_full_rerun_uses_all_pages(self):
        service = coordinator(
            impact=Impact(
                mode="full_rerun"
            )
        )

        document = Document(
            "new-doc",
            "new.pdf",
            (
                Page(1),
                Page(2),
                Page(3),
            ),
        )

        service.execute_documents(
            old_document=document,
            new_document=document,
            previous_semantic=(
                semantic()
            ),
            estimate_id="est",
            actor_id="estimator",
            city="Dallas",
            as_of=date(
                2026,
                8,
                15,
            ),
            markup=(
                SimpleNamespace()
            ),
        )

        sliced = (
            service
            .semantic_resolver
            .calls[0]
        )

        self.assertEqual(
            len(
                sliced.pages
            ),
            3,
        )

    def test_no_change_skips_semantic_rerun(self):
        service = coordinator(
            impact=Impact(
                no_change=True
            )
        )

        result = (
            service.execute_documents(
                old_document=(
                    Document(
                        "old-doc",
                        "old.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                new_document=(
                    Document(
                        "new-doc",
                        "new.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                previous_semantic=(
                    semantic()
                ),
                estimate_id="est",
                actor_id="estimator",
                city="Dallas",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=(
                    SimpleNamespace()
                ),
            )
        )

        self.assertEqual(
            service
            .semantic_resolver
            .calls,
            [],
        )

        self.assertEqual(
            result
            .approval_packet
            .mode,
            RevisionExecutionMode
            .NO_CHANGE,
        )

        self.assertTrue(
            result
            .approval_packet
            .ready_for_revised_proposal,
        )

    def test_revision_blocker_prevents_mutation(self):
        blocker = (
            SimpleNamespace(
                code=(
                    "DUPLICATE_SHEET_ID"
                ),
                severity=(
                    SimpleNamespace(
                        value="blocker"
                    )
                ),
                message=(
                    "duplicate sheet"
                ),
                new_page_number=1,
                old_page_number=1,
                sheet_number="S2.1",
                source_ref="new.pdf#page=1",
            )
        )

        service = coordinator(
            impact=Impact(
                blockers=(
                    blocker,
                )
            )
        )

        result = (
            service.execute_documents(
                old_document=(
                    Document(
                        "old-doc",
                        "old.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                new_document=(
                    Document(
                        "new-doc",
                        "new.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                previous_semantic=(
                    semantic()
                ),
                estimate_id="est",
                actor_id="estimator",
                city="Dallas",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=(
                    SimpleNamespace()
                ),
            )
        )

        self.assertEqual(
            service.lifecycle.calls,
            [],
        )

        self.assertEqual(
            result
            .approval_packet
            .mode,
            RevisionExecutionMode
            .BLOCKED,
        )

        self.assertTrue(
            result
            .approval_packet
            .blockers,
        )

    def test_lifecycle_delta_enters_approval_packet(self):
        service = coordinator(
            impact=Impact()
        )

        result = (
            service.execute_documents(
                old_document=(
                    Document(
                        "old-doc",
                        "old.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                new_document=(
                    Document(
                        "new-doc",
                        "new.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                previous_semantic=(
                    semantic()
                ),
                estimate_id="est",
                actor_id="estimator",
                city="Dallas",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=(
                    SimpleNamespace()
                ),
            )
        )

        delta = (
            result
            .approval_packet
            .financial_delta
        )

        self.assertEqual(
            delta
            .bid_price_delta_cents,
            2000,
        )

        self.assertEqual(
            result
            .approval_packet
            .invalidated_line_ids,
            (
                "old-line",
            ),
        )

        self.assertEqual(
            result
            .approval_packet
            .replacement_line_ids,
            (
                "new-line",
            ),
        )

    def test_review_queue_blocks_revised_proposal(self):
        review = (
            SimpleNamespace(
                code=(
                    "REVISION_SCOPE_REVIEW"
                ),
                severity=(
                    SimpleNamespace(
                        value="review"
                    )
                ),
                message=(
                    "estimator review"
                ),
                candidate_id=(
                    "new-candidate"
                ),
                line_id=None,
                source_ref=(
                    "new.pdf#page=1"
                ),
            )
        )

        service = coordinator(
            impact=Impact(),
            lifecycle_value=(
                lifecycle_result(
                    ready=False,
                    review_queue=(
                        review,
                    ),
                )
            ),
        )

        result = (
            service.execute_documents(
                old_document=(
                    Document(
                        "old-doc",
                        "old.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                new_document=(
                    Document(
                        "new-doc",
                        "new.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                previous_semantic=(
                    semantic()
                ),
                estimate_id="est",
                actor_id="estimator",
                city="Dallas",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=(
                    SimpleNamespace()
                ),
            )
        )

        self.assertFalse(
            result
            .approval_packet
            .ready_for_revised_proposal,
        )

        self.assertTrue(
            result
            .approval_packet
            .review_items,
        )

    def test_removed_only_revision_skips_semantic(self):
        service = coordinator(
            impact=Impact(
                new_pages=(),
            )
        )

        result = (
            service.execute_documents(
                old_document=(
                    Document(
                        "old-doc",
                        "old.pdf",
                        (
                            Page(1),
                        ),
                    )
                ),
                new_document=(
                    Document(
                        "new-doc",
                        "new.pdf",
                        (),
                    )
                ),
                previous_semantic=(
                    semantic()
                ),
                estimate_id="est",
                actor_id="estimator",
                city="Dallas",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                markup=(
                    SimpleNamespace()
                ),
            )
        )

        self.assertEqual(
            service
            .semantic_resolver
            .calls,
            [],
        )

        self.assertEqual(
            result
            .semantic
            .candidates,
            (),
        )

    def test_execute_pdfs_ingests_both_sets(self):
        old_document = (
            Document(
                "old-doc",
                "old.pdf",
                (
                    Page(1),
                ),
            )
        )

        new_document = (
            Document(
                "new-doc",
                "new.pdf",
                (
                    Page(1),
                ),
            )
        )

        ingest = (
            FakePdfIngest(
                (
                    old_document,
                    new_document,
                )
            )
        )

        service = (
            RevisionExecutionCoordinator(
                workflow=(
                    SimpleNamespace()
                ),
                pricing_service=(
                    FakePricingService(
                        pricing()
                    )
                ),
                revision_engine=(
                    FakeRevisionEngine(
                        Impact(
                            no_change=True
                        )
                    )
                ),
                semantic_resolver=(
                    FakeSemanticResolver(
                        semantic()
                    )
                ),
                lifecycle=(
                    FakeLifecycle(
                        lifecycle_result()
                    )
                ),
                pdf_ingest=ingest,
            )
        )

        service.execute_pdfs(
            old_path="old.pdf",
            new_path="new.pdf",
            previous_semantic=(
                semantic()
            ),
            estimate_id="est",
            actor_id="estimator",
            city="Dallas",
            as_of=date(
                2026,
                8,
                15,
            ),
            markup=(
                SimpleNamespace()
            ),
        )

        self.assertEqual(
            ingest.calls,
            [
                (
                    "old.pdf",
                    None,
                ),
                (
                    "new.pdf",
                    None,
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
