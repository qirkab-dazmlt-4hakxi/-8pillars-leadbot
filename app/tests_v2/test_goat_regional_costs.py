import json
import tempfile
import unittest

from datetime import date
from pathlib import Path

from leadbot_v2.goat.preconstruction.pricing.engine import (
    CostClass,
    PriceBook,
    PricingUnit,
)
from leadbot_v2.goat.preconstruction.regional_costs.engine import (
    CostRecord,
    DuplicateCostRecordError,
    FreshnessPolicy,
    FreshnessStatus,
    LaborBasis,
    LaborBurdenModel,
    RateContext,
    RegionalCostCatalog,
    RegionalPriceBookBuilder,
    RegionalRateResolver,
    SourceKind,
    TexasMarket,
    TexasMarketRegistry,
    UnresolvedRateError,
)
from leadbot_v2.goat.preconstruction.regional_costs.ingest import (
    CostDataIngestError,
    load_json_records,
)


AS_OF = date(
    2026,
    8,
    14,
)


def record(
    *,
    record_id,
    source_kind,
    market,
    effective,
    material=0,
    labor=0,
    equipment=0,
    trade="concrete",
    description="4000 PSI Ready Mix",
    unit=PricingUnit.CY,
    confidence=0.95,
    project_id=None,
    labor_basis=(
        LaborBasis.OPEN_SHOP
    ),
):
    return CostRecord(
        record_id=record_id,
        source_kind=source_kind,
        source_name=(
            source_kind.value
        ),
        source_item_id=record_id,
        trade=trade,
        description=description,
        csi_division="03",
        cost_code="03-3000",
        unit=unit,
        market=market,
        material_cents_per_unit=(
            material
        ),
        labor_cents_per_unit=(
            labor
        ),
        equipment_cents_per_unit=(
            equipment
        ),
        labor_basis=labor_basis,
        effective_date=effective,
        confidence=confidence,
        project_id=project_id,
    )


class TexasMarketTests(
    unittest.TestCase
):

    def test_dallas_maps_to_dfw(self):
        self.assertEqual(
            TexasMarketRegistry.resolve(
                city="Dallas"
            ),
            TexasMarket.DFW,
        )

    def test_frisco_maps_to_dfw(self):
        self.assertEqual(
            TexasMarketRegistry.resolve(
                city="Frisco"
            ),
            TexasMarket.DFW,
        )

    def test_houston_maps_to_houston(self):
        self.assertEqual(
            TexasMarketRegistry.resolve(
                city="Houston"
            ),
            TexasMarket.HOUSTON,
        )

    def test_austin_maps_to_austin(self):
        self.assertEqual(
            TexasMarketRegistry.resolve(
                city="Austin"
            ),
            TexasMarket.AUSTIN,
        )

    def test_midland_maps_west_texas(self):
        self.assertEqual(
            TexasMarketRegistry.resolve(
                city="Midland"
            ),
            TexasMarket.MIDLAND_ODESSA,
        )

    def test_unknown_city_fails_closed(self):
        with self.assertRaises(
            UnresolvedRateError
        ):
            TexasMarketRegistry.resolve(
                city="Unknown Place"
            )

    def test_explicit_market_allowed(self):
        self.assertEqual(
            TexasMarketRegistry.resolve(
                city=None,
                explicit_market=(
                    TexasMarket
                    .RIO_GRANDE_VALLEY
                ),
            ),
            TexasMarket
            .RIO_GRANDE_VALLEY,
        )


class CatalogTests(
    unittest.TestCase
):

    def test_duplicate_record_rejected(self):
        catalog = (
            RegionalCostCatalog()
        )

        item = record(
            record_id="x",
            source_kind=(
                SourceKind.RSMEANS
            ),
            market=TexasMarket.DFW,
            effective=date(
                2026,
                7,
                1,
            ),
            material=15000,
        )

        catalog.register(
            item
        )

        with self.assertRaises(
            DuplicateCostRecordError
        ):
            catalog.register(
                item
            )

    def test_query_filters_trade(self):
        catalog = (
            RegionalCostCatalog()
        )

        catalog.register_many(
            (
                record(
                    record_id="c",
                    source_kind=(
                        SourceKind.RSMEANS
                    ),
                    market=TexasMarket.DFW,
                    effective=date(
                        2026,
                        7,
                        1,
                    ),
                    material=15000,
                ),
                record(
                    record_id="e",
                    source_kind=(
                        SourceKind.RSMEANS
                    ),
                    market=TexasMarket.DFW,
                    effective=date(
                        2026,
                        7,
                        1,
                    ),
                    material=500,
                    trade="electrical",
                    description="EMT",
                    unit=PricingUnit.LF,
                ),
            )
        )

        result = catalog.query(
            trade="concrete",
            unit=PricingUnit.CY,
        )

        self.assertEqual(
            len(result),
            1,
        )


class FreshnessTests(
    unittest.TestCase
):

    def resolver(self):
        return RegionalRateResolver(
            catalog=(
                RegionalCostCatalog()
            )
        )

    def test_recent_rsmeans_is_current(self):
        item = record(
            record_id="r",
            source_kind=(
                SourceKind.RSMEANS
            ),
            market=TexasMarket.DFW,
            effective=date(
                2026,
                7,
                1,
            ),
            material=15000,
        )

        self.assertEqual(
            self.resolver()
            .freshness(
                record=item,
                as_of=AS_OF,
            ),
            FreshnessStatus.CURRENT,
        )

    def test_old_project_quote_is_stale(self):
        item = record(
            record_id="q",
            source_kind=(
                SourceKind.PROJECT_QUOTE
            ),
            market=TexasMarket.DFW,
            effective=date(
                2026,
                5,
                1,
            ),
            material=15000,
        )

        self.assertEqual(
            self.resolver()
            .freshness(
                record=item,
                as_of=AS_OF,
            ),
            FreshnessStatus.STALE,
        )


class ResolutionTests(
    unittest.TestCase
):

    def resolver(
        self,
        *items,
    ):
        catalog = (
            RegionalCostCatalog()
        )

        catalog.register_many(
            items
        )

        return RegionalRateResolver(
            catalog=catalog
        )

    def context(
        self,
        market=TexasMarket.DFW,
        project_id=None,
        prevailing=False,
    ):
        return RateContext(
            market=market,
            as_of=AS_OF,
            project_id=project_id,
            prevailing_wage_required=(
                prevailing
            ),
        )

    def test_project_quote_beats_rsmeans(self):
        resolved = self.resolver(
            record(
                record_id="rs",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    7,
                    1,
                ),
                material=15000,
            ),
            record(
                record_id="quote",
                source_kind=(
                    SourceKind.PROJECT_QUOTE
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    8,
                    10,
                ),
                material=14200,
                project_id="P1",
            ),
        ).resolve(
            trade="concrete",
            unit=PricingUnit.CY,
            context=self.context(
                project_id="P1"
            ),
        )

        self.assertEqual(
            resolved.record.record_id,
            "quote",
        )

    def test_negotiated_rate_beats_rsmeans(self):
        resolved = self.resolver(
            record(
                record_id="rs",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    7,
                    1,
                ),
                material=15000,
            ),
            record(
                record_id="neg",
                source_kind=(
                    SourceKind
                    .NEGOTIATED_COMPANY_RATE
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    8,
                    1,
                ),
                material=14500,
            ),
        ).resolve(
            trade="concrete",
            unit=PricingUnit.CY,
            context=self.context(),
        )

        self.assertEqual(
            resolved.record.record_id,
            "neg",
        )

    def test_dallas_rate_does_not_price_houston(self):
        resolver = self.resolver(
            record(
                record_id="dfw",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    7,
                    1,
                ),
                material=15000,
            )
        )

        with self.assertRaises(
            UnresolvedRateError
        ):
            resolver.resolve(
                trade="concrete",
                unit=PricingUnit.CY,
                context=self.context(
                    market=(
                        TexasMarket.HOUSTON
                    )
                ),
            )

    def test_houston_rate_is_selected_for_houston(self):
        resolved = self.resolver(
            record(
                record_id="dfw",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    7,
                    1,
                ),
                material=15000,
            ),
            record(
                record_id="hou",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=(
                    TexasMarket.HOUSTON
                ),
                effective=date(
                    2026,
                    7,
                    1,
                ),
                material=16000,
            ),
        ).resolve(
            trade="concrete",
            unit=PricingUnit.CY,
            context=self.context(
                market=TexasMarket.HOUSTON
            ),
        )

        self.assertEqual(
            resolved.record.record_id,
            "hou",
        )

    def test_statewide_fallback_allowed(self):
        resolved = self.resolver(
            record(
                record_id="state",
                source_kind=(
                    SourceKind
                    .PUBLIC_BENCHMARK
                ),
                market=(
                    TexasMarket.STATEWIDE
                ),
                effective=date(
                    2026,
                    5,
                    1,
                ),
                material=14000,
            )
        ).resolve(
            trade="concrete",
            unit=PricingUnit.CY,
            context=self.context(),
        )

        self.assertEqual(
            resolved.record.record_id,
            "state",
        )

    def test_stale_rate_fails_when_current_required(self):
        resolver = self.resolver(
            record(
                record_id="old",
                source_kind=(
                    SourceKind.PROJECT_QUOTE
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    1,
                    1,
                ),
                material=15000,
            )
        )

        with self.assertRaises(
            UnresolvedRateError
        ):
            resolver.resolve(
                trade="concrete",
                unit=PricingUnit.CY,
                context=self.context(),
            )

    def test_prevailing_wage_required_blocks_open_shop(self):
        resolver = self.resolver(
            record(
                record_id="open",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    7,
                    1,
                ),
                labor=5000,
                labor_basis=(
                    LaborBasis.OPEN_SHOP
                ),
            )
        )

        with self.assertRaises(
            UnresolvedRateError
        ):
            resolver.resolve(
                trade="concrete",
                unit=PricingUnit.CY,
                cost_class=(
                    CostClass.LABOR
                ),
                context=self.context(
                    prevailing=True
                ),
            )

    def test_prevailing_record_used_when_required(self):
        resolved = self.resolver(
            record(
                record_id="open",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    7,
                    1,
                ),
                labor=5000,
                labor_basis=(
                    LaborBasis.OPEN_SHOP
                ),
            ),
            record(
                record_id="wd",
                source_kind=(
                    SourceKind
                    .PREVAILING_WAGE
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    6,
                    1,
                ),
                labor=8000,
                labor_basis=(
                    LaborBasis.PREVAILING
                ),
            ),
        ).resolve(
            trade="concrete",
            unit=PricingUnit.CY,
            cost_class=(
                CostClass.LABOR
            ),
            context=self.context(
                prevailing=True
            ),
        )

        self.assertEqual(
            resolved.record.record_id,
            "wd",
        )


class LaborBurdenTests(
    unittest.TestCase
):

    def test_loaded_labor_exceeds_base_wage(self):
        model = LaborBurdenModel(
            base_wage_cents_per_hour=3000,
            benefits_cents_per_hour=500,
            payroll_tax_bps=1000,
            workers_comp_bps=500,
            supervision_bps=500,
        )

        self.assertGreater(
            model.loaded_hourly_cents,
            3000,
        )

    def test_low_productivity_increases_effective_cost(self):
        normal = LaborBurdenModel(
            base_wage_cents_per_hour=3000,
            productivity_factor=1.0,
        )

        reduced = LaborBurdenModel(
            base_wage_cents_per_hour=3000,
            productivity_factor=0.75,
        )

        self.assertGreater(
            reduced.loaded_hourly_cents,
            normal.loaded_hourly_cents,
        )


class PriceBookBridgeTests(
    unittest.TestCase
):

    def test_resolved_material_enters_pricebook(self):
        catalog = (
            RegionalCostCatalog()
        )

        catalog.register(
            record(
                record_id="rs",
                source_kind=(
                    SourceKind.RSMEANS
                ),
                market=TexasMarket.DFW,
                effective=date(
                    2026,
                    7,
                    1,
                ),
                material=15500,
            )
        )

        resolved = (
            RegionalRateResolver(
                catalog=catalog
            )
            .resolve(
                trade="concrete",
                unit=PricingUnit.CY,
                context=RateContext(
                    market=TexasMarket.DFW,
                    as_of=AS_OF,
                ),
            )
        )

        book = PriceBook()

        rate = (
            RegionalPriceBookBuilder
            .add_component(
                price_book=book,
                resolved=resolved,
                code=(
                    "CONCRETE_READY_MIX"
                ),
                description=(
                    "Ready Mix Concrete"
                ),
                cost_class=(
                    CostClass.MATERIAL
                ),
            )
        )

        self.assertEqual(
            rate.cents_per_unit,
            15500,
        )


class IngestTests(
    unittest.TestCase
):

    def test_json_ingest(self):
        payload = [
            {
                "record_id": "test-1",
                "source_kind": "rsmeans",
                "source_name": (
                    "Licensed RSMeans"
                ),
                "trade": "concrete",
                "description": (
                    "4000 PSI Ready Mix"
                ),
                "unit": "CY",
                "market": (
                    "dallas_fort_worth"
                ),
                "material_cents_per_unit":
                    15000,
                "effective_date":
                    "2026-07-01",
                "confidence": 0.99,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(
                tmp
            ) / "costs.json"

            path.write_text(
                json.dumps(
                    payload
                )
            )

            records = (
                load_json_records(
                    path
                )
            )

        self.assertEqual(
            len(records),
            1,
        )

        self.assertEqual(
            records[0].market,
            TexasMarket.DFW,
        )

    def test_invalid_json_shape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(
                tmp
            ) / "bad.json"

            path.write_text(
                json.dumps(
                    {
                        "not":
                            "a list"
                    }
                )
            )

            with self.assertRaises(
                CostDataIngestError
            ):
                load_json_records(
                    path
                )


if __name__ == "__main__":
    unittest.main()
