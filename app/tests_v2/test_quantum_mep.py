import unittest

from leadbot_v2.goat.data_spine.store import InMemoryDataSpine
from leadbot_v2.goat.preconstruction.estimating.workflow import (
    EstimateWorkflowService,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)
from leadbot_v2.goat.preconstruction.mep.bridge import (
    MEPEstimateBridge,
)
from leadbot_v2.goat.preconstruction.mep.electrical import (
    ElectricalCalloutParser,
    ElectricalPricingEngine,
    ElectricalPricingRecipe,
    ElectricalTakeoffEngine,
)
from leadbot_v2.goat.preconstruction.mep.plumbing import (
    PlumbingCalloutParser,
    PlumbingPricingEngine,
    PlumbingPricingRecipe,
    PlumbingSystem,
    PlumbingTakeoffEngine,
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


def electrical_source():
    return GeometryProvenance(
        document_id="electrical-doc",
        sheet_number="E3.1",
        page_number=14,
        source_ref="electrical.pdf#page=14",
        geometry_ids=("feeder-run-1",),
        text_refs=("feeder-note-1",),
        confidence=0.98,
    )


def plumbing_source():
    return GeometryProvenance(
        document_id="plumbing-doc",
        sheet_number="P2.1",
        page_number=20,
        source_ref="plumbing.pdf#page=20",
        geometry_ids=("pipe-run-1",),
        text_refs=("pipe-note-1",),
        confidence=0.98,
    )


def price_book():
    book = PriceBook()

    rates = (
        ("EMT_MAT", "EMT Material", PricingUnit.LF, CostClass.MATERIAL, 300),
        ("EMT_LAB", "EMT Labor", PricingUnit.LF, CostClass.LABOR, 450),
        ("WIRE_MAT", "Copper Wire", PricingUnit.LF, CostClass.MATERIAL, 650),
        ("WIRE_LAB", "Wire Labor", PricingUnit.LF, CostClass.LABOR, 180),
        ("TERM", "Termination", PricingUnit.EA, CostClass.LABOR, 2500),

        ("LIGHT_MAT", "Fixture", PricingUnit.EA, CostClass.MATERIAL, 15000),
        ("LIGHT_LAB", "Fixture Labor", PricingUnit.EA, CostClass.LABOR, 7500),

        ("PVC_PIPE", "PVC Pipe", PricingUnit.LF, CostClass.MATERIAL, 900),
        ("PVC_LAB", "PVC Labor", PricingUnit.LF, CostClass.LABOR, 1200),

        ("PVC_FITTING", "PVC Fitting", PricingUnit.EA, CostClass.MATERIAL, 2500),
        ("PVC_FITTING_LAB", "Fitting Labor", PricingUnit.EA, CostClass.LABOR, 1800),

        ("HANGER_MAT", "Pipe Hanger", PricingUnit.EA, CostClass.MATERIAL, 800),
        ("HANGER_LAB", "Hanger Labor", PricingUnit.EA, CostClass.LABOR, 1500),

        ("WC_MAT", "Water Closet", PricingUnit.EA, CostClass.MATERIAL, 45000),
        ("WC_LAB", "Water Closet Labor", PricingUnit.EA, CostClass.LABOR, 30000),
    )

    for code, description, unit, cost_class, cents in rates:
        book.register(
            UnitRate(
                code=code,
                description=description,
                unit=unit,
                cost_class=cost_class,
                cents_per_unit=cents,
                source="TEST APPROVED RATE",
            )
        )

    return book


class ElectricalMEPTests(unittest.TestCase):

    def test_service_callout(self):
        result = ElectricalCalloutParser.service(
            "400A 480Y/277V 3PH SERVICE"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.amperage, 400)
        self.assertEqual(result.phase, 3)

    def test_conduit_callout(self):
        result = ElectricalCalloutParser.conduit(
            '2" EMT'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.size_inches, "2")
        self.assertEqual(result.conduit_type, "EMT")

    def test_conductor_callout(self):
        result = ElectricalCalloutParser.conductors(
            "4 #3/0 CU"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.count, 4)
        self.assertEqual(result.size, "3/0")
        self.assertEqual(result.material, "CU")

    def test_conductor_takeoff_includes_waste(self):
        result = ElectricalTakeoffEngine.run(
            description="Main Feeder",
            length_ft=100,
            provenance=electrical_source(),
            conduit=ElectricalCalloutParser.conduit(
                '2" EMT'
            ),
            conductors=ElectricalCalloutParser.conductors(
                "4 #3/0 CU"
            ),
            conductor_waste_percent=10,
            termination_count=8,
        )

        self.assertAlmostEqual(
            result.conductor_linear_feet,
            440.0,
        )

    def test_missing_conductors_requires_review(self):
        result = ElectricalTakeoffEngine.run(
            description="Unknown Feeder",
            length_ft=100,
            provenance=electrical_source(),
            conduit=ElectricalCalloutParser.conduit(
                '2" EMT'
            ),
            conductors=None,
        )

        self.assertTrue(result.requires_review)

    def test_feeder_prices(self):
        takeoff = ElectricalTakeoffEngine.run(
            description="Main Feeder",
            length_ft=100,
            provenance=electrical_source(),
            conduit=ElectricalCalloutParser.conduit(
                '2" EMT'
            ),
            conductors=ElectricalCalloutParser.conductors(
                "4 #3/0 CU"
            ),
            conductor_waste_percent=10,
            termination_count=8,
        )

        result = ElectricalPricingEngine.price_run(
            takeoff=takeoff,
            price_book=price_book(),
            markup=MarkupPolicy(),
            recipe=ElectricalPricingRecipe(
                conduit_material_code="EMT_MAT",
                conduit_labor_code="EMT_LAB",
                conductor_material_code="WIRE_MAT",
                conductor_labor_code="WIRE_LAB",
                termination_code="TERM",
            ),
        )

        codes = {
            component.rate_code
            for component in result.components
        }

        self.assertEqual(
            codes,
            {
                "EMT_MAT",
                "EMT_LAB",
                "WIRE_MAT",
                "WIRE_LAB",
                "TERM",
            },
        )

    def test_missing_electrical_rate_fails_closed(self):
        takeoff = ElectricalTakeoffEngine.run(
            description="Main Feeder",
            length_ft=100,
            provenance=electrical_source(),
            conduit=ElectricalCalloutParser.conduit(
                '2" EMT'
            ),
            conductors=ElectricalCalloutParser.conductors(
                "4 #3/0 CU"
            ),
        )

        with self.assertRaises(MissingRateError):
            ElectricalPricingEngine.price_run(
                takeoff=takeoff,
                price_book=PriceBook(),
                markup=MarkupPolicy(),
                recipe=ElectricalPricingRecipe(
                    conduit_material_code="MISSING"
                ),
            )


class PlumbingMEPTests(unittest.TestCase):

    def test_sanitary_callout(self):
        result = PlumbingCalloutParser.parse(
            '4" PVC SANITARY'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.size_inches, "4")
        self.assertEqual(result.material, "PVC")
        self.assertEqual(
            result.system,
            PlumbingSystem.SANITARY,
        )

    def test_domestic_water_callout(self):
        result = PlumbingCalloutParser.parse(
            '2" COPPER DOMESTIC WATER'
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.system,
            PlumbingSystem.DOMESTIC_WATER,
        )

    def test_unknown_system_requires_review(self):
        pipe = PlumbingCalloutParser.parse(
            '4" PVC'
        )

        result = PlumbingTakeoffEngine.run(
            description="Unknown Pipe",
            length_ft=100,
            pipe=pipe,
            provenance=plumbing_source(),
        )

        self.assertTrue(result.requires_review)

    def test_hanger_count(self):
        pipe = PlumbingCalloutParser.parse(
            '4" PVC SANITARY'
        )

        result = PlumbingTakeoffEngine.run(
            description="Sanitary Main",
            length_ft=100,
            pipe=pipe,
            provenance=plumbing_source(),
            fitting_count=10,
            hanger_spacing_ft=10,
        )

        self.assertEqual(
            result.hanger_count,
            11,
        )

    def test_pipe_prices(self):
        pipe = PlumbingCalloutParser.parse(
            '4" PVC SANITARY'
        )

        takeoff = PlumbingTakeoffEngine.run(
            description="Sanitary Main",
            length_ft=100,
            pipe=pipe,
            provenance=plumbing_source(),
            fitting_count=10,
            hanger_spacing_ft=10,
        )

        result = PlumbingPricingEngine.price_run(
            takeoff=takeoff,
            price_book=price_book(),
            markup=MarkupPolicy(),
            recipe=PlumbingPricingRecipe(
                pipe_material_code="PVC_PIPE",
                pipe_labor_code="PVC_LAB",
                fitting_material_code="PVC_FITTING",
                fitting_labor_code="PVC_FITTING_LAB",
                hanger_material_code="HANGER_MAT",
                hanger_labor_code="HANGER_LAB",
            ),
        )

        codes = {
            component.rate_code
            for component in result.components
        }

        self.assertIn("PVC_PIPE", codes)
        self.assertIn("PVC_FITTING", codes)
        self.assertIn("HANGER_MAT", codes)

    def test_fixture_prices(self):
        takeoff = PlumbingTakeoffEngine.fixture(
            fixture_type="Water Closet",
            quantity=10,
            provenance=plumbing_source(),
        )

        result = PlumbingPricingEngine.price_fixture(
            takeoff=takeoff,
            price_book=price_book(),
            markup=MarkupPolicy(),
            material_code="WC_MAT",
            labor_code="WC_LAB",
        )

        self.assertEqual(
            len(result.components),
            2,
        )


class MEPBridgeTests(unittest.TestCase):

    def test_electrical_enters_goat_estimate(self):
        spine = InMemoryDataSpine()

        workflow = EstimateWorkflowService(
            spine=spine
        )

        estimate = workflow.create_estimate(
            tenant_id=TENANT,
            business_unit_id=BU,
            project_name="MEP Project",
            actor_id="estimator",
        )

        takeoff = ElectricalTakeoffEngine.run(
            description="Main Feeder",
            length_ft=100,
            provenance=electrical_source(),
            conduit=ElectricalCalloutParser.conduit(
                '2" EMT'
            ),
            conductors=ElectricalCalloutParser.conductors(
                "4 #3/0 CU"
            ),
        )

        priced = ElectricalPricingEngine.price_run(
            takeoff=takeoff,
            price_book=price_book(),
            markup=MarkupPolicy(),
            recipe=ElectricalPricingRecipe(
                conduit_material_code="EMT_MAT",
                conduit_labor_code="EMT_LAB",
                conductor_material_code="WIRE_MAT",
                conductor_labor_code="WIRE_LAB",
            ),
        )

        line = MEPEstimateBridge.add_scope(
            workflow=workflow,
            estimate_id=estimate.estimate_id,
            actor_id="estimator",
            priced_scope=priced,
            cost_code="26-0000",
        )

        self.assertEqual(
            line.cost_code,
            "26-0000",
        )

        self.assertIn(
            "electrical.pdf#page=14",
            line.source_refs,
        )

    def test_plumbing_enters_goat_estimate(self):
        spine = InMemoryDataSpine()

        workflow = EstimateWorkflowService(
            spine=spine
        )

        estimate = workflow.create_estimate(
            tenant_id=TENANT,
            business_unit_id=BU,
            project_name="MEP Project",
            actor_id="estimator",
        )

        pipe = PlumbingCalloutParser.parse(
            '4" PVC SANITARY'
        )

        takeoff = PlumbingTakeoffEngine.run(
            description="Sanitary Main",
            length_ft=100,
            pipe=pipe,
            provenance=plumbing_source(),
        )

        priced = PlumbingPricingEngine.price_run(
            takeoff=takeoff,
            price_book=price_book(),
            markup=MarkupPolicy(),
            recipe=PlumbingPricingRecipe(
                pipe_material_code="PVC_PIPE",
                pipe_labor_code="PVC_LAB",
            ),
        )

        line = MEPEstimateBridge.add_scope(
            workflow=workflow,
            estimate_id=estimate.estimate_id,
            actor_id="estimator",
            priced_scope=priced,
            cost_code="22-0000",
        )

        self.assertEqual(
            line.cost_code,
            "22-0000",
        )


if __name__ == "__main__":
    unittest.main()
