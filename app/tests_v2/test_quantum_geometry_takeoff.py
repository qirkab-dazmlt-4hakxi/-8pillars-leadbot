import unittest

from leadbot_v2.goat.preconstruction.documents.models import (
    ScaleState,
    SheetScale,
)
from leadbot_v2.goat.preconstruction.geometry.measurement import (
    AmbiguousScaleError,
    GeometryMeasurementEngine,
    SheetCalibrationResolver,
    UnmeasurableGeometryError,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
    Point2D,
    VectorLine,
    VectorPolygon,
    VectorPolyline,
)
from leadbot_v2.goat.preconstruction.takeoff.concrete import (
    ConcreteAssemblyKind,
    ConcreteTakeoffEngine,
    ConcreteTakeoffPackage,
)
from leadbot_v2.goat.preconstruction.takeoff.rebar import (
    RebarIntelligence,
)


def architectural_scale() -> SheetScale:
    return SheetScale(
        raw='1/8" = 1\'-0"',
        state=ScaleState.DECLARED,
        paper_units=0.125,
        model_units=12.0,
        model_unit_name="inch",
        confidence=0.98,
    )


def engineering_scale() -> SheetScale:
    return SheetScale(
        raw='1" = 20\'',
        state=ScaleState.DECLARED,
        paper_units=1.0,
        model_units=20.0,
        model_unit_name="foot",
        confidence=0.97,
    )


def provenance(
    *geometry_ids: str,
) -> GeometryProvenance:
    return GeometryProvenance(
        document_id="doc-1",
        sheet_number="S2.1",
        page_number=3,
        source_ref="plans.pdf#page=3",
        geometry_ids=tuple(
            geometry_ids
        ),
        confidence=0.96,
    )


class QuantumGeometryTests(
    unittest.TestCase
):

    def test_architectural_scale_converts_pdf_points(self):
        calibration = (
            SheetCalibrationResolver.resolve(
                (
                    architectural_scale(),
                )
            )
        )

        # 72 points = 1 paper inch.
        # At 1/8" = 1'-0", one paper inch = 8 feet.
        self.assertAlmostEqual(
            calibration.points_to_feet(
                72.0
            ),
            8.0,
        )

    def test_engineering_scale_converts_pdf_points(self):
        calibration = (
            SheetCalibrationResolver.resolve(
                (
                    engineering_scale(),
                )
            )
        )

        self.assertAlmostEqual(
            calibration.points_to_feet(
                72.0
            ),
            20.0,
        )

    def test_conflicting_scale_refuses_measurement(self):
        with self.assertRaises(
            AmbiguousScaleError
        ):
            SheetCalibrationResolver.resolve(
                (
                    architectural_scale(),
                    SheetScale(
                        raw=(
                            "MULTIPLE DECLARED SCALES"
                        ),
                        state=(
                            ScaleState.CONFLICT
                        ),
                        confidence=0.95,
                    ),
                )
            )

    def test_nts_refuses_measurement(self):
        with self.assertRaises(
            UnmeasurableGeometryError
        ):
            SheetCalibrationResolver.resolve(
                (
                    SheetScale(
                        raw="NTS",
                        state=ScaleState.NTS,
                        confidence=1.0,
                    ),
                )
            )

    def test_missing_scale_refuses_measurement(self):
        with self.assertRaises(
            UnmeasurableGeometryError
        ):
            SheetCalibrationResolver.resolve(
                ()
            )

    def test_line_length_is_measured(self):
        calibration = (
            SheetCalibrationResolver.resolve(
                (
                    engineering_scale(),
                )
            )
        )

        line = VectorLine(
            geometry_id="line-1",
            start=Point2D(
                0.0,
                0.0,
            ),
            end=Point2D(
                72.0,
                0.0,
            ),
        )

        measurement = (
            GeometryMeasurementEngine
            .line_length(
                line,
                calibration,
            )
        )

        self.assertAlmostEqual(
            measurement.length_ft,
            20.0,
        )

    def test_polyline_length_sums_segments(self):
        calibration = (
            SheetCalibrationResolver.resolve(
                (
                    engineering_scale(),
                )
            )
        )

        polyline = VectorPolyline(
            geometry_id="poly-1",
            points=(
                Point2D(0, 0),
                Point2D(72, 0),
                Point2D(72, 72),
            ),
        )

        measurement = (
            GeometryMeasurementEngine
            .polyline_length(
                polyline,
                calibration,
            )
        )

        self.assertAlmostEqual(
            measurement.length_ft,
            40.0,
        )

    def test_polygon_area_is_real_world_square_feet(self):
        calibration = (
            SheetCalibrationResolver.resolve(
                (
                    engineering_scale(),
                )
            )
        )

        polygon = VectorPolygon(
            geometry_id="square",
            points=(
                Point2D(0, 0),
                Point2D(72, 0),
                Point2D(72, 72),
                Point2D(0, 72),
            ),
        )

        measurement = (
            GeometryMeasurementEngine
            .polygon_area(
                polygon,
                calibration,
            )
        )

        self.assertAlmostEqual(
            measurement.area_sqft,
            400.0,
        )

    def test_polygon_perimeter_is_measured(self):
        calibration = (
            SheetCalibrationResolver.resolve(
                (
                    engineering_scale(),
                )
            )
        )

        polygon = VectorPolygon(
            geometry_id="square",
            points=(
                Point2D(0, 0),
                Point2D(72, 0),
                Point2D(72, 72),
                Point2D(0, 72),
            ),
        )

        measurement = (
            GeometryMeasurementEngine
            .polygon_area(
                polygon,
                calibration,
            )
        )

        self.assertAlmostEqual(
            measurement.perimeter_ft,
            80.0,
        )

    def test_polygon_bounds_calibrate_to_dimensions(self):
        calibration = (
            SheetCalibrationResolver.resolve(
                (
                    engineering_scale(),
                )
            )
        )

        polygon = VectorPolygon(
            geometry_id="rectangle",
            points=(
                Point2D(0, 0),
                Point2D(144, 0),
                Point2D(144, 72),
                Point2D(0, 72),
            ),
        )

        dimensions = (
            GeometryMeasurementEngine
            .bounding_rectangle(
                polygon.bounds,
                calibration,
            )
        )

        self.assertAlmostEqual(
            dimensions.width_ft,
            40.0,
        )

        self.assertAlmostEqual(
            dimensions.height_ft,
            20.0,
        )


class ConcreteTakeoffTests(
    unittest.TestCase
):

    def setUp(self):
        self.calibration = (
            SheetCalibrationResolver.resolve(
                (
                    engineering_scale(),
                )
            )
        )

        self.square_20 = VectorPolygon(
            geometry_id="slab-geometry",
            points=(
                Point2D(0, 0),
                Point2D(72, 0),
                Point2D(72, 72),
                Point2D(0, 72),
            ),
        )

    def test_slab_volume_calculated(self):
        item = (
            ConcreteTakeoffEngine
            .slab_from_polygon(
                polygon=self.square_20,
                calibration=self.calibration,
                thickness_inches=6.0,
                provenance=provenance(
                    "slab-geometry"
                ),
                waste_percent=0.0,
            )
        )

        expected = (
            400.0
            * 0.5
            / 27.0
        )

        self.assertAlmostEqual(
            item.net_concrete_cy,
            expected,
            places=5,
        )

    def test_slab_waste_is_applied(self):
        item = (
            ConcreteTakeoffEngine
            .slab_from_polygon(
                polygon=self.square_20,
                calibration=self.calibration,
                thickness_inches=6.0,
                provenance=provenance(
                    "slab-geometry"
                ),
                waste_percent=5.0,
            )
        )

        self.assertAlmostEqual(
            item.bid_concrete_cy,
            item.net_concrete_cy
            * 1.05,
        )

    def test_slab_preserves_clickable_provenance(self):
        item = (
            ConcreteTakeoffEngine
            .slab_from_polygon(
                polygon=self.square_20,
                calibration=self.calibration,
                thickness_inches=6.0,
                provenance=provenance(
                    "slab-geometry"
                ),
            )
        )

        self.assertEqual(
            item.provenance.sheet_number,
            "S2.1",
        )

        self.assertIn(
            "slab-geometry",
            item.provenance.geometry_ids,
        )

    def test_footing_volume_calculated(self):
        item = (
            ConcreteTakeoffEngine
            .footing_from_polygon(
                polygon=self.square_20,
                calibration=self.calibration,
                depth_inches=24.0,
                provenance=provenance(
                    "slab-geometry"
                ),
                waste_percent=0.0,
            )
        )

        expected = (
            400.0
            * 2.0
            / 27.0
        )

        self.assertAlmostEqual(
            item.net_concrete_cy,
            expected,
        )

    def test_grade_beam_volume_calculated(self):
        beam = VectorPolyline(
            geometry_id="beam-1",
            points=(
                Point2D(0, 0),
                Point2D(360, 0),
            ),
        )

        # 360 points at 1" = 20'
        # = 100 LF
        item = (
            ConcreteTakeoffEngine
            .grade_beam_from_polyline(
                polyline=beam,
                calibration=self.calibration,
                width_inches=24.0,
                depth_inches=24.0,
                provenance=provenance(
                    "beam-1"
                ),
                waste_percent=0.0,
            )
        )

        expected = (
            100.0
            * 2.0
            * 2.0
            / 27.0
        )

        self.assertAlmostEqual(
            item.net_concrete_cy,
            expected,
        )

    def test_grade_beam_formwork_is_optional(self):
        beam = VectorPolyline(
            geometry_id="beam-1",
            points=(
                Point2D(0, 0),
                Point2D(360, 0),
            ),
        )

        item = (
            ConcreteTakeoffEngine
            .grade_beam_from_polyline(
                polyline=beam,
                calibration=self.calibration,
                width_inches=24.0,
                depth_inches=24.0,
                formed_sides=2,
                provenance=provenance(
                    "beam-1"
                ),
                waste_percent=0.0,
            )
        )

        self.assertAlmostEqual(
            item.formwork_sf,
            400.0,
        )

    def test_wall_volume_and_formwork(self):
        wall = VectorPolyline(
            geometry_id="wall-1",
            points=(
                Point2D(0, 0),
                Point2D(360, 0),
            ),
        )

        item = (
            ConcreteTakeoffEngine
            .wall_from_polyline(
                polyline=wall,
                calibration=self.calibration,
                height_ft=10.0,
                thickness_inches=8.0,
                provenance=provenance(
                    "wall-1"
                ),
                waste_percent=0.0,
            )
        )

        expected_cy = (
            100.0
            * 10.0
            * (8.0 / 12.0)
            / 27.0
        )

        self.assertAlmostEqual(
            item.net_concrete_cy,
            expected_cy,
        )

        self.assertAlmostEqual(
            item.formwork_sf,
            2000.0,
        )

    def test_package_totals_multiple_items(self):
        slab = (
            ConcreteTakeoffEngine
            .slab_from_polygon(
                polygon=self.square_20,
                calibration=self.calibration,
                thickness_inches=6.0,
                provenance=provenance(
                    "slab-geometry"
                ),
                waste_percent=0.0,
            )
        )

        footing = (
            ConcreteTakeoffEngine
            .footing_from_polygon(
                polygon=self.square_20,
                calibration=self.calibration,
                depth_inches=12.0,
                provenance=provenance(
                    "slab-geometry"
                ),
                waste_percent=0.0,
            )
        )

        package = (
            ConcreteTakeoffPackage()
        )

        package.add(slab)
        package.add(footing)

        self.assertAlmostEqual(
            package.total_bid_concrete_cy,
            slab.bid_concrete_cy
            + footing.bid_concrete_cy,
        )

        self.assertEqual(
            len(
                package.by_kind(
                    ConcreteAssemblyKind.SLAB
                )
            ),
            1,
        )


class RebarIntelligenceTests(
    unittest.TestCase
):

    def test_rebar_spec_parses_size_and_spacing(self):
        spec = (
            RebarIntelligence.parse(
                '#6 @ 12" O.C.'
            )
        )

        self.assertIsNotNone(spec)
        self.assertEqual(
            spec.bar_size,
            6,
        )
        self.assertEqual(
            spec.spacing_inches,
            12.0,
        )

    def test_each_way_creates_two_directions(self):
        spec = (
            RebarIntelligence.parse(
                '#6 @ 12" O.C. EACH WAY'
            )
        )

        self.assertEqual(
            spec.directions,
            2,
        )

    def test_ew_abbreviation_creates_two_directions(self):
        spec = (
            RebarIntelligence.parse(
                '#5 @ 10" OC EW'
            )
        )

        self.assertEqual(
            spec.directions,
            2,
        )

    def test_top_and_bottom_creates_two_layers(self):
        spec = (
            RebarIntelligence.parse(
                '#8 @ 8" OC EW T&B'
            )
        )

        self.assertEqual(
            spec.layers,
            2,
        )

    def test_two_mats_creates_two_layers(self):
        spec = (
            RebarIntelligence.parse(
                '2 MATS #8 @ 8" OC EW'
            )
        )

        self.assertEqual(
            spec.layers,
            2,
        )

    def test_non_rebar_note_returns_none(self):
        spec = (
            RebarIntelligence.parse(
                "CONCRETE SHALL BE 5000 PSI"
            )
        )

        self.assertIsNone(spec)

    def test_slab_rebar_linear_feet_calculated(self):
        spec = (
            RebarIntelligence.parse(
                '#6 @ 12" OC EW T&B'
            )
        )

        result = (
            RebarIntelligence
            .slab_grid_takeoff(
                spec=spec,
                area_sqft=400.0,
                provenance=provenance(
                    "slab-geometry"
                ),
                lap_waste_percent=0.0,
            )
        )

        # 400 SF / 1 FT spacing
        # × 2 directions × 2 layers
        self.assertAlmostEqual(
            result.total_linear_feet,
            1600.0,
        )

    def test_slab_rebar_weight_calculated(self):
        spec = (
            RebarIntelligence.parse(
                '#6 @ 12" OC EW T&B'
            )
        )

        result = (
            RebarIntelligence
            .slab_grid_takeoff(
                spec=spec,
                area_sqft=400.0,
                provenance=provenance(
                    "slab-geometry"
                ),
                lap_waste_percent=0.0,
            )
        )

        self.assertAlmostEqual(
            result.total_weight_lb,
            1600.0 * 1.502,
        )

    def test_rebar_takeoff_preserves_source_provenance(self):
        spec = (
            RebarIntelligence.parse(
                '#6 @ 12" OC EW'
            )
        )

        result = (
            RebarIntelligence
            .slab_grid_takeoff(
                spec=spec,
                area_sqft=100.0,
                provenance=provenance(
                    "reinforcing-zone-1"
                ),
            )
        )

        self.assertIn(
            "reinforcing-zone-1",
            result.provenance.geometry_ids,
        )


if __name__ == "__main__":
    unittest.main()
