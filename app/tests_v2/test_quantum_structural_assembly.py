import unittest

from leadbot_v2.goat.preconstruction.assemblies.structural import (
    AssemblyInferenceError,
    AssemblyKind,
    AutomaticStructuralTakeoffEngine,
    StructuralAssemblyInferenceEngine,
    StructuralCalloutParser,
)
from leadbot_v2.goat.preconstruction.documents.models import (
    ScaleState,
    SheetScale,
)
from leadbot_v2.goat.preconstruction.geometry.measurement import (
    SheetCalibrationResolver,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    BoundingBox,
    Point2D,
    TextSpan,
    VectorPolygon,
    VectorPolyline,
)


def calibration():
    return SheetCalibrationResolver.resolve(
        (
            SheetScale(
                raw='1" = 20\'',
                state=ScaleState.DECLARED,
                paper_units=1.0,
                model_units=20.0,
                model_unit_name="foot",
                confidence=0.98,
            ),
        )
    )


def slab_polygon():
    return VectorPolygon(
        geometry_id="slab-1",
        points=(
            Point2D(0, 0),
            Point2D(72, 0),
            Point2D(72, 72),
            Point2D(0, 72),
        ),
    )


def beam_polyline():
    return VectorPolyline(
        geometry_id="beam-1",
        points=(
            Point2D(0, 0),
            Point2D(360, 0),
        ),
    )


def nearby_span(
    text: str,
    text_id: str = "text-1",
):
    return TextSpan(
        text_id=text_id,
        text=text,
        bounds=BoundingBox(
            20,
            20,
            40,
            35,
        ),
    )


class StructuralCalloutTests(
    unittest.TestCase
):

    def test_slab_callout_parses(self):
        result = (
            StructuralCalloutParser.parse(
                '6" SOG'
            )
        )

        self.assertEqual(
            result.kind,
            AssemblyKind.SLAB,
        )

        self.assertEqual(
            result.thickness_inches,
            6.0,
        )

    def test_slab_with_rebar_parses(self):
        result = (
            StructuralCalloutParser.parse(
                '6" SOG #5 @ 12" OC EW'
            )
        )

        self.assertEqual(
            result.kind,
            AssemblyKind.SLAB,
        )

        self.assertIsNotNone(
            result.rebar
        )

        self.assertEqual(
            result.rebar.bar_size,
            5,
        )

        self.assertEqual(
            result.rebar.directions,
            2,
        )

    def test_grade_beam_callout_parses(self):
        result = (
            StructuralCalloutParser.parse(
                'GB-3 24"x36"'
            )
        )

        self.assertEqual(
            result.kind,
            AssemblyKind.GRADE_BEAM,
        )

        self.assertEqual(
            result.label,
            "GB-3",
        )

        self.assertEqual(
            result.width_inches,
            24.0,
        )

        self.assertEqual(
            result.depth_inches,
            36.0,
        )

    def test_generic_grade_beam_parses(self):
        result = (
            StructuralCalloutParser.parse(
                'GRADE BEAM 18"x24"'
            )
        )

        self.assertEqual(
            result.kind,
            AssemblyKind.GRADE_BEAM,
        )

    def test_footing_callout_parses(self):
        result = (
            StructuralCalloutParser.parse(
                'F-2 48"x18"'
            )
        )

        self.assertEqual(
            result.kind,
            AssemblyKind.FOOTING,
        )

        self.assertEqual(
            result.depth_inches,
            18.0,
        )

    def test_wall_callout_parses(self):
        result = (
            StructuralCalloutParser.parse(
                '12" CONCRETE WALL H=10\''
            )
        )

        self.assertEqual(
            result.kind,
            AssemblyKind.WALL,
        )

        self.assertEqual(
            result.thickness_inches,
            12.0,
        )

        self.assertEqual(
            result.height_ft,
            10.0,
        )

    def test_irrelevant_text_returns_none(self):
        result = (
            StructuralCalloutParser.parse(
                "GENERAL STRUCTURAL NOTES"
            )
        )

        self.assertIsNone(
            result
        )


class StructuralAssociationTests(
    unittest.TestCase
):

    def setUp(self):
        self.inference = (
            StructuralAssemblyInferenceEngine()
        )

    def test_slab_callout_associates_polygon(self):
        candidates = (
            self.inference.infer(
                document_id="doc-1",
                sheet_number="S2.1",
                page_number=3,
                source_ref="plans.pdf#page=3",
                text_spans=(
                    nearby_span(
                        '6" SOG'
                    ),
                ),
                polygons=(
                    slab_polygon(),
                ),
                polylines=(),
            )
        )

        self.assertEqual(
            len(candidates),
            1,
        )

        self.assertEqual(
            candidates[0].geometry_id,
            "slab-1",
        )

    def test_grade_beam_associates_polyline(self):
        candidates = (
            self.inference.infer(
                document_id="doc-1",
                sheet_number="S2.1",
                page_number=3,
                source_ref="plans.pdf#page=3",
                text_spans=(
                    nearby_span(
                        'GB-3 24"x36"'
                    ),
                ),
                polygons=(),
                polylines=(
                    beam_polyline(),
                ),
            )
        )

        self.assertEqual(
            candidates[0].geometry_id,
            "beam-1",
        )

    def test_provenance_contains_geometry_and_text(self):
        candidates = (
            self.inference.infer(
                document_id="doc-1",
                sheet_number="S2.1",
                page_number=3,
                source_ref="plans.pdf#page=3",
                text_spans=(
                    nearby_span(
                        '6" SOG',
                        "callout-17",
                    ),
                ),
                polygons=(
                    slab_polygon(),
                ),
                polylines=(),
            )
        )

        source = (
            candidates[0].provenance
        )

        self.assertIn(
            "slab-1",
            source.geometry_ids,
        )

        self.assertIn(
            "callout-17",
            source.text_refs,
        )

    def test_distant_callout_is_not_forced(self):
        span = TextSpan(
            text_id="far",
            text='6" SOG',
            bounds=BoundingBox(
                1000,
                1000,
                1020,
                1020,
            ),
        )

        candidates = (
            self.inference.infer(
                document_id="doc",
                sheet_number="S2.1",
                page_number=1,
                source_ref="plans.pdf#page=1",
                text_spans=(span,),
                polygons=(
                    slab_polygon(),
                ),
                polylines=(),
            )
        )

        self.assertEqual(
            candidates,
            (),
        )


class AutomaticTakeoffTests(
    unittest.TestCase
):

    def setUp(self):
        self.inference = (
            StructuralAssemblyInferenceEngine()
        )

        self.takeoff = (
            AutomaticStructuralTakeoffEngine()
        )

    def slab_candidate(
        self,
        text='6" SOG',
    ):
        return (
            self.inference.infer(
                document_id="doc",
                sheet_number="S2.1",
                page_number=1,
                source_ref="plans.pdf#page=1",
                text_spans=(
                    nearby_span(text),
                ),
                polygons=(
                    slab_polygon(),
                ),
                polylines=(),
            )[0]
        )

    def test_auto_slab_generates_concrete(self):
        candidate = (
            self.slab_candidate()
        )

        result = self.takeoff.build(
            candidate=candidate,
            calibration=calibration(),
            polygon=slab_polygon(),
            waste_percent=0.0,
        )

        expected = (
            400.0
            * 0.5
            / 27.0
        )

        self.assertAlmostEqual(
            result.concrete.net_concrete_cy,
            expected,
        )

    def test_auto_slab_generates_rebar(self):
        candidate = (
            self.slab_candidate(
                '6" SOG #5 @ 12" OC EW'
            )
        )

        result = self.takeoff.build(
            candidate=candidate,
            calibration=calibration(),
            polygon=slab_polygon(),
            waste_percent=0.0,
            rebar_waste_percent=0.0,
        )

        self.assertIsNotNone(
            result.rebar
        )

        self.assertAlmostEqual(
            result.rebar
            .total_linear_feet,
            800.0,
        )

    def test_auto_grade_beam_generates_concrete(self):
        candidate = (
            self.inference.infer(
                document_id="doc",
                sheet_number="S2.1",
                page_number=1,
                source_ref="plans.pdf#page=1",
                text_spans=(
                    nearby_span(
                        'GB-3 24"x36"'
                    ),
                ),
                polygons=(),
                polylines=(
                    beam_polyline(),
                ),
            )[0]
        )

        result = self.takeoff.build(
            candidate=candidate,
            calibration=calibration(),
            polyline=beam_polyline(),
            waste_percent=0.0,
        )

        # 100 LF x 2 FT x 3 FT / 27
        self.assertAlmostEqual(
            result.concrete.net_concrete_cy,
            600.0 / 27.0,
        )

    def test_auto_wall_requires_height(self):
        candidate = (
            self.inference.infer(
                document_id="doc",
                sheet_number="S2.1",
                page_number=1,
                source_ref="plans.pdf#page=1",
                text_spans=(
                    nearby_span(
                        '12" CONCRETE WALL'
                    ),
                ),
                polygons=(),
                polylines=(
                    beam_polyline(),
                ),
            )[0]
        )

        with self.assertRaises(
            AssemblyInferenceError
        ):
            self.takeoff.build(
                candidate=candidate,
                calibration=calibration(),
                polyline=beam_polyline(),
            )

    def test_wall_with_height_can_takeoff(self):
        candidate = (
            self.inference.infer(
                document_id="doc",
                sheet_number="S2.1",
                page_number=1,
                source_ref="plans.pdf#page=1",
                text_spans=(
                    nearby_span(
                        '12" CONCRETE WALL H=10\''
                    ),
                ),
                polygons=(),
                polylines=(
                    beam_polyline(),
                ),
            )[0]
        )

        result = self.takeoff.build(
            candidate=candidate,
            calibration=calibration(),
            polyline=beam_polyline(),
            waste_percent=0.0,
        )

        # 100 LF x 10 FT x 1 FT / 27
        self.assertAlmostEqual(
            result.concrete.net_concrete_cy,
            1000.0 / 27.0,
        )

    def test_low_confidence_association_requires_review(self):
        span = TextSpan(
            text_id="medium-distance",
            text='6" SOG',
            bounds=BoundingBox(
                170,
                170,
                190,
                190,
            ),
        )

        candidate = (
            self.inference.infer(
                document_id="doc",
                sheet_number="S2.1",
                page_number=1,
                source_ref="plans.pdf#page=1",
                text_spans=(span,),
                polygons=(
                    slab_polygon(),
                ),
                polylines=(),
            )[0]
        )

        result = self.takeoff.build(
            candidate=candidate,
            calibration=calibration(),
            polygon=slab_polygon(),
        )

        self.assertTrue(
            result.requires_review
        )


if __name__ == "__main__":
    unittest.main()
