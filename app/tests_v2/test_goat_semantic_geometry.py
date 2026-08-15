import unittest

from dataclasses import dataclass

from leadbot_v2.goat.preconstruction.semantic.geometry import (
    GeometryKind,
    SemanticGeometryResolver,
    SemanticKind,
)


@dataclass(frozen=True)
class Span:
    text: str
    bbox: tuple[
        float,
        float,
        float,
        float,
    ]


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
    source_ref: str

    @property
    def length_points(self):
        dx = (
            self.end[0]
            - self.start[0]
        )

        dy = (
            self.end[1]
            - self.start[1]
        )

        return (
            dx * dx
            + dy * dy
        ) ** 0.5


@dataclass(frozen=True)
class Rectangle:
    rectangle_id: str
    bbox: tuple[
        float,
        float,
        float,
        float,
    ]
    source_ref: str

    @property
    def area_points2(self):
        x0, y0, x1, y1 = (
            self.bbox
        )

        return abs(
            (x1 - x0)
            * (y1 - y0)
        )


@dataclass(frozen=True)
class Page:
    page_number: int
    text: str
    source_ref: str
    sheet_hint: str
    scale_text: str
    text_spans: tuple
    segments: tuple = ()
    rectangles: tuple = ()


@dataclass(frozen=True)
class Document:
    document_id: str
    pages: tuple


def resolver():
    return (
        SemanticGeometryResolver()
    )


class ConcreteSemanticTests(
    unittest.TestCase
):

    def test_nearby_sog_classifies_slab(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET S2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        '6" SOG'
                    ),
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            '6" SOG',
                            (
                                20,
                                20,
                                100,
                                50,
                            ),
                        ),
                    ),
                    rectangles=(
                        Rectangle(
                            "slab-1",
                            (
                                0,
                                0,
                                72,
                                72,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        item = (
            result.candidates[0]
        )

        self.assertEqual(
            item.semantic_kind,
            SemanticKind.SLAB,
        )

        self.assertEqual(
            item.geometry_kind,
            GeometryKind.AREA,
        )

        self.assertTrue(
            item.auto_classified
        )

    def test_slab_thickness_creates_cy(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET S2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        '6" SOG'
                    ),
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            '6" SOG',
                            (
                                20,
                                20,
                                100,
                                50,
                            ),
                        ),
                    ),
                    rectangles=(
                        Rectangle(
                            "slab-1",
                            (
                                0,
                                0,
                                72,
                                72,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        item = (
            result.candidates[0]
        )

        # 64 SF * 0.5 FT / 27
        self.assertAlmostEqual(
            item.derived_volume_cy,
            64 * 0.5 / 27,
        )

    def test_grade_beam_line(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET S2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        "GRADE BEAM"
                    ),
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            'GRADE BEAM 24" x 36"',
                            (
                                20,
                                0,
                                140,
                                30,
                            ),
                        ),
                    ),
                    segments=(
                        Segment(
                            "gb-1",
                            (
                                0,
                                20,
                            ),
                            (
                                72,
                                20,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        item = (
            result.candidates[0]
        )

        self.assertEqual(
            item.semantic_kind,
            SemanticKind.GRADE_BEAM,
        )

    def test_retaining_wall_line(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET S3.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        "RETAINING WALL"
                    ),
                    "plans#1",
                    "S3.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            "RETAINING WALL",
                            (
                                25,
                                0,
                                150,
                                30,
                            ),
                        ),
                    ),
                    segments=(
                        Segment(
                            "wall-1",
                            (
                                0,
                                20,
                            ),
                            (
                                72,
                                20,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertEqual(
            result.candidates[0]
            .semantic_kind,
            SemanticKind.CONCRETE_WALL,
        )


class CivilSemanticTests(
    unittest.TestCase
):

    def test_utility_trench(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET C3.1\n"
                        'SCALE 1" = 20\'\n'
                        "UTILITY TRENCH"
                    ),
                    "civil#1",
                    "C3.1",
                    '1" = 20\'',
                    (
                        Span(
                            "UTILITY TRENCH",
                            (
                                20,
                                0,
                                150,
                                30,
                            ),
                        ),
                    ),
                    segments=(
                        Segment(
                            "trench-1",
                            (
                                0,
                                20,
                            ),
                            (
                                72,
                                20,
                            ),
                            "civil#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertEqual(
            result.candidates[0]
            .semantic_kind,
            SemanticKind.TRENCH,
        )


class MEPSemanticTests(
    unittest.TestCase
):

    def test_emt_feeder_is_conduit(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET E2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        '2" EMT FEEDER'
                    ),
                    "electrical#1",
                    "E2.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            '2" EMT FEEDER',
                            (
                                10,
                                0,
                                130,
                                30,
                            ),
                        ),
                    ),
                    segments=(
                        Segment(
                            "e1",
                            (
                                0,
                                20,
                            ),
                            (
                                72,
                                20,
                            ),
                            "electrical#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        item = (
            result.candidates[0]
        )

        self.assertEqual(
            item.semantic_kind,
            SemanticKind.CONDUIT_RUN,
        )

        self.assertTrue(
            item.auto_classified
        )

    def test_sanitary_is_pipe(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET P2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        '4" PVC SANITARY'
                    ),
                    "plumbing#1",
                    "P2.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            '4" PVC SANITARY',
                            (
                                10,
                                0,
                                150,
                                30,
                            ),
                        ),
                    ),
                    segments=(
                        Segment(
                            "p1",
                            (
                                0,
                                20,
                            ),
                            (
                                72,
                                20,
                            ),
                            "plumbing#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertEqual(
            result.candidates[0]
            .semantic_kind,
            SemanticKind.PIPE_RUN,
        )


class AssuranceTests(
    unittest.TestCase
):

    def test_unrelated_geometry_stays_unresolved(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET S2.1\n"
                        'SCALE 1/8" = 1\'-0"'
                    ),
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    (),
                    segments=(
                        Segment(
                            "unknown",
                            (
                                0,
                                0,
                            ),
                            (
                                72,
                                0,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertEqual(
            result.candidates[0]
            .semantic_kind,
            SemanticKind.UNRESOLVED,
        )

        self.assertTrue(
            result.candidates[0]
            .requires_review
        )

    def test_page_level_text_cannot_auto_classify(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET S2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        "GRADE BEAM"
                    ),
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    (),
                    segments=(
                        Segment(
                            "gb",
                            (
                                0,
                                0,
                            ),
                            (
                                72,
                                0,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertFalse(
            result.candidates[0]
            .auto_classified
        )

    def test_far_text_does_not_get_proximity_credit(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    (
                        "SHEET E2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        "EMT FEEDER"
                    ),
                    "plans#1",
                    "E2.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            "EMT FEEDER",
                            (
                                2000,
                                2000,
                                2100,
                                2030,
                            ),
                        ),
                    ),
                    segments=(
                        Segment(
                            "e1",
                            (
                                0,
                                0,
                            ),
                            (
                                72,
                                0,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertTrue(
            result.candidates[0]
            .requires_review
        )

    def test_source_provenance_preserved(self):
        source = (
            "plans.pdf"
            "#sha256=abc"
            "&page=4"
        )

        document = Document(
            "doc",
            (
                Page(
                    4,
                    (
                        "SHEET P2.1\n"
                        'SCALE 1/8" = 1\'-0"\n'
                        "SANITARY"
                    ),
                    source,
                    "P2.1",
                    '1/8" = 1\'-0"',
                    (
                        Span(
                            "SANITARY",
                            (
                                10,
                                0,
                                100,
                                30,
                            ),
                        ),
                    ),
                    segments=(
                        Segment(
                            "p1",
                            (
                                0,
                                20,
                            ),
                            (
                                72,
                                20,
                            ),
                            source,
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertEqual(
            result.candidates[0]
            .source_ref,
            source,
        )

    def test_missing_scale_propagates_blocker(self):
        document = Document(
            "doc",
            (
                Page(
                    1,
                    "SHEET S2.1",
                    "plans#1",
                    "S2.1",
                    None,
                    (),
                    segments=(
                        Segment(
                            "s1",
                            (
                                0,
                                0,
                            ),
                            (
                                72,
                                0,
                            ),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            resolver().resolve(
                document
            )
        )

        self.assertTrue(
            result.blockers
        )


if __name__ == "__main__":
    unittest.main()
