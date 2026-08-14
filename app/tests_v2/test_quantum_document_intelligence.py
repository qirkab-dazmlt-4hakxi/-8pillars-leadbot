import unittest

from leadbot_v2.goat.preconstruction.documents.intelligence import (
    ConstructionDocumentIntelligence,
    RawPage,
)
from leadbot_v2.goat.preconstruction.documents.models import (
    Discipline,
    ScaleState,
)
from leadbot_v2.goat.preconstruction.rfi.engine import (
    PreconstructionRFIEngine,
    RFISeverity,
)


class QuantumDocumentIntelligenceTests(
    unittest.TestCase
):

    def setUp(self):
        self.engine = (
            ConstructionDocumentIntelligence()
        )

    def test_structural_sheet_identified(self):
        sheet = self.engine.analyze_page(
            RawPage(
                page_number=1,
                text=(
                    "SHEET S2.1\n"
                    "FOUNDATION PLAN\n"
                    "CONCRETE 5000 PSI"
                ),
            )
        )

        self.assertEqual(
            sheet.sheet_number,
            "S2.1",
        )

        self.assertEqual(
            sheet.discipline,
            Discipline.STRUCTURAL,
        )

    def test_architectural_scale_parsed(self):
        scales = self.engine.extract_scales(
            'SCALE: 1/8" = 1\'-0"'
        )

        declared = [
            scale
            for scale in scales
            if scale.state
            == ScaleState.DECLARED
        ]

        self.assertEqual(
            len(declared),
            1,
        )

        self.assertAlmostEqual(
            declared[0].paper_units,
            0.125,
        )

        self.assertEqual(
            declared[0].model_units,
            12.0,
        )

    def test_engineering_scale_parsed(self):
        scales = self.engine.extract_scales(
            'SCALE 1" = 20\''
        )

        declared = [
            scale
            for scale in scales
            if scale.state
            == ScaleState.DECLARED
        ]

        self.assertEqual(
            declared[0].model_units,
            20.0,
        )

        self.assertEqual(
            declared[0].model_unit_name,
            "foot",
        )

    def test_nts_detected(self):
        scales = self.engine.extract_scales(
            "DETAIL 3 - NOT TO SCALE"
        )

        self.assertTrue(
            any(
                scale.state
                == ScaleState.NTS
                for scale in scales
            )
        )

    def test_conflicting_scales_detected(self):
        scales = self.engine.extract_scales(
            'PLAN 1/8" = 1\'-0"\n'
            'DETAIL 1/4" = 1\'-0"'
        )

        self.assertTrue(
            any(
                scale.state
                == ScaleState.CONFLICT
                for scale in scales
            )
        )

    def test_dimensions_parsed(self):
        dimensions = (
            self.engine.extract_dimensions(
                "GRADE BEAM 24'-6\" LONG"
            )
        )

        self.assertEqual(
            dimensions[0].feet,
            24.0,
        )

        self.assertEqual(
            dimensions[0].inches,
            6.0,
        )

    def test_fractional_inches_parsed(self):
        dimensions = (
            self.engine.extract_dimensions(
                "DIMENSION 8'-6 1/2\""
            )
        )

        self.assertEqual(
            dimensions[0].inches,
            6.5,
        )

    def test_cross_sheet_reference_parsed(self):
        refs = (
            self.engine.extract_references(
                "SEE DETAIL 4/S5.2"
            )
        )

        self.assertEqual(
            refs[0].detail_number,
            "4",
        )

        self.assertEqual(
            refs[0].sheet_number,
            "S5.2",
        )

    def test_rebar_note_detected(self):
        notes = self.engine.extract_notes(
            "#6 @ 12\" O.C. EACH WAY T&B"
        )

        self.assertTrue(
            any(
                note.category
                == "reinforcing"
                for note in notes
            )
        )

    def test_electrical_note_detected(self):
        notes = self.engine.extract_notes(
            "600 AMP SERVICE WITH NEW SWITCHGEAR"
        )

        self.assertTrue(
            any(
                note.category
                == "electrical"
                for note in notes
            )
        )

    def test_revision_marker_detected(self):
        revisions = (
            self.engine.extract_revisions(
                "REV 3 - OWNER CHANGES"
            )
        )

        self.assertEqual(
            revisions[0].identifier,
            "3",
        )

    def test_document_is_ordered_by_page(self):
        document = (
            self.engine.analyze_document(
                source_name="plans.pdf",
                pages=(
                    RawPage(
                        page_number=2,
                        text="SHEET S2.0",
                    ),
                    RawPage(
                        page_number=1,
                        text="SHEET G0.1",
                    ),
                ),
            )
        )

        self.assertEqual(
            document.sheets[0].page_number,
            1,
        )

    def test_missing_detail_creates_rfi(self):
        document = (
            self.engine.analyze_document(
                source_name="plans.pdf",
                pages=(
                    RawPage(
                        page_number=1,
                        text=(
                            "SHEET S2.1\n"
                            "FOUNDATION PLAN\n"
                            "SEE DETAIL 4/S5.2"
                        ),
                    ),
                ),
            )
        )

        rfis = (
            PreconstructionRFIEngine()
            .analyze(document)
        )

        self.assertTrue(
            any(
                "Missing referenced detail"
                in rfi.title
                for rfi in rfis
            )
        )

    def test_nts_creates_measurement_warning(self):
        document = (
            self.engine.analyze_document(
                source_name="plans.pdf",
                pages=(
                    RawPage(
                        page_number=1,
                        text=(
                            "SHEET A5.1\n"
                            "WALL DETAIL\n"
                            "NOT TO SCALE"
                        ),
                    ),
                ),
            )
        )

        rfis = (
            PreconstructionRFIEngine()
            .analyze(document)
        )

        self.assertTrue(
            any(
                "Not-to-scale"
                in rfi.title
                for rfi in rfis
            )
        )

    def test_conflicting_scale_is_high_severity(self):
        document = (
            self.engine.analyze_document(
                source_name="plans.pdf",
                pages=(
                    RawPage(
                        page_number=1,
                        text=(
                            "SHEET A1.1\n"
                            "FLOOR PLAN\n"
                            '1/8" = 1\'-0"\n'
                            '1/4" = 1\'-0"'
                        ),
                    ),
                ),
            )
        )

        rfis = (
            PreconstructionRFIEngine()
            .analyze(document)
        )

        matches = [
            rfi
            for rfi in rfis
            if rfi.title
            == "Conflicting drawing scales"
        ]

        self.assertEqual(
            matches[0].severity,
            RFISeverity.HIGH,
        )


if __name__ == "__main__":
    unittest.main()
