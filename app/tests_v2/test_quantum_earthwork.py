import unittest

from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)
from leadbot_v2.goat.preconstruction.earthwork.engine import (
    EarthworkActivity,
    EarthworkEstimateBridge,
    EarthworkPricingEngine,
    EarthworkSeverity,
    EarthworkTakeoffEngine,
    EarthworkValidationError,
    GradeCell,
    HaulPlanningEngine,
    ProductionPlanningEngine,
    SoilFactors,
)
from leadbot_v2.goat.preconstruction.estimating.workflow import (
    EstimateWorkflowService,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)
from leadbot_v2.goat.preconstruction.pricing.engine import (
    CostClass,
    MarkupPolicy,
    MissingRateError,
    PriceBook,
    PricingUnit,
    UnitRate,
)


TENANT = "twins-development"
BU = "twins-development"


def provenance(
    confidence=0.98,
):
    return GeometryProvenance(
        document_id="civil-doc",
        sheet_number="C3.1",
        page_number=8,
        source_ref="civil.pdf#page=8",
        geometry_ids=(
            "grading-region-1",
        ),
        text_refs=(
            "grading-note-1",
        ),
        confidence=confidence,
    )


def price_book():
    book = PriceBook()

    rates = (
        (
            "MASS_EXCAVATION",
            "Mass Excavation",
            PricingUnit.CY,
            CostClass.EQUIPMENT,
            550,
        ),
        (
            "IMPORT_FILL",
            "Imported Fill",
            PricingUnit.CY,
            CostClass.MATERIAL,
            1800,
        ),
        (
            "EXPORT_HAUL",
            "Export Haul",
            PricingUnit.CY,
            CostClass.EQUIPMENT,
            900,
        ),
        (
            "DISPOSAL",
            "Disposal",
            PricingUnit.CY,
            CostClass.OTHER,
            700,
        ),
        (
            "COMPACTION",
            "Compaction",
            PricingUnit.CY,
            CostClass.EQUIPMENT,
            450,
        ),
        (
            "FINE_GRADING",
            "Fine Grading",
            PricingUnit.SF,
            CostClass.LABOR,
            18,
        ),
        (
            "TRENCH_EXCAVATION",
            "Trench Excavation",
            PricingUnit.CY,
            CostClass.EQUIPMENT,
            1400,
        ),
        (
            "BEDDING",
            "Trench Bedding",
            PricingUnit.CY,
            CostClass.MATERIAL,
            3200,
        ),
        (
            "TRENCH_BACKFILL",
            "Trench Backfill",
            PricingUnit.CY,
            CostClass.LABOR,
            1200,
        ),
        (
            "TRENCH_SPOIL_HAUL",
            "Trench Spoil Haul",
            PricingUnit.CY,
            CostClass.EQUIPMENT,
            900,
        ),
    )

    for (
        code,
        description,
        unit,
        cost_class,
        cents,
    ) in rates:
        book.register(
            UnitRate(
                code=code,
                description=description,
                unit=unit,
                cost_class=(
                    cost_class
                ),
                cents_per_unit=(
                    cents
                ),
                source=(
                    "TEST APPROVED RATE"
                ),
            )
        )

    return book


class SoilFactorTests(
    unittest.TestCase
):

    def test_swell_conversion(self):
        factors = SoilFactors(
            swell_percent=20,
        )

        self.assertAlmostEqual(
            factors.bank_to_loose(
                100
            ),
            120,
        )

    def test_shrink_conversion(self):
        factors = SoilFactors(
            shrink_percent=10,
        )

        self.assertAlmostEqual(
            factors.bank_to_compacted(
                100
            ),
            90,
        )

    def test_compacted_to_bank(self):
        factors = SoilFactors(
            shrink_percent=10,
        )

        self.assertAlmostEqual(
            factors.compacted_to_bank(
                90
            ),
            100,
        )

    def test_invalid_shrink_rejected(self):
        with self.assertRaises(
            EarthworkValidationError
        ):
            SoilFactors(
                shrink_percent=100
            )

    def test_negative_swell_rejected(self):
        with self.assertRaises(
            EarthworkValidationError
        ):
            SoilFactors(
                swell_percent=-1
            )


class CutFillTests(
    unittest.TestCase
):

    def test_cut_cell_calculates_bank_volume(self):
        result = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="1",
                        area_sqft=2700,
                        existing_elevation_ft=100,
                        proposed_elevation_ft=99,
                    ),
                ),
                soil_factors=(
                    SoilFactors()
                ),
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.gross_cut_bcy,
            100,
        )

        self.assertEqual(
            result.gross_fill_ccy,
            0,
        )

    def test_fill_cell_calculates_compacted_volume(self):
        result = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="1",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors()
                ),
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.gross_fill_ccy,
            100,
        )

    def test_fill_shrink_increases_bank_requirement(self):
        result = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="1",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors(
                        shrink_percent=10
                    )
                ),
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.fill_bank_required_bcy,
            111.11111111111111,
        )

    def test_balanced_cut_fill(self):
        result = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="cut",
                        area_sqft=2700,
                        existing_elevation_ft=100,
                        proposed_elevation_ft=99,
                    ),
                    GradeCell(
                        cell_id="fill",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors()
                ),
                provenance=provenance(),
            )
        )

        self.assertTrue(
            result.balanced
        )

    def test_surplus_cut_generates_export(self):
        result = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="cut",
                        area_sqft=5400,
                        existing_elevation_ft=100,
                        proposed_elevation_ft=99,
                    ),
                    GradeCell(
                        cell_id="fill",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors(
                        swell_percent=20
                    )
                ),
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.surplus_bank_bcy,
            100,
        )

        self.assertAlmostEqual(
            result.export_loose_cy,
            120,
        )

    def test_fill_deficit_generates_import(self):
        result = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="fill",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors()
                ),
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.import_bank_cy,
            100,
        )

    def test_undercut_adds_cut_and_replacement_fill(self):
        result = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="1",
                        area_sqft=2700,
                        existing_elevation_ft=100,
                        proposed_elevation_ft=100,
                        undercut_ft=1,
                    ),
                ),
                soil_factors=(
                    SoilFactors()
                ),
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.gross_cut_bcy,
            100,
        )

        self.assertAlmostEqual(
            result.gross_fill_ccy,
            100,
        )

    def test_empty_grid_rejected(self):
        with self.assertRaises(
            EarthworkValidationError
        ):
            (
                EarthworkTakeoffEngine
                .cut_fill_from_cells(
                    cells=(),
                    soil_factors=(
                        SoilFactors()
                    ),
                    provenance=provenance(),
                )
            )


class TrenchTests(
    unittest.TestCase
):

    def test_trench_volume(self):
        result = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=100,
                excavation_width_ft=3,
                excavation_depth_ft=6,
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.excavation_bcy,
            1800 / 27,
        )

    def test_bedding_volume(self):
        result = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=100,
                excavation_width_ft=3,
                excavation_depth_ft=6,
                bedding_depth_ft=1,
                provenance=provenance(),
            )
        )

        self.assertAlmostEqual(
            result.bedding_cy,
            300 / 27,
        )

    def test_pipe_displacement_reduces_backfill(self):
        no_pipe = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=100,
                excavation_width_ft=3,
                excavation_depth_ft=6,
                bedding_depth_ft=1,
                provenance=provenance(),
            )
        )

        with_pipe = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=100,
                excavation_width_ft=3,
                excavation_depth_ft=6,
                bedding_depth_ft=1,
                pipe_outer_diameter_inches=24,
                provenance=provenance(),
            )
        )

        self.assertLess(
            with_pipe.backfill_cy,
            no_pipe.backfill_cy,
        )

    def test_deep_trench_creates_high_risk_finding(self):
        result = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=100,
                excavation_width_ft=4,
                excavation_depth_ft=8,
                provenance=provenance(),
            )
        )

        self.assertTrue(
            any(
                item.code
                == "deep_trench_review"
                and item.severity
                == EarthworkSeverity.HIGH
                for item
                in result.findings
            )
        )

    def test_twenty_foot_trench_creates_critical_review(self):
        result = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=50,
                excavation_width_ft=6,
                excavation_depth_ft=20,
                provenance=provenance(),
            )
        )

        self.assertTrue(
            any(
                item.severity
                == EarthworkSeverity.CRITICAL
                for item
                in result.findings
            )
        )

    def test_invalid_trench_rejected(self):
        with self.assertRaises(
            EarthworkValidationError
        ):
            (
                EarthworkTakeoffEngine
                .trench(
                    length_ft=0,
                    excavation_width_ft=3,
                    excavation_depth_ft=5,
                    provenance=provenance(),
                )
            )


class HaulProductionTests(
    unittest.TestCase
):

    def test_haul_load_count(self):
        result = (
            HaulPlanningEngine.plan(
                loose_volume_cy=180,
                truck_capacity_cy=20,
                cycle_minutes=60,
                truck_count=3,
                load_factor=0.90,
            )
        )

        self.assertEqual(
            result.required_loads,
            10,
        )

    def test_haul_elapsed_time_uses_truck_count(self):
        result = (
            HaulPlanningEngine.plan(
                loose_volume_cy=180,
                truck_capacity_cy=20,
                cycle_minutes=60,
                truck_count=5,
                load_factor=0.90,
            )
        )

        self.assertAlmostEqual(
            result.elapsed_hours,
            2,
        )

    def test_production_plan_calculates_hours(self):
        result = (
            ProductionPlanningEngine
            .estimate(
                activity=(
                    EarthworkActivity
                    .MASS_EXCAVATION
                ),
                quantity=1000,
                unit="CY",
                production_per_hour=100,
                labor_cost_per_hour_cents=15000,
                equipment_cost_per_hour_cents=25000,
            )
        )

        self.assertEqual(
            result.crew_hours,
            10,
        )

        self.assertEqual(
            result.total_production_cost_cents,
            400_000,
        )


class EarthworkPricingTests(
    unittest.TestCase
):

    def mass_balance(self):
        return (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="cut",
                        area_sqft=5400,
                        existing_elevation_ft=100,
                        proposed_elevation_ft=99,
                    ),
                    GradeCell(
                        cell_id="fill",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors(
                        swell_percent=20
                    )
                ),
                provenance=provenance(),
            )
        )

    def test_mass_earthwork_prices_excavation(self):
        priced = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=(
                    self.mass_balance()
                ),
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            any(
                item.rate_code
                == "MASS_EXCAVATION"
                for item
                in priced.components
            )
        )

    def test_mass_earthwork_prices_export_and_disposal(self):
        priced = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=(
                    self.mass_balance()
                ),
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        codes = {
            item.rate_code
            for item
            in priced.components
        }

        self.assertIn(
            "EXPORT_HAUL",
            codes,
        )

        self.assertIn(
            "DISPOSAL",
            codes,
        )

    def test_fill_job_prices_import_and_compaction(self):
        takeoff = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="fill",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors()
                ),
                provenance=provenance(),
            )
        )

        priced = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=takeoff,
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        codes = {
            item.rate_code
            for item
            in priced.components
        }

        self.assertIn(
            "IMPORT_FILL",
            codes,
        )

        self.assertIn(
            "COMPACTION",
            codes,
        )

    def test_mass_earthwork_prices_fine_grading(self):
        priced = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=(
                    self.mass_balance()
                ),
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            any(
                item.rate_code
                == "FINE_GRADING"
                for item
                in priced.components
            )
        )

    def test_markup_increases_bid_price(self):
        base = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=(
                    self.mass_balance()
                ),
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        marked = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=(
                    self.mass_balance()
                ),
                price_book=price_book(),
                markup=MarkupPolicy(
                    overhead_bps=1000,
                    contingency_bps=500,
                    profit_bps=1500,
                ),
            )
        )

        self.assertGreater(
            marked.bid_price_cents,
            base.bid_price_cents,
        )

    def test_missing_approved_rate_fails_closed(self):
        with self.assertRaises(
            MissingRateError
        ):
            (
                EarthworkPricingEngine
                .price_mass_balance(
                    takeoff=(
                        self.mass_balance()
                    ),
                    price_book=PriceBook(),
                    markup=MarkupPolicy(),
                )
            )

    def test_provenance_survives_pricing(self):
        priced = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=(
                    self.mass_balance()
                ),
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        self.assertEqual(
            priced.provenance
            .sheet_number,
            "C3.1",
        )

        self.assertIn(
            "grading-region-1",
            priced.provenance
            .geometry_ids,
        )

    def test_low_confidence_requires_review(self):
        takeoff = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="cut",
                        area_sqft=2700,
                        existing_elevation_ft=100,
                        proposed_elevation_ft=99,
                    ),
                ),
                soil_factors=(
                    SoilFactors(
                        swell_percent=20
                    )
                ),
                provenance=provenance(
                    confidence=0.60
                ),
            )
        )

        priced = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=takeoff,
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            priced.requires_review
        )

    def test_deep_trench_pricing_requires_review(self):
        trench = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=100,
                excavation_width_ft=4,
                excavation_depth_ft=8,
                bedding_depth_ft=1,
                pipe_outer_diameter_inches=18,
                provenance=provenance(),
            )
        )

        priced = (
            EarthworkPricingEngine
            .price_trench(
                takeoff=trench,
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            priced.requires_review
        )

    def test_trench_pricing_contains_core_components(self):
        trench = (
            EarthworkTakeoffEngine
            .trench(
                length_ft=100,
                excavation_width_ft=4,
                excavation_depth_ft=4,
                bedding_depth_ft=1,
                pipe_outer_diameter_inches=18,
                provenance=provenance(),
            )
        )

        priced = (
            EarthworkPricingEngine
            .price_trench(
                takeoff=trench,
                price_book=price_book(),
                markup=MarkupPolicy(),
            )
        )

        codes = {
            item.rate_code
            for item
            in priced.components
        }

        self.assertIn(
            "TRENCH_EXCAVATION",
            codes,
        )

        self.assertIn(
            "BEDDING",
            codes,
        )

        self.assertIn(
            "TRENCH_BACKFILL",
            codes,
        )


class EarthworkEstimateBridgeTests(
    unittest.TestCase
):

    def test_priced_earthwork_enters_goat_estimate(self):
        spine = InMemoryDataSpine()

        workflow = (
            EstimateWorkflowService(
                spine=spine
            )
        )

        estimate = (
            workflow.create_estimate(
                tenant_id=TENANT,
                business_unit_id=BU,
                project_name=(
                    "Civil Project"
                ),
                actor_id="estimator",
            )
        )

        takeoff = (
            EarthworkTakeoffEngine
            .cut_fill_from_cells(
                cells=(
                    GradeCell(
                        cell_id="cut",
                        area_sqft=5400,
                        existing_elevation_ft=100,
                        proposed_elevation_ft=99,
                    ),
                    GradeCell(
                        cell_id="fill",
                        area_sqft=2700,
                        existing_elevation_ft=99,
                        proposed_elevation_ft=100,
                    ),
                ),
                soil_factors=(
                    SoilFactors(
                        swell_percent=20
                    )
                ),
                provenance=provenance(),
            )
        )

        priced = (
            EarthworkPricingEngine
            .price_mass_balance(
                takeoff=takeoff,
                price_book=price_book(),
                markup=MarkupPolicy(
                    overhead_bps=1000,
                    profit_bps=1500,
                ),
            )
        )

        line = (
            EarthworkEstimateBridge
            .add_to_estimate(
                workflow=workflow,
                estimate_id=(
                    estimate.estimate_id
                ),
                actor_id="estimator",
                priced_scope=priced,
                cost_code="31-2000",
            )
        )

        current = (
            workflow.current_version(
                estimate.estimate_id
            )
        )

        self.assertEqual(
            line.cost_code,
            "31-2000",
        )

        self.assertEqual(
            current.base_bid_price_cents,
            priced.bid_price_cents,
        )

        self.assertIn(
            "civil.pdf#page=8",
            line.source_refs,
        )


if __name__ == "__main__":
    unittest.main()
