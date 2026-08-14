import unittest

from dataclasses import replace

from leadbot_v2.goat.preconstruction.assemblies.structural import (
    AutomaticStructuralTakeoffEngine,
    StructuralAssemblyInferenceEngine,
)
from leadbot_v2.goat.preconstruction.details.resolver import (
    DetailResolutionError,
    DetailResolutionStatus,
    DrawingDetailResolver,
)
from leadbot_v2.goat.preconstruction.documents.models import (
    Discipline,
    DocumentSet,
    DrawingReference,
    ScaleState,
    SheetRecord,
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
)
from leadbot_v2.goat.preconstruction.pricing.engine import (
    ConcreteAssemblyPricingEngine,
    ConcretePricingRecipe,
    CostClass,
    DuplicateRateError,
    EstimatePackage,
    MarkupPolicy,
    MissingRateError,
    PriceBook,
    PricingUnit,
    UnitRate,
    apply_bps,
    money_extension,
)


def sheet(
    *,
    page: int,
    number: str,
    text: str,
    refs=(),
):
    return SheetRecord(
        page_number=page,
        sheet_number=number,
        title="TEST",
        discipline=(
            Discipline.STRUCTURAL
        ),
        text=text,
        references=tuple(refs),
        confidence=0.99,
        source_ref=(
            f"plans.pdf#page={page}"
        ),
    )


def test_document(
    *,
    include_target=True,
    include_detail=True,
):
    reference = DrawingReference(
        detail_number="4",
        sheet_number="S5.2",
        raw="4/S5.2",
        confidence=0.98,
    )

    sheets = [
        sheet(
            page=1,
            number="S2.1",
            text=(
                "FOUNDATION PLAN\n"
                "SEE DETAIL 4/S5.2"
            ),
            refs=(reference,),
        )
    ]

    if include_target:
        target_text = (
            "STRUCTURAL DETAILS\n"
            + (
                'DETAIL 4\nGB-3 24"x36"'
                if include_detail
                else
                'DETAIL 7\nGB-3 24"x36"'
            )
        )

        sheets.append(
            sheet(
                page=2,
                number="S5.2",
                text=target_text,
            )
        )

    return DocumentSet(
        document_id="doc-1",
        source_name="plans.pdf",
        sheets=tuple(sheets),
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


def slab_span():
    return TextSpan(
        text_id="slab-note",
        text=(
            '6" SOG '
            '#5 @ 12" OC EW'
        ),
        bounds=BoundingBox(
            20,
            20,
            40,
            35,
        ),
    )


def automated_slab():
    inference = (
        StructuralAssemblyInferenceEngine()
    )

    candidate = inference.infer(
        document_id="doc-1",
        sheet_number="S2.1",
        page_number=1,
        source_ref="plans.pdf#page=1",
        text_spans=(
            slab_span(),
        ),
        polygons=(
            slab_polygon(),
        ),
        polylines=(),
    )[0]

    return (
        AutomaticStructuralTakeoffEngine()
        .build(
            candidate=candidate,
            calibration=calibration(),
            polygon=slab_polygon(),
            waste_percent=0.0,
            rebar_waste_percent=0.0,
        )
    )


def base_price_book():
    book = PriceBook()

    book.register(
        UnitRate(
            code="CONCRETE_READY_MIX",
            description="Ready Mix Concrete",
            unit=PricingUnit.CY,
            cost_class=(
                CostClass.MATERIAL
            ),
            cents_per_unit=15_000,
            source="Twins Approved Rate",
        )
    )

    book.register(
        UnitRate(
            code=(
                "CONCRETE_PLACEMENT_LABOR"
            ),
            description=(
                "Concrete Placement Labor"
            ),
            unit=PricingUnit.CY,
            cost_class=CostClass.LABOR,
            cents_per_unit=8_000,
            source="Twins Approved Rate",
        )
    )

    book.register(
        UnitRate(
            code="FORMWORK",
            description="Formwork",
            unit=PricingUnit.SF,
            cost_class=CostClass.LABOR,
            cents_per_unit=1_500,
            source="Twins Approved Rate",
        )
    )

    book.register(
        UnitRate(
            code="REBAR_MATERIAL",
            description="Reinforcing Steel",
            unit=PricingUnit.LB,
            cost_class=(
                CostClass.MATERIAL
            ),
            cents_per_unit=85,
            source="Twins Approved Rate",
        )
    )

    book.register(
        UnitRate(
            code="REBAR_INSTALL_LABOR",
            description="Rebar Installation",
            unit=PricingUnit.LB,
            cost_class=CostClass.LABOR,
            cents_per_unit=60,
            source="Twins Approved Rate",
        )
    )

    return book


class DetailResolverTests(
    unittest.TestCase
):

    def test_reference_resolves_to_existing_detail(self):
        document = test_document()

        result = (
            DrawingDetailResolver
            .resolve_all(document)
        )[0]

        self.assertEqual(
            result.status,
            DetailResolutionStatus.RESOLVED,
        )

        self.assertTrue(
            result.resolved
        )

    def test_missing_target_sheet(self):
        document = test_document(
            include_target=False,
        )

        result = (
            DrawingDetailResolver
            .resolve_all(document)
        )[0]

        self.assertEqual(
            result.status,
            DetailResolutionStatus
            .SHEET_MISSING,
        )

    def test_existing_sheet_missing_detail(self):
        document = test_document(
            include_target=True,
            include_detail=False,
        )

        result = (
            DrawingDetailResolver
            .resolve_all(document)
        )[0]

        self.assertEqual(
            result.status,
            DetailResolutionStatus
            .DETAIL_MISSING,
        )

    def test_resolve_all_returns_every_reference(self):
        document = test_document()

        results = (
            DrawingDetailResolver
            .resolve_all(document)
        )

        self.assertEqual(
            len(results),
            1,
        )

    def test_unresolved_resolution_creates_rfi(self):
        document = test_document(
            include_target=False,
        )

        resolutions = (
            DrawingDetailResolver
            .resolve_all(document)
        )

        rfis = (
            DrawingDetailResolver
            .unresolved_to_rfis(
                resolutions
            )
        )

        self.assertEqual(
            len(rfis),
            1,
        )

        self.assertIn(
            "Missing referenced",
            rfis[0].title,
        )

    def test_duplicate_sheet_numbers_rejected(self):
        document = DocumentSet(
            document_id="doc",
            source_name="plans.pdf",
            sheets=(
                sheet(
                    page=1,
                    number="S2.1",
                    text="A",
                ),
                sheet(
                    page=2,
                    number="S2.1",
                    text="B",
                ),
            ),
        )

        with self.assertRaises(
            DetailResolutionError
        ):
            (
                DrawingDetailResolver
                .build_sheet_index(
                    document
                )
            )


class PricingTests(
    unittest.TestCase
):

    def test_unit_rate_negative_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            UnitRate(
                code="BAD",
                description="Bad",
                unit=PricingUnit.CY,
                cost_class=(
                    CostClass.MATERIAL
                ),
                cents_per_unit=-1,
                source="test",
            )

    def test_pricebook_duplicate_rejected(self):
        book = PriceBook()

        rate = UnitRate(
            code="TEST",
            description="Test",
            unit=PricingUnit.CY,
            cost_class=(
                CostClass.MATERIAL
            ),
            cents_per_unit=100,
            source="test",
        )

        book.register(rate)

        with self.assertRaises(
            DuplicateRateError
        ):
            book.register(rate)

    def test_missing_rate_rejected(self):
        with self.assertRaises(
            MissingRateError
        ):
            PriceBook().get(
                code="UNKNOWN",
                unit=PricingUnit.CY,
            )

    def test_extension_rounds_to_cents(self):
        result = money_extension(
            quantity=1.255,
            cents_per_unit=100,
        )

        self.assertEqual(
            result,
            126,
        )

    def test_markup_policy_calculates_integer_cents(self):
        amount = apply_bps(
            amount_cents=100_00,
            basis_points=1500,
        )

        self.assertEqual(
            amount,
            15_00,
        )

    def test_slab_pricing_includes_concrete_material(self):
        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            any(
                item.rate_code
                == "CONCRETE_READY_MIX"
                for item
                in priced.components
            )
        )

    def test_slab_pricing_includes_labor(self):
        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            any(
                item.rate_code
                == (
                    "CONCRETE_PLACEMENT_LABOR"
                )
                for item
                in priced.components
            )
        )

    def test_rebar_material_priced(self):
        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            any(
                item.rate_code
                == "REBAR_MATERIAL"
                for item
                in priced.components
            )
        )

    def test_rebar_labor_priced(self):
        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            any(
                item.rate_code
                == "REBAR_INSTALL_LABOR"
                for item
                in priced.components
            )
        )

    def test_formwork_priced(self):
        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            any(
                item.rate_code
                == "FORMWORK"
                for item
                in priced.components
            )
        )

    def test_equipment_optional(self):
        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
                recipe=(
                    ConcretePricingRecipe(
                        concrete_equipment_code=None,
                    )
                ),
            )
        )

        self.assertFalse(
            any(
                item.cost_class
                == CostClass.EQUIPMENT
                for item
                in priced.components
            )
        )

    def test_priced_assembly_preserves_provenance(self):
        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
            )
        )

        self.assertEqual(
            priced.provenance.sheet_number,
            "S2.1",
        )

        self.assertIn(
            "slab-1",
            priced.provenance.geometry_ids,
        )

    def test_review_flag_propagates(self):
        assembly = automated_slab()

        low_candidate = replace(
            assembly.candidate,
            confidence=0.60,
        )

        low_assembly = replace(
            assembly,
            candidate=low_candidate,
            requires_review=True,
        )

        priced = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=low_assembly,
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(),
            )
        )

        self.assertTrue(
            priced.requires_review
        )

    def test_estimate_package_totals_assemblies(self):
        priced_1 = (
            ConcreteAssemblyPricingEngine
            .price(
                assembly=automated_slab(),
                price_book=(
                    base_price_book()
                ),
                markup=MarkupPolicy(
                    overhead_bps=1000,
                    profit_bps=1500,
                ),
            )
        )

        priced_2 = replace(
            priced_1,
            assembly_id="second",
        )

        package = EstimatePackage(
            estimate_id="estimate-1"
        )

        package.add(
            priced_1
        )

        package.add(
            priced_2
        )

        self.assertEqual(
            package.bid_price_cents,
            priced_1.bid_price_cents
            + priced_2.bid_price_cents,
        )

        self.assertEqual(
            package.direct_cost_cents,
            priced_1.direct_cost_cents
            + priced_2.direct_cost_cents,
        )


if __name__ == "__main__":
    unittest.main()
