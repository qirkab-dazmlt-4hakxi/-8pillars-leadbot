import tempfile
import unittest

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import leadbot_v2.goat.preconstruction.pdf_ingest.engine as pdf_module

from leadbot_v2.goat.preconstruction.integration.vector_takeoff import (
    PdfVectorTakeoffBridge,
    Severity,
    TradeKind,
    parse_scale,
    trade_from_sheet,
)

from leadbot_v2.goat.preconstruction.pdf_ingest.engine import (
    PdfIngestEngine,
    PdfIngestError,
    PdfPageKind,
)


class FakePoint:
    def __init__(
        self,
        x,
        y,
    ):
        self.x = x
        self.y = y


class FakeRect:
    def __init__(
        self,
        x0,
        y0,
        x1,
        y1,
    ):
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    @property
    def width(self):
        return (
            self.x1
            - self.x0
        )

    @property
    def height(self):
        return (
            self.y1
            - self.y0
        )


class FakePage:
    def __init__(
        self,
        *,
        text="",
        drawings=(),
        images=(),
    ):
        self.rect = FakeRect(
            0,
            0,
            1728,
            2592,
        )

        self.rotation = 0
        self.text = text
        self.drawings = drawings
        self.images = images

    def get_text(
        self,
        mode,
    ):
        if mode == "text":
            return self.text

        if mode == "dict":
            return {
                "blocks": [
                    {
                        "type": 0,
                        "lines": [
                            {
                                "spans": [
                                    {
                                        "text":
                                            self.text,
                                        "bbox":
                                            (
                                                10,
                                                10,
                                                500,
                                                40,
                                            ),
                                        "font":
                                            "Arial",
                                        "size":
                                            10,
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }

        raise AssertionError(
            mode
        )

    def get_drawings(self):
        return self.drawings

    def get_images(
        self,
        full=False,
    ):
        return self.images


class FakeDocument:
    def __init__(
        self,
        pages,
    ):
        self.pages = list(
            pages
        )

        self.page_count = len(
            self.pages
        )

        self.needs_pass = False

    def __getitem__(
        self,
        index,
    ):
        return self.pages[
            index
        ]

    def close(self):
        pass


class FakeFitz:
    document = None

    @classmethod
    def open(
        cls,
        path,
    ):
        return cls.document


def fake_pdf() -> Path:
    handle = (
        tempfile
        .NamedTemporaryFile(
            suffix=".pdf",
            delete=False,
        )
    )

    handle.write(
        b"%PDF-1.7\nGOAT\n"
    )

    handle.close()

    return Path(
        handle.name
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
    source_ref: str


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


@dataclass(frozen=True)
class BridgePage:
    page_number: int
    text: str
    source_ref: str
    sheet_hint: str | None
    scale_text: str | None
    segments: tuple = ()
    rectangles: tuple = ()


@dataclass(frozen=True)
class BridgeDocument:
    document_id: str
    pages: tuple


class ScaleTests(
    unittest.TestCase
):

    def test_eighth_scale(self):
        scale = parse_scale(
            '1/8" = 1\'-0"'
        )

        self.assertAlmostEqual(
            scale.feet_per_paper_inch,
            8.0,
        )

    def test_quarter_scale(self):
        scale = parse_scale(
            '1/4" = 1\'-0"'
        )

        self.assertAlmostEqual(
            scale.feet_per_paper_inch,
            4.0,
        )

    def test_engineering_scale(self):
        scale = parse_scale(
            '1" = 20\''
        )

        self.assertAlmostEqual(
            scale.feet_per_paper_inch,
            20.0,
        )

    def test_nts_rejected(self):
        self.assertIsNone(
            parse_scale(
                "NOT TO SCALE"
            )
        )


class RoutingTests(
    unittest.TestCase
):

    def test_structural(self):
        self.assertEqual(
            trade_from_sheet(
                "S2.1"
            ),
            TradeKind.CONCRETE,
        )

    def test_civil(self):
        self.assertEqual(
            trade_from_sheet(
                "C3.1"
            ),
            TradeKind.EARTHWORK,
        )

    def test_electrical(self):
        self.assertEqual(
            trade_from_sheet(
                "E2.1"
            ),
            TradeKind.ELECTRICAL,
        )

    def test_plumbing(self):
        self.assertEqual(
            trade_from_sheet(
                "P2.1"
            ),
            TradeKind.PLUMBING,
        )


class NativePdfTests(
    unittest.TestCase
):

    def test_invalid_pdf_rejected(self):
        with tempfile.NamedTemporaryFile(
            delete=False,
        ) as handle:
            handle.write(
                b"NOT PDF"
            )

            path = Path(
                handle.name
            )

        with self.assertRaises(
            PdfIngestError
        ):
            (
                PdfIngestEngine()
                ._validate_file(
                    path
                )
            )

    def test_vector_ingestion(self):
        path = fake_pdf()

        page = FakePage(
            text=(
                "SHEET S2.1\n"
                'SCALE 1/8" = 1\'-0"'
            ),
            drawings=(
                {
                    "width": 1,
                    "items": (
                        (
                            "l",
                            FakePoint(
                                0,
                                0,
                            ),
                            FakePoint(
                                72,
                                0,
                            ),
                        ),
                        (
                            "re",
                            FakeRect(
                                0,
                                0,
                                72,
                                72,
                            ),
                        ),
                    ),
                },
            ),
        )

        FakeFitz.document = (
            FakeDocument(
                [page]
            )
        )

        with patch.object(
            pdf_module,
            "fitz",
            FakeFitz,
        ):
            result = (
                PdfIngestEngine()
                .ingest(
                    path
                )
            )

        self.assertEqual(
            result.page_count,
            1,
        )

        self.assertEqual(
            result.pages[0]
            .page_kind,
            PdfPageKind.VECTOR,
        )

        self.assertEqual(
            len(
                result.pages[0]
                .segments
            ),
            1,
        )

        self.assertEqual(
            len(
                result.pages[0]
                .rectangles
            ),
            1,
        )

        self.assertEqual(
            result.pages[0]
            .sheet_hint,
            "S2.1",
        )


class BridgeTests(
    unittest.TestCase
):

    def test_pdf_line_to_real_lf(self):
        document = BridgeDocument(
            "doc",
            (
                BridgePage(
                    1,
                    'SHEET S2.1\nSCALE 1/8" = 1\'-0"',
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    segments=(
                        Segment(
                            "s1",
                            (0, 0),
                            (72, 0),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            PdfVectorTakeoffBridge()
            .analyze(
                document
            )
        )

        candidate = (
            result.candidates[0]
        )

        self.assertEqual(
            candidate.unit,
            "LF",
        )

        self.assertAlmostEqual(
            candidate.quantity,
            8.0,
        )

    def test_pdf_rectangle_to_real_sf(self):
        document = BridgeDocument(
            "doc",
            (
                BridgePage(
                    1,
                    'SHEET S2.1\nSCALE 1/8" = 1\'-0"',
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    rectangles=(
                        Rectangle(
                            "r1",
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
            PdfVectorTakeoffBridge()
            .analyze(
                document
            )
        )

        candidate = (
            result.candidates[0]
        )

        self.assertEqual(
            candidate.unit,
            "SF",
        )

        self.assertAlmostEqual(
            candidate.quantity,
            64.0,
        )

    def test_missing_scale_blocks(self):
        document = BridgeDocument(
            "doc",
            (
                BridgePage(
                    1,
                    "SHEET S2.1",
                    "plans#1",
                    "S2.1",
                    None,
                    segments=(
                        Segment(
                            "s1",
                            (0, 0),
                            (72, 0),
                            "plans#1",
                        ),
                    ),
                ),
            ),
        )

        result = (
            PdfVectorTakeoffBridge()
            .analyze(
                document
            )
        )

        self.assertTrue(
            result.blockers
        )

        self.assertEqual(
            result.blockers[0]
            .severity,
            Severity.BLOCKER,
        )

    def test_source_provenance_survives(self):
        source = (
            "plans.pdf"
            "#sha256=abc"
            "&page=7"
        )

        document = BridgeDocument(
            "doc",
            (
                BridgePage(
                    7,
                    'SHEET E2.1\nSCALE 1/8" = 1\'-0"',
                    source,
                    "E2.1",
                    '1/8" = 1\'-0"',
                    segments=(
                        Segment(
                            "e1",
                            (0, 0),
                            (72, 0),
                            source,
                        ),
                    ),
                ),
            ),
        )

        result = (
            PdfVectorTakeoffBridge()
            .analyze(
                document
            )
        )

        self.assertEqual(
            result.candidates[0]
            .source_ref,
            source,
        )

    def test_geometry_remains_review_gated(self):
        document = BridgeDocument(
            "doc",
            (
                BridgePage(
                    1,
                    'SHEET S2.1\nSCALE 1/8" = 1\'-0"',
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                    rectangles=(
                        Rectangle(
                            "r1",
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
            PdfVectorTakeoffBridge()
            .analyze(
                document
            )
        )

        self.assertTrue(
            result.candidates[0]
            .requires_review
        )

        self.assertFalse(
            result
            .ready_for_final_pricing
        )

    def test_conflicting_sheet_scales_block(self):
        document = BridgeDocument(
            "doc",
            (
                BridgePage(
                    1,
                    'SHEET S2.1\nSCALE 1/8" = 1\'-0"',
                    "plans#1",
                    "S2.1",
                    '1/8" = 1\'-0"',
                ),
                BridgePage(
                    2,
                    'SHEET S2.1\nSCALE 1/4" = 1\'-0"',
                    "plans#2",
                    "S2.1",
                    '1/4" = 1\'-0"',
                ),
            ),
        )

        result = (
            PdfVectorTakeoffBridge()
            .analyze(
                document
            )
        )

        self.assertIn(
            "CONFLICTING_SHEET_SCALE",
            {
                item.code
                for item
                in result.blockers
            },
        )


if __name__ == "__main__":
    unittest.main()
