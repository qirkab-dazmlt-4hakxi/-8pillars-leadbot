from __future__ import annotations

import unittest

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

from leadbot_v2.goat.multiphysics_engineering import (
    AnalysisDisposition,
    AnalysisNode,
    CalculationIntegrityError,
    ConcreteSectionInputs,
    EarthPressureInputs,
    ElectricalLoad,
    FoundationBearingInputs,
    HVACZoneInputs,
    MultiphysicsEngineeringService,
    MultiphysicsError,
    NodalLoad,
    NumericalFailure,
    PhysicsDomain,
    RandomVariable,
    SoilLayer,
    SteelYieldInputs,
    TrussMember,
    TrussNode,
    solve_linear_system,
)

from leadbot_v2.goat.multiphysics_engineering.persistence import (
    MultiphysicsRepository,
)


class FakeStore:
    def __init__(self):
        self.entities = {}

    def get_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        include_deleted=False,
    ):
        return deepcopy(
            self.entities.get(
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                )
            )
        )

    def put_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        payload,
        actor_id,
        expected_version=None,
    ):
        key = (
            tenant_id,
            entity_type,
            entity_id,
        )

        current = (
            self.entities.get(
                key
            )
        )

        if current is None:
            if expected_version is not None:
                raise RuntimeError(
                    "version conflict"
                )

            version = 1

        else:
            if (
                current.version
                != expected_version
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = (
                current.version
                + 1
            )

        record = SimpleNamespace(
            version=version,
            payload=deepcopy(
                payload
            ),
        )

        self.entities[
            key
        ] = record

        return deepcopy(
            record
        )


class ImportContractTests(
    unittest.TestCase
):
    def test_expected_exports(self):
        import leadbot_v2.goat.multiphysics_engineering as mp

        expected = (
            "CalculationIntegrityError",
            "MultiphysicsEngineeringService",
            "Truss2DSolver",
            "FoundationEngine",
            "ConcreteSectionEngine",
            "SteelYieldEngine",
            "HVACLoadEngine",
            "ElectricalDemandEngine",
            "UncertaintyEngine",
            "AnalysisTraceChain",
        )

        for name in expected:
            self.assertTrue(
                hasattr(
                    mp,
                    name,
                ),
                name,
            )


class NumericsTests(
    unittest.TestCase
):
    def test_linear_system(self):
        result = solve_linear_system(
            (
                (
                    3.0,
                    2.0,
                ),
                (
                    1.0,
                    2.0,
                ),
            ),
            (
                5.0,
                5.0,
            ),
        )

        self.assertAlmostEqual(
            result.solution[0],
            0.0,
            places=10,
        )

        self.assertAlmostEqual(
            result.solution[1],
            2.5,
            places=10,
        )

        self.assertTrue(
            result.converged
        )

    def test_singular_system_fails(
        self,
    ):
        with self.assertRaises(
            NumericalFailure
        ):
            solve_linear_system(
                (
                    (
                        1.0,
                        2.0,
                    ),
                    (
                        2.0,
                        4.0,
                    ),
                ),
                (
                    1.0,
                    2.0,
                ),
            )


class StructuralTests(
    unittest.TestCase
):
    def test_horizontal_bar(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = service.structural.solve(
            nodes=(
                TrussNode(
                    node_id="n1",
                    x=0.0,
                    y=0.0,
                    restrained_x=True,
                    restrained_y=True,
                ),
                TrussNode(
                    node_id="n2",
                    x=100.0,
                    y=0.0,
                    restrained_y=True,
                ),
            ),
            members=(
                TrussMember(
                    member_id="m1",
                    node_i="n1",
                    node_j="n2",
                    area=2.0,
                    elastic_modulus=29000.0,
                ),
            ),
            loads=(
                NodalLoad(
                    node_id="n2",
                    fx=10.0,
                ),
            ),
        )

        expected = (
            10.0
            * 100.0
            / (
                29000.0
                * 2.0
            )
        )

        self.assertAlmostEqual(
            result
            .node_displacements[
                "n2"
            ][0],
            expected,
            places=10,
        )

        self.assertAlmostEqual(
            result
            .member_results[0]
            .axial_force,
            10.0,
            places=8,
        )

        self.assertAlmostEqual(
            result
            .support_reactions[
                "n1"
            ][0],
            -10.0,
            places=8,
        )

        self.assertLess(
            result.equilibrium_error,
            1.0e-8,
        )


class GeotechnicalTests(
    unittest.TestCase
):
    def test_effective_stress(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = (
            service.effective_stress
            .calculate(
                layers=(
                    SoilLayer(
                        layer_id="soil",
                        thickness_ft=20.0,
                        total_unit_weight_pcf=120.0,
                        saturated_unit_weight_pcf=125.0,
                    ),
                ),
                depth_ft=10.0,
                groundwater_depth_ft=5.0,
            )
        )

        self.assertGreater(
            result.total_vertical_stress_psf,
            result
            .effective_vertical_stress_psf,
        )

        self.assertGreater(
            result.pore_pressure_psf,
            0.0,
        )

    def test_bearing_screen(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = (
            service.foundations
            .bearing_screen(
                FoundationBearingInputs(
                    service_load_kips=100.0,
                    footing_area_sf=50.0,
                    allowable_bearing_psf=3000.0,
                )
            )
        )

        self.assertAlmostEqual(
            result.gross_pressure_psf,
            2000.0,
        )

        self.assertTrue(
            result.passes_screen
        )

    def test_settlement(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = (
            service.foundations
            .settlement_screen(
                net_pressure_psf=2000.0,
                layers=(
                    SoilLayer(
                        layer_id="a",
                        thickness_ft=5.0,
                        total_unit_weight_pcf=120.0,
                        constrained_modulus_psf=200000.0,
                        settlement_influence_factor=1.0,
                    ),
                    SoilLayer(
                        layer_id="b",
                        thickness_ft=5.0,
                        total_unit_weight_pcf=120.0,
                        constrained_modulus_psf=400000.0,
                        settlement_influence_factor=0.5,
                    ),
                ),
            )
        )

        self.assertGreater(
            result.settlement_inches,
            0.0,
        )

    def test_water_increases_earth_pressure(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        dry = service.earth_pressure.active(
            EarthPressureInputs(
                retained_height_ft=10,
                soil_unit_weight_pcf=120,
                friction_angle_deg=30,
                surcharge_psf=100,
                water_height_ft=0,
            )
        )

        wet = service.earth_pressure.active(
            EarthPressureInputs(
                retained_height_ft=10,
                soil_unit_weight_pcf=120,
                friction_angle_deg=30,
                surcharge_psf=100,
                water_height_ft=10,
            )
        )

        self.assertGreater(
            wet.total_thrust_lb_per_ft,
            dry.total_thrust_lb_per_ft,
        )


class MaterialsTests(
    unittest.TestCase
):
    def test_concrete_capacity(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = (
            service.concrete
            .rectangular_flexure(
                ConcreteSectionInputs(
                    width_in=12.0,
                    effective_depth_in=20.0,
                    reinforcement_area_in2=2.0,
                    concrete_strength_psi=4000.0,
                    steel_yield_strength_psi=60000.0,
                    compression_stress_factor=0.85,
                    compression_block_factor=0.85,
                    resistance_factor=0.90,
                    source_fact_ids=(
                        "official-rule",
                    ),
                )
            )
        )

        self.assertGreater(
            result.design_moment_kip_ft,
            0.0,
        )

        self.assertLess(
            result.design_moment_kip_ft,
            result.nominal_moment_kip_ft,
        )

        self.assertTrue(
            result
            .professional_review_required
        )

    def test_steel_screen(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = (
            service.steel
            .gross_section(
                SteelYieldInputs(
                    area_in2=10.0,
                    section_modulus_in3=100.0,
                    yield_strength_ksi=50.0,
                    axial_resistance_factor=0.9,
                    flexural_resistance_factor=0.9,
                    source_fact_ids=(
                        "official-rule",
                    ),
                )
            )
        )

        self.assertEqual(
            result
            .nominal_axial_capacity_kips,
            500.0,
        )

        self.assertTrue(
            result
            .stability_check_required
        )


class MEPTests(
    unittest.TestCase
):
    def test_hvac_load(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = service.hvac.zone_load(
            HVACZoneInputs(
                zone_id="zone",
                opaque_area_sf=1000,
                opaque_u_value=0.05,
                glazing_area_sf=200,
                glazing_u_value=0.30,
                design_delta_t_f=30,
                infiltration_cfm=200,
                sensible_air_coefficient=1.08,
                latent_air_coefficient=0.68,
                humidity_difference=30,
                occupant_count=10,
                sensible_btu_per_person=250,
                latent_btu_per_person=200,
                equipment_sensible_btu_hr=5000,
                solar_glazing_btu_hr=4000,
            )
        )

        self.assertAlmostEqual(
            result.total_btu_hr,
            (
                result.total_sensible_btu_hr
                + result.total_latent_btu_hr
            ),
        )

    def test_electrical_demand(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        result = (
            service.electrical
            .aggregate(
                (
                    ElectricalLoad(
                        load_id="a",
                        connected_kva=100,
                        demand_factor=0.8,
                    ),
                    ElectricalLoad(
                        load_id="b",
                        connected_kva=50,
                        demand_factor=0.5,
                    ),
                )
            )
        )

        self.assertEqual(
            result.connected_kva,
            150.0,
        )

        self.assertEqual(
            result.diversified_kva,
            105.0,
        )


class GraphTests(
    unittest.TestCase
):
    def test_dependency_execution(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        service.graph.add_node(
            AnalysisNode(
                node_id="soil",
                domain=(
                    PhysicsDomain
                    .GEOTECHNICAL
                ),
                dependencies=(),
                evaluator=lambda ctx:
                    2000.0,
            )
        )

        service.graph.add_node(
            AnalysisNode(
                node_id="foundation",
                domain=(
                    PhysicsDomain
                    .STRUCTURAL
                ),
                dependencies=(
                    "soil",
                ),
                evaluator=lambda ctx:
                    ctx[
                        "dependencies"
                    ][
                        "soil"
                    ]
                    * 0.75,
            )
        )

        result = (
            service.graph.execute()
        )

        self.assertEqual(
            result.execution_order,
            (
                "soil",
                "foundation",
            ),
        )

        self.assertEqual(
            result.values[
                "foundation"
            ],
            1500.0,
        )

    def test_cycle_rejected(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        service.graph.add_node(
            AnalysisNode(
                node_id="a",
                domain=(
                    PhysicsDomain.STRUCTURAL
                ),
                dependencies=(
                    "b",
                ),
                evaluator=lambda ctx:
                    1,
            )
        )

        service.graph.add_node(
            AnalysisNode(
                node_id="b",
                domain=(
                    PhysicsDomain.GEOTECHNICAL
                ),
                dependencies=(
                    "a",
                ),
                evaluator=lambda ctx:
                    1,
            )
        )

        with self.assertRaises(
            MultiphysicsError
        ):
            service.graph.execution_order()


class UncertaintyTests(
    unittest.TestCase
):
    def test_seeded_determinism(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        kwargs = dict(
            variables=(
                RandomVariable(
                    name="load",
                    mean=100.0,
                    standard_deviation=10.0,
                    minimum=0.0,
                ),
                RandomVariable(
                    name="capacity",
                    mean=150.0,
                    standard_deviation=15.0,
                    minimum=1.0,
                ),
            ),
            evaluator=lambda values:
                (
                    values["load"]
                    / values["capacity"]
                ),
            samples=2000,
            seed=42,
        )

        first = (
            service.uncertainty
            .simulate(
                **kwargs
            )
        )

        second = (
            service.uncertainty
            .simulate(
                **kwargs
            )
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertLess(
            first.p05,
            first.p95,
        )


class DiagnosticTests(
    unittest.TestCase
):
    def test_overutilization_failure(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        diagnostic = (
            service.diagnostics
            .utilization(
                domain=(
                    PhysicsDomain
                    .STRUCTURAL
                ),
                name="beam",
                demand=120.0,
                capacity=100.0,
            )
        )

        self.assertEqual(
            diagnostic.disposition,
            AnalysisDisposition.FAIL,
        )

    def test_professional_review_blocks_release(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        diagnostic = (
            service.diagnostics
            .utilization(
                domain=(
                    PhysicsDomain
                    .STRUCTURAL
                ),
                name="member",
                demand=20.0,
                capacity=100.0,
                professional_review_required=True,
            )
        )

        self.assertEqual(
            diagnostic.disposition,
            AnalysisDisposition.PASS,
        )

        self.assertFalse(
            service.diagnostics
            .release_allowed(
                (
                    diagnostic,
                )
            )
        )


class TraceTests(
    unittest.TestCase
):
    def test_trace_chain(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        service.record_analysis(
            analysis_id="a",
            engine="solver",
            engine_version="1",
            domain=(
                PhysicsDomain.STRUCTURAL
            ),
            inputs={
                "load":
                    10
            },
            outputs={
                "reaction":
                    10
            },
            source_fact_ids=(
                "fact",
            ),
        )

        trace = service.record_analysis(
            analysis_id="b",
            engine="solver",
            engine_version="1",
            domain=(
                PhysicsDomain.GEOTECHNICAL
            ),
            inputs={
                "pressure":
                    1000
            },
            outputs={
                "settlement":
                    0.5
            },
            source_fact_ids=(
                "fact-2",
            ),
        )

        self.assertTrue(
            service.traces.verify()
        )

        tampered = replace(
            trace,
            outputs={
                "settlement":
                    999
            },
        )

        with self.assertRaises(
            CalculationIntegrityError
        ):
            service.traces.verify_trace(
                tampered
            )


class PersistenceTests(
    unittest.TestCase
):
    def test_trace_persists(
        self,
    ):
        store = FakeStore()

        repository = (
            MultiphysicsRepository(
                store,
                tenant_id="tenant",
            )
        )

        service = (
            MultiphysicsEngineeringService(
                repository=repository
            )
        )

        service.record_analysis(
            analysis_id="analysis",
            engine="goat-test",
            engine_version="1",
            domain=(
                PhysicsDomain.STRUCTURAL
            ),
            inputs={
                "x":
                    1
            },
            outputs={
                "y":
                    2
            },
            source_fact_ids=(
                "fact",
            ),
        )

        entity_types = {
            key[1]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.multiphysics.analysis_trace",
            entity_types,
        )


class StressTests(
    unittest.TestCase
):
    def test_20000_foundation_screens(
        self,
    ):
        service = (
            MultiphysicsEngineeringService()
        )

        inputs = FoundationBearingInputs(
            service_load_kips=200,
            footing_area_sf=100,
            allowable_bearing_psf=3000,
        )

        for _ in range(20000):
            result = (
                service.foundations
                .bearing_screen(
                    inputs
                )
            )

            self.assertLess(
                result.utilization,
                1.0,
            )


if __name__ == "__main__":
    unittest.main()
