import unittest

from dataclasses import dataclass
from types import SimpleNamespace

from leadbot_v2.goat.preconstruction.revisions.lifecycle import (
    EstimateRevisionLifecycle,
    RevisionReviewSeverity,
)


@dataclass
class Line:
    line_id: str
    description: str
    cost_code: str
    direct_cost_cents: int
    bid_price_cents: int
    source_refs: tuple


@dataclass
class Version:
    version_id: str
    version_number: int
    status: str
    lines: tuple
    overrides: tuple = ()


@dataclass
class Candidate:
    candidate_id: str
    page_number: int


@dataclass
class Semantic:
    candidates: tuple


@dataclass
class Provenance:
    source_ref: str
    geometry_ids: tuple
    text_refs: tuple
    rate_refs: tuple


class Scope:
    def __init__(
        self,
        candidate_id,
        *,
        direct=12000,
        bid=15000,
        ready=True,
        review=False,
        page=1,
    ):
        self.semantic_candidate_id = (
            candidate_id
        )
        self.description = (
            "Revised concrete scope"
        )
        self.cost_code = "03-3000"
        self.quantity = 10.0
        self.unit = "CY"
        self.direct_cost_cents = (
            direct
            if ready
            else None
        )
        self.bid_price_cents = (
            bid
            if ready
            else None
        )
        self.ready_for_estimate = ready
        self.requires_review = review
        self.confidence = 0.97
        self.unresolved_reason = (
            None
            if ready
            else "PRICE_UNRESOLVED"
        )
        self.provenance = Provenance(
            source_ref=(
                f"new.pdf#page={page}"
            ),
            geometry_ids=(
                candidate_id,
            ),
            text_refs=(
                f"new.pdf#page={page}#span=1",
            ),
            rate_refs=(
                "rate:verified",
            ),
        )


class Pricing:
    def __init__(
        self,
        scopes,
    ):
        self.scopes = tuple(
            scopes
        )


class Delta:
    def __init__(
        self,
        *,
        old_page=1,
        new_page=1,
        old_ref="plans.pdf#page=1",
        new_ref="new.pdf#page=1",
    ):
        self.old_page_number = old_page
        self.new_page_number = new_page
        self.old_source_ref = old_ref
        self.new_source_ref = new_ref


class Impact:
    def __init__(
        self,
        *,
        changed=True,
        blockers=(),
        old_pages=(1,),
        new_pages=(1,),
        invalidated=(
            "old-candidate",
        ),
    ):
        self.blockers = tuple(
            blockers
        )
        self.impacted_old_pages = tuple(
            old_pages
        )
        self.impacted_new_pages = tuple(
            new_pages
        )
        self.invalidated_candidate_ids = tuple(
            invalidated
        )
        self.changed_sheets = (
            (
                Delta()
                if changed
                else None
            ),
        ) if changed else ()
        self.no_change = not changed


class FakeWorkflow:
    def __init__(
        self,
        version,
    ):
        self.version = version
        self.created = 0
        self.override_calls = []
        self.add_calls = []

    def current_version(
        self,
        estimate_id,
    ):
        return self.version

    def create_revision(
        self,
        *,
        estimate_id,
        actor_id,
    ):
        self.created += 1

        self.version = Version(
            version_id=(
                f"v{self.created + 1}"
            ),
            version_number=(
                self.version
                .version_number
                + 1
            ),
            status="draft",
            lines=(
                self.version.lines
            ),
            overrides=(
                self.version.overrides
            ),
        )

        return self.version

    def override_line(
        self,
        **kwargs,
    ):
        self.override_calls.append(
            kwargs
        )

        override = (
            SimpleNamespace(
                line_id=(
                    kwargs[
                        "line_id"
                    ]
                ),
                new_direct_cost_cents=(
                    kwargs[
                        "new_direct_cost_cents"
                    ]
                ),
                new_bid_price_cents=(
                    kwargs[
                        "new_bid_price_cents"
                    ]
                ),
            )
        )

        self.version = Version(
            version_id=(
                self.version
                .version_id
            ),
            version_number=(
                self.version
                .version_number
            ),
            status=(
                self.version.status
            ),
            lines=(
                self.version.lines
            ),
            overrides=(
                self.version.overrides
                + (
                    override,
                )
            ),
        )

        return override

    def add_manual_line(
        self,
        **kwargs,
    ):
        self.add_calls.append(
            kwargs
        )

        line = Line(
            line_id=(
                f"new-line-"
                f"{len(self.add_calls)}"
            ),
            description=(
                kwargs[
                    "description"
                ]
            ),
            cost_code=(
                kwargs[
                    "cost_code"
                ]
            ),
            direct_cost_cents=(
                kwargs[
                    "direct_cost_cents"
                ]
            ),
            bid_price_cents=(
                kwargs[
                    "bid_price_cents"
                ]
            ),
            source_refs=(
                kwargs[
                    "source_refs"
                ]
            ),
        )

        self.version = Version(
            version_id=(
                self.version
                .version_id
            ),
            version_number=(
                self.version
                .version_number
            ),
            status=(
                self.version.status
            ),
            lines=(
                self.version.lines
                + (
                    line,
                )
            ),
            overrides=(
                self.version
                .overrides
            ),
        )

        return line


def old_version(
    *,
    status="draft",
):
    return Version(
        version_id="v1",
        version_number=1,
        status=status,
        lines=(
            Line(
                line_id="affected",
                description="Old slab",
                cost_code="03-3000",
                direct_cost_cents=10000,
                bid_price_cents=13000,
                source_refs=(
                    "plans.pdf#page=1",
                    "old-candidate",
                ),
            ),
            Line(
                line_id="unaffected",
                description="Electrical",
                cost_code="26-0000",
                direct_cost_cents=5000,
                bid_price_cents=7000,
                source_refs=(
                    "plans.pdf#page=2",
                    "electrical-candidate",
                ),
            ),
        ),
    )


def semantic(
    *,
    candidate_id="new-candidate",
    page=1,
):
    return Semantic(
        candidates=(
            Candidate(
                candidate_id,
                page,
            ),
        )
    )


class RevisionLifecycleTests(
    unittest.TestCase
):

    def test_creates_new_revision(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est-1",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate"
                        ),
                    )
                ),
            )
        )

        self.assertTrue(
            result.changed
        )

        self.assertEqual(
            workflow.created,
            1,
        )

        self.assertEqual(
            result
            .revised_version_number,
            2,
        )

    def test_impacted_line_is_zeroed_by_override(self):
        workflow = FakeWorkflow(
            old_version()
        )

        (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate"
                        ),
                    )
                ),
            )
        )

        self.assertEqual(
            len(
                workflow
                .override_calls
            ),
            1,
        )

        call = (
            workflow
            .override_calls[0]
        )

        self.assertEqual(
            call[
                "line_id"
            ],
            "affected",
        )

        self.assertEqual(
            call[
                "new_bid_price_cents"
            ],
            0,
        )

    def test_unaffected_line_is_preserved(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate"
                        ),
                    )
                ),
            )
        )

        self.assertEqual(
            result
            .preserved_line_ids,
            (
                "unaffected",
            ),
        )

    def test_replacement_scope_is_added(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate"
                        ),
                    )
                ),
            )
        )

        self.assertEqual(
            len(
                result
                .replacement_lines
            ),
            1,
        )

        self.assertIn(
            "rate:verified",
            result
            .replacement_lines[0]
            .source_refs,
        )

    def test_delta_is_old_vs_replacement(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate",
                            direct=12000,
                            bid=16000,
                        ),
                    )
                ),
            )
        )

        self.assertEqual(
            result
            .delta
            .direct_cost_delta_cents,
            2000,
        )

        self.assertEqual(
            result
            .delta
            .bid_price_delta_cents,
            3000,
        )

    def test_unpriced_replacement_blocks_mutation(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate",
                            ready=False,
                        ),
                    )
                ),
            )
        )

        self.assertFalse(
            result.changed
        )

        self.assertEqual(
            workflow.created,
            0,
        )

        self.assertTrue(
            result.blockers
        )

    def test_review_scope_creates_review_queue(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate",
                            review=True,
                        ),
                    )
                ),
            )
        )

        self.assertTrue(
            result.changed
        )

        self.assertFalse(
            result.proposal_ready
        )

        self.assertEqual(
            result
            .review_queue[0]
            .severity,
            RevisionReviewSeverity
            .REVIEW,
        )

    def test_submitted_estimate_is_protected(self):
        workflow = FakeWorkflow(
            old_version(
                status="submitted"
            )
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate"
                        ),
                    )
                ),
            )
        )

        self.assertFalse(
            result.changed
        )

        self.assertEqual(
            workflow.created,
            0,
        )

        self.assertIn(
            "ESTIMATE_STATUS_PROTECTED",
            {
                item.code
                for item
                in result.blockers
            },
        )

    def test_awarded_estimate_is_protected(self):
        workflow = FakeWorkflow(
            old_version(
                status="awarded"
            )
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate"
                        ),
                    )
                ),
            )
        )

        self.assertFalse(
            result.changed
        )

        self.assertEqual(
            workflow.created,
            0,
        )

    def test_revision_blocker_prevents_estimate_change(self):
        blocker = (
            SimpleNamespace(
                code=(
                    "DUPLICATE_SHEET_ID"
                ),
                message=(
                    "Duplicate sheet"
                ),
                source_ref=(
                    "plans.pdf"
                ),
            )
        )

        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(
                    blockers=(
                        blocker,
                    )
                ),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate"
                        ),
                    )
                ),
            )
        )

        self.assertFalse(
            result.changed
        )

        self.assertEqual(
            workflow.created,
            0,
        )

    def test_no_change_does_not_create_revision(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(
                    changed=False
                ),
                new_semantic=semantic(),
                new_pricing=Pricing(
                    ()
                ),
            )
        )

        self.assertFalse(
            result.changed
        )

        self.assertEqual(
            workflow.created,
            0,
        )

        self.assertTrue(
            result.proposal_ready
        )

    def test_added_sheet_scope_can_be_added(self):
        workflow = FakeWorkflow(
            Version(
                version_id="v1",
                version_number=1,
                status="draft",
                lines=(),
            )
        )

        impact = Impact(
            old_pages=(),
            new_pages=(3,),
            invalidated=(),
        )

        impact.changed_sheets = (
            Delta(
                old_page=None,
                new_page=3,
                old_ref=None,
                new_ref=(
                    "new.pdf#page=3"
                ),
            ),
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=impact,
                new_semantic=semantic(
                    page=3
                ),
                new_pricing=Pricing(
                    (
                        Scope(
                            "new-candidate",
                            page=3,
                        ),
                    )
                ),
            )
        )

        self.assertTrue(
            result.changed
        )

        self.assertEqual(
            len(
                result
                .replacement_lines
            ),
            1,
        )

    def test_removed_sheet_has_no_replacement(self):
        workflow = FakeWorkflow(
            old_version()
        )

        result = (
            EstimateRevisionLifecycle(
                workflow=workflow
            )
            .apply(
                estimate_id="est",
                actor_id="estimator",
                impact=Impact(
                    new_pages=(),
                ),
                new_semantic=(
                    Semantic(
                        candidates=()
                    )
                ),
                new_pricing=(
                    Pricing(
                        ()
                    )
                ),
            )
        )

        self.assertTrue(
            result.changed
        )

        self.assertEqual(
            len(
                result
                .invalidated_lines
            ),
            1,
        )

        self.assertEqual(
            result
            .replacement_lines,
            (),
        )

        self.assertEqual(
            result
            .delta
            .bid_price_delta_cents,
            -13000,
        )


if __name__ == "__main__":
    unittest.main()
