import tempfile
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import leadbot_v2.goat.preconstruction.pdf_ingest.engine as engine_module

from leadbot_v2.goat.preconstruction.pdf_ingest.engine import (
    FindingSeverity,
    PdfIngestEngine,
    PdfIngestError,
    PdfIngestPolicy,
    PdfLimitError,
    PdfPageKind,
    PdfSecurityError,
    detect_scale_text,
    detect_sheet_hint,
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
        rotation=0,
    ):
        self.rect = FakeRect(
            0,
            0,
            1728,
            2592,
        )

        self.rotation = rotation

        self._text = text
        self._drawings = drawings
        self._images = images

    def get_text(
        self,
        kind,
    ):
        if kind == "text":
            return self._text

        if kind == "dict":
            return {
                "blocks": [
                    {
                        "type": 0,
                        "lines": [
                            {
                                "spans": [
                                    {
                                        "text": self._text,
                                        "bbox": (
                                            10,
                                            10,
                                            500,
                                            40,
                                        ),
                                        "font": "Arial",
                                        "size": 10,
                                        "flags": 0,
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }

        raise AssertionError(
            f"unexpected text kind: {kind}"
        )

    def get_drawings(self):
        return self._drawings

    def get_images(
        self,
        full=False,
    ):
        return self._images


class FakeDocument:
    def __init__(
        self,
        pages,
        *,
        needs_pass=False,
        password="secret",
    ):
        self._pages = list(
            pages
        )

        self.page_count = len(
            self._pages
        )

        self.needs_pass = (
            needs_pass
        )

        self._password = password
        self.closed = False

    def __getitem__(
        self,
        index,
    ):
        return self._pages[
            index
        ]

    def authenticate(
        self,
        password,
    ):
        return int(
            password
            == self._password
        )

    def close(self):
        self.closed = True


class FakeFitz:
    document = None

    @classmethod
    def open(
        cls,
        path,
    ):
        return cls.document


def make_pdf_file():
    handle = tempfile.NamedTemporaryFile(
        suffix=".pdf",
        delete=False,
    )

    handle.write(
        b"%PDF-1.7\n"
        b"GOAT TEST PDF\n"
    )

    handle.close()

    return Path(
        handle.name
    )


class PdfEvidenceTests(
    unittest.TestCase
):

    def test_structural_sheet_hint(self):
        self.assertEqual(
            detect_sheet_hint(
                "SHEET S2.1\n"
                "FOUNDATION PLAN"
            ),
            "S2.1",
        )

    def test_electrical_sheet_hint(self):
        self.assertEqual(
            detect_sheet_hint(
                "E4.2 POWER PLAN"
            ),
            "E4.2",
        )

    def test_architectural_scale_evidence(self):
        value = (
            detect_scale_text(
                'SCALE 1/8" = 1\'-0"'
            )
        )

        self.assertIsNotNone(
            value
        )

        self.assertIn(
            "1/8",
            value
        )

    def test_engineering_scale_evidence(self):
        value = (
            detect_scale_text(
                'SCALE 1" = 20\''
            )
        )

        self.assertIsNotNone(
            value
        )

        self.assertIn(
            "20",
            value
        )

    def test_scale_is_not_invented(self):
        self.assertIsNone(
            detect_scale_text(
                "NOT TO SCALE"
            )
        )


class PdfValidationTests(
    unittest.TestCase
):

    def test_missing_file_rejected(self):
        service = (
            PdfIngestEngine()
        )

        with self.assertRaises(
            FileNotFoundError
        ):
            service._validate_file(
                Path(
                    "/tmp/does-not-exist.pdf"
                )
            )

    def test_non_pdf_rejected(self):
        with tempfile.NamedTemporaryFile(
            delete=False,
        ) as handle:
            handle.write(
                b"NOT A PDF"
            )

            path = Path(
                handle.name
            )

        service = (
            PdfIngestEngine()
        )

        with self.assertRaises(
            PdfIngestError
        ):
            service._validate_file(
                path
            )

    def test_file_limit_enforced(self):
        path = make_pdf_file()

        service = PdfIngestEngine(
            PdfIngestPolicy(
                max_file_bytes=5,
            )
        )

        with self.assertRaises(
            PdfLimitError
        ):
            service._validate_file(
                path
            )


class PdfIngestionTests(
    unittest.TestCase
):

    def test_vector_plan_ingestion(self):
        path = make_pdf_file()

        page = FakePage(
            text=(
                "SHEET S2.1\n"
                "FOUNDATION PLAN\n"
                'SCALE 1/8" = 1\'-0"'
            ),
            drawings=(
                {
                    "width": 1.0,
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
                                144,
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
            engine_module,
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
            result.vector_page_count,
            1,
        )

        self.assertEqual(
            result.pages[0]
            .page_kind,
            PdfPageKind.VECTOR,
        )

        self.assertEqual(
            result.pages[0]
            .sheet_hint,
            "S2.1",
        )

        self.assertIsNotNone(
            result.pages[0]
            .scale_text
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

        self.assertTrue(
            result.ready_for_vector_takeoff
        )

    def test_pdf_sha256_is_stable(self):
        path = make_pdf_file()

        first = (
            PdfIngestEngine
            .fingerprint(
                path
            )
        )

        second = (
            PdfIngestEngine
            .fingerprint(
                path
            )
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            len(first),
            64,
        )

    def test_provenance_contains_page_and_hash(self):
        path = make_pdf_file()

        page = FakePage(
            text=(
                "SHEET C3.1\n"
                'SCALE 1" = 20\''
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
            engine_module,
            "fitz",
            FakeFitz,
        ):
            result = (
                PdfIngestEngine()
                .ingest(
                    path
                )
            )

        source_ref = (
            result.pages[0]
            .source_ref
        )

        self.assertIn(
            "page=1",
            source_ref,
        )

        self.assertIn(
            "sha256=",
            source_ref,
        )

    def test_raw_page_bridge(self):
        path = make_pdf_file()

        page = FakePage(
            text=(
                "SHEET E2.1\n"
                "POWER PLAN"
            )
        )

        FakeFitz.document = (
            FakeDocument(
                [page]
            )
        )

        with patch.object(
            engine_module,
            "fitz",
            FakeFitz,
        ):
            result = (
                PdfIngestEngine()
                .ingest(
                    path
                )
            )

        raw = (
            result.raw_pages
        )

        self.assertEqual(
            len(raw),
            1,
        )

        self.assertEqual(
            raw[0].page_number,
            1,
        )

        self.assertIn(
            "POWER PLAN",
            raw[0].text,
        )

    def test_raster_only_sheet_blocks_vector_takeoff(self):
        path = make_pdf_file()

        page = FakePage(
            text="",
            drawings=(),
            images=(
                ("image",),
            ),
        )

        FakeFitz.document = (
            FakeDocument(
                [page]
            )
        )

        with patch.object(
            engine_module,
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
            result.pages[0]
            .page_kind,
            PdfPageKind.RASTER,
        )

        self.assertFalse(
            result.ready_for_vector_takeoff
        )

        codes = {
            finding.code
            for finding
            in result.pages[0]
            .findings
        }

        self.assertIn(
            "RASTER_ONLY_PAGE",
            codes,
        )

    def test_missing_scale_generates_review_evidence(self):
        path = make_pdf_file()

        page = FakePage(
            text=(
                "SHEET S2.1\n"
                "FOUNDATION PLAN"
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
            engine_module,
            "fitz",
            FakeFitz,
        ):
            result = (
                PdfIngestEngine()
                .ingest(
                    path
                )
            )

        codes = {
            finding.code
            for finding
            in result.pages[0]
            .findings
        }

        self.assertIn(
            "SCALE_NOT_CONFIRMED",
            codes,
        )

    def test_encrypted_pdf_requires_password(self):
        path = make_pdf_file()

        FakeFitz.document = (
            FakeDocument(
                [
                    FakePage(
                        text=(
                            "SHEET A1.0"
                        )
                    )
                ],
                needs_pass=True,
            )
        )

        with patch.object(
            engine_module,
            "fitz",
            FakeFitz,
        ):
            with self.assertRaises(
                PdfSecurityError
            ):
                (
                    PdfIngestEngine()
                    .ingest(
                        path
                    )
                )

    def test_encrypted_pdf_accepts_valid_password(self):
        path = make_pdf_file()

        FakeFitz.document = (
            FakeDocument(
                [
                    FakePage(
                        text=(
                            "SHEET A1.0"
                        )
                    )
                ],
                needs_pass=True,
                password="goat",
            )
        )

        with patch.object(
            engine_module,
            "fitz",
            FakeFitz,
        ):
            result = (
                PdfIngestEngine()
                .ingest(
                    path,
                    password="goat",
                )
            )

        self.assertEqual(
            result.page_count,
            1,
        )

    def test_page_limit_fails_closed(self):
        path = make_pdf_file()

        FakeFitz.document = (
            FakeDocument(
                [
                    FakePage(
                        text="SHEET A1.0"
                    ),
                    FakePage(
                        text="SHEET A1.1"
                    ),
                ]
            )
        )

        service = PdfIngestEngine(
            PdfIngestPolicy(
                max_pages=1,
            )
        )

        with patch.object(
            engine_module,
            "fitz",
            FakeFitz,
        ):
            with self.assertRaises(
                PdfLimitError
            ):
                service.ingest(
                    path
                )

    def test_unsupported_geometry_not_fabricated(self):
        path = make_pdf_file()

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
                            "c",
                            FakePoint(
                                0,
                                0,
                            ),
                            FakePoint(
                                10,
                                10,
                            ),
                            FakePoint(
                                20,
                                20,
                            ),
                            FakePoint(
                                30,
                                30,
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
            engine_module,
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
            len(
                result.pages[0]
                .segments
            ),
            0,
        )

        codes = {
            finding.code
            for finding
            in result.pages[0]
            .findings
        }

        self.assertIn(
            "UNSUPPORTED_VECTOR_PRIMITIVES",
            codes,
        )

    def test_text_span_geometry_preserved(self):
        path = make_pdf_file()

        page = FakePage(
            text=(
                "SHEET P2.1\n"
                "PLUMBING PLAN"
            )
        )

        FakeFitz.document = (
            FakeDocument(
                [page]
            )
        )

        with patch.object(
            engine_module,
            "fitz",
            FakeFitz,
        ):
            result = (
                PdfIngestEngine()
                .ingest(
                    path
                )
            )

        spans = (
            result.pages[0]
            .text_spans
        )

        self.assertEqual(
            len(spans),
            1,
        )

        self.assertEqual(
            spans[0].bbox,
            (
                10.0,
                10.0,
                500.0,
                40.0,
            ),
        )


if __name__ == "__main__":
    unittest.main()
