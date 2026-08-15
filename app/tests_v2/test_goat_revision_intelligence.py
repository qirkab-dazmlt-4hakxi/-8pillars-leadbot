import unittest

from dataclasses import dataclass

from leadbot_v2.goat.preconstruction.integration.vector_takeoff import (
    TradeKind,
)

from leadbot_v2.goat.preconstruction.revisions.intelligence import (
    PlanRevisionEngine,
    RevisionAspect,
    RevisionRerunPlanner,
    RevisionSeverity,
    RerunStage,
    SheetChangeKind,
    extract_revision_markers,
    fingerprint_page,
)


@dataclass(frozen=True)
class Segment:
    segment_id: str

    start: tuple[
        float,
        float,
    ]

    end: tuple[
        float,
        float,
    ]

    width_points: float = 1.0


@dataclass(frozen=True)
class Rectangle:
    rectangle_id: str

    bbox: tuple[
        float,
        float,
        float,
        float,
    ]

    width_points: float = 1.0


@dataclass(frozen=True)
class Page:
    page_number: int

    sheet_hint: str | None

    text: str

    scale_text: str | None

    source_ref: str

    segments: tuple = ()

    rectangles: tuple = ()


@dataclass(frozen=True)
class Document:
    document_id: str

    pages: tuple


@dataclass(frozen=True)
class SemanticCandidate:
    candidate_id: str

    page_number: int


@dataclass(frozen=True)
class SemanticTakeoff:
    candidates: tuple


def page(
    number,
    sheet,
    *,
    text=None,
    scale='1/8" = 1\'-0"',
    segment_end=72,
    source=None,
):
    if text is None:
        text = (
            f"SHEET {sheet}\n"
            "FOUNDATION PLAN\n"
            f"SCALE {scale}"
        )

    return Page(
        page_number=number,
        sheet_hint=sheet,
        text=text,
        scale_text=scale,
        source_ref=(
            source
            or f"plans#page={number}"
        ),
        segments=(
            Segment(
                segment_id=(
                    f"segment-{number}"
                ),
                start=(
                    0,
                    0,
                ),
                end=(
                    segment_end,
                    0,
                ),
            ),
        ),
    )


class FingerprintTests(
    unittest.TestCase
):

    def test_fingerprint_is_stable(self):
        first = (
            fingerprint_page(
                page(
                    1,
                    "S2.1",
                )
            )
        )

        second = (
            fingerprint_page(
                page(
                    1,
                    "S2.1",
                )
            )
        )

        self.assertEqual(
            first.combined_hash,
            second.combined_hash,
        )

    def test_reversed_line_is_same_geometry(self):
        first_page = Page(
            page_number=1,
            sheet_hint="S2.1",
            text="SHEET S2.1",
            scale_text=(
                '1/8" = 1\'-0"'
            ),
            source_ref="old#1",
            segments=(
                Segment(
                    "a",
                    (
                        0,
                        0,
                    ),
                    (
                        72,
                        0,
                    ),
                ),
            ),
        )

        second_page = Page(
            page_number=1,
            sheet_hint="S2.1",
            text="SHEET S2.1",
            scale_text=(
                '1/8" = 1\'-0"'
            ),
            source_ref="new#1",
            segments=(
                Segment(
                    "b",
                    (
                        72,
                        0,
                    ),
                    (
                        0,
                        0,
                    ),
                ),
            ),
        )

        self.assertEqual(
            fingerprint_page(
                first_page
            ).geometry_hash,
            fingerprint_page(
                second_page
            ).geometry_hash,
        )

    def test_revision_markers(self):
        markers = (
            extract_revision_markers(
                "REV 3\n"
                "ADDENDUM 2\n"
                "ISSUED FOR BID"
            )
        )

        self.assertIn(
            "REV 3",
            markers,
        )

        self.assertIn(
            "ADDENDUM 2",
            markers,
        )

        self.assertIn(
            "ISSUED FOR BID",
            markers,
        )


class ComparisonTests(
    unittest.TestCase
):

    def test_identical_sheet_unchanged(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        self.assertTrue(
            result.no_change
        )

        self.assertEqual(
            result.deltas[0]
            .change_kind,
            SheetChangeKind
            .UNCHANGED,
        )

    def test_page_reorder_does_not_create_revision(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                    source="old#1",
                ),
                page(
                    2,
                    "E2.1",
                    text=(
                        "SHEET E2.1\n"
                        "POWER PLAN\n"
                        'SCALE 1/8" = 1\'-0"'
                    ),
                    source="old#2",
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "E2.1",
                    text=(
                        "SHEET E2.1\n"
                        "POWER PLAN\n"
                        'SCALE 1/8" = 1\'-0"'
                    ),
                    source="new#1",
                ),
                page(
                    2,
                    "S2.1",
                    source="new#2",
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        self.assertTrue(
            result.no_change
        )

    def test_geometry_change_requires_geometry_rerun(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=72,
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=144,
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        delta = (
            result
            .changed_sheets[0]
        )

        self.assertIn(
            RevisionAspect
            .VECTOR_GEOMETRY,
            delta.aspects,
        )

        self.assertEqual(
            delta.rerun_stage,
            RerunStage.GEOMETRY,
        )

    def test_scale_change_requires_full_sheet_rerun(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                    scale=(
                        '1/8" = 1\'-0"'
                    ),
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                    scale=(
                        '1/4" = 1\'-0"'
                    ),
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        delta = (
            result
            .changed_sheets[0]
        )

        self.assertIn(
            RevisionAspect.SCALE,
            delta.aspects,
        )

        self.assertEqual(
            delta.rerun_stage,
            RerunStage.FULL_SHEET,
        )

        self.assertIn(
            "DRAWING_SCALE_CHANGED",
            {
                finding.code
                for finding
                in result.findings
            },
        )

    def test_text_change_requires_semantic_rerun(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                    text=(
                        "SHEET S2.1\n"
                        "6 IN SOG"
                    ),
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                    text=(
                        "SHEET S2.1\n"
                        "8 IN SOG"
                    ),
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        self.assertEqual(
            result
            .changed_sheets[0]
            .rerun_stage,
            RerunStage.SEMANTIC,
        )

    def test_added_sheet_detected(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                ),
                page(
                    2,
                    "S3.1",
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        kinds = {
            delta.change_kind
            for delta
            in result.deltas
        }

        self.assertIn(
            SheetChangeKind.ADDED,
            kinds,
        )

        self.assertIn(
            "SHEET_ADDED",
            {
                finding.code
                for finding
                in result.findings
            },
        )

    def test_removed_sheet_detected(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                ),
                page(
                    2,
                    "S3.1",
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        self.assertIn(
            SheetChangeKind.REMOVED,
            {
                delta.change_kind
                for delta
                in result.deltas
            },
        )


class InvalidationTests(
    unittest.TestCase
):

    def test_changed_old_page_invalidates_prior_candidates(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=72,
                ),
                page(
                    2,
                    "E2.1",
                    text=(
                        "SHEET E2.1\n"
                        "POWER PLAN"
                    ),
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=144,
                ),
                page(
                    2,
                    "E2.1",
                    text=(
                        "SHEET E2.1\n"
                        "POWER PLAN"
                    ),
                ),
            ),
        )

        previous = (
            SemanticTakeoff(
                candidates=(
                    SemanticCandidate(
                        "structural-1",
                        1,
                    ),
                    SemanticCandidate(
                        "electrical-1",
                        2,
                    ),
                )
            )
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
                previous_semantic=(
                    previous
                ),
            )
        )

        self.assertEqual(
            result
            .invalidated_candidate_ids,
            (
                "structural-1",
            ),
        )

    def test_removed_sheet_invalidates_old_scope(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                ),
                page(
                    2,
                    "S3.1",
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        previous = (
            SemanticTakeoff(
                candidates=(
                    SemanticCandidate(
                        "wall-scope",
                        2,
                    ),
                )
            )
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
                previous_semantic=(
                    previous
                ),
            )
        )

        self.assertEqual(
            result
            .invalidated_candidate_ids,
            (
                "wall-scope",
            ),
        )


class AssuranceTests(
    unittest.TestCase
):

    def test_duplicate_sheet_id_blocks_incremental_matching(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                ),
                page(
                    2,
                    "S2.1",
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        self.assertTrue(
            result.blockers
        )

        self.assertTrue(
            result.requires_full_rerun
        )

        self.assertFalse(
            result
            .can_incrementally_rerun
        )

    def test_vector_sheet_without_sheet_id_blocks(self):
        old_page = Page(
            page_number=1,
            sheet_hint=None,
            text="FOUNDATION PLAN",
            scale_text=(
                '1/8" = 1\'-0"'
            ),
            source_ref="old#1",
            segments=(
                Segment(
                    "a",
                    (
                        0,
                        0,
                    ),
                    (
                        72,
                        0,
                    ),
                ),
            ),
        )

        new_page = Page(
            page_number=1,
            sheet_hint=None,
            text="FOUNDATION PLAN",
            scale_text=(
                '1/8" = 1\'-0"'
            ),
            source_ref="new#1",
            segments=(
                Segment(
                    "b",
                    (
                        0,
                        0,
                    ),
                    (
                        72,
                        0,
                    ),
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=(
                    Document(
                        "old",
                        (
                            old_page,
                        )
                    )
                ),
                new_document=(
                    Document(
                        "new",
                        (
                            new_page,
                        )
                    )
                ),
            )
        )

        self.assertIn(
            "VECTOR_SHEET_ID_MISSING",
            {
                finding.code
                for finding
                in result.blockers
            },
        )

    def test_geometry_trade_impact(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=72,
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=144,
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        self.assertEqual(
            result.impacted_trades,
            (
                TradeKind.CONCRETE,
            ),
        )


class RerunPlannerTests(
    unittest.TestCase
):

    def test_incremental_plan(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=72,
                ),
                page(
                    2,
                    "E2.1",
                    text=(
                        "SHEET E2.1\n"
                        "POWER PLAN"
                    ),
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                    segment_end=144,
                ),
                page(
                    2,
                    "E2.1",
                    text=(
                        "SHEET E2.1\n"
                        "POWER PLAN"
                    ),
                ),
            ),
        )

        result = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        plan = (
            RevisionRerunPlanner
            .execution_plan(
                result
            )
        )

        self.assertEqual(
            plan[
                "mode"
            ],
            "incremental",
        )

        self.assertEqual(
            plan[
                "pages"
            ],
            (
                1,
            ),
        )

        self.assertEqual(
            plan[
                "trades"
            ],
            (
                "concrete",
            ),
        )

    def test_no_change_plan(self):
        old = Document(
            "old",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        new = Document(
            "new",
            (
                page(
                    1,
                    "S2.1",
                ),
            ),
        )

        impact = (
            PlanRevisionEngine()
            .compare(
                old_document=old,
                new_document=new,
            )
        )

        plan = (
            RevisionRerunPlanner
            .execution_plan(
                impact
            )
        )

        self.assertEqual(
            plan[
                "mode"
            ],
            "no_change",
        )


if __name__ == "__main__":
    unittest.main()
