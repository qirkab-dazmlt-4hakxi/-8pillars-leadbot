from __future__ import annotations

import unittest

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from leadbot_v2.goat.engineering_codes import (
    AdoptionStatus,
    CalculationIntegrityError,
    CodeAdoption,
    CodeAmendment,
    CodeAuthority,
    CodeResolutionError,
    ComplianceStatus,
    EngineeringCodeRepository,
    EngineeringCodeService,
    EngineeringDiscipline,
    Jurisdiction,
    JurisdictionType,
    LoadCase,
    LoadCombination,
    LoadFactor,
    ProjectEngineeringContext,
    RequirementSeverity,
    RuleRequirement,
    StructureContext,
    WaterIntrusionInputs,
    WaterRiskLevel,
)


NOW = datetime(
    2026,
    8,
    17,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeStore:
    def __init__(
        self,
    ):
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


def build_jurisdictions(
    service,
):
    service.add_jurisdiction(
        Jurisdiction(
            jurisdiction_id="tx",
            name="Texas",
            jurisdiction_type=(
                JurisdictionType.STATE
            ),
        )
    )

    service.add_jurisdiction(
        Jurisdiction(
            jurisdiction_id="tarrant",
            name="Tarrant County",
            jurisdiction_type=(
                JurisdictionType.COUNTY
            ),
            parent_id="tx",
        )
    )

    service.add_jurisdiction(
        Jurisdiction(
            jurisdiction_id="fort-worth",
            name="Fort Worth",
            jurisdiction_type=(
                JurisdictionType.CITY
            ),
            parent_id="tarrant",
        )
    )

    service.add_jurisdiction(
        Jurisdiction(
            jurisdiction_id="fort-worth-ahj",
            name="Fort Worth AHJ",
            jurisdiction_type=(
                JurisdictionType.AHJ
            ),
            parent_id="fort-worth",
        )
    )


class JurisdictionTests(
    unittest.TestCase
):
    def test_path_is_root_to_ahj(
        self,
    ):
        service = EngineeringCodeService()

        build_jurisdictions(
            service
        )

        path = (
            service.jurisdictions
            .path_root_to_leaf(
                "fort-worth-ahj"
            )
        )

        self.assertEqual(
            tuple(
                node.jurisdiction_id
                for node
                in path
            ),
            (
                "tx",
                "tarrant",
                "fort-worth",
                "fort-worth-ahj",
            ),
        )


class CodeResolutionTests(
    unittest.TestCase
):
    def test_more_specific_adoption_wins(
        self,
    ):
        service = EngineeringCodeService()

        build_jurisdictions(
            service
        )

        service.add_adoption(
            CodeAdoption(
                adoption_id="state",
                jurisdiction_id="tx",
                discipline=(
                    EngineeringDiscipline
                    .STRUCTURAL
                ),
                code_family="TEST-STRUCTURAL",
                edition="2021",
                effective_from=(
                    date(
                        2024,
                        1,
                        1,
                    )
                ),
                effective_until=None,
                authority=(
                    CodeAuthority.ADOPTED
                ),
                status=(
                    AdoptionStatus.ACTIVE
                ),
                source_fact_id=(
                    "world-fact-state"
                ),
            )
        )

        service.add_adoption(
            CodeAdoption(
                adoption_id="city",
                jurisdiction_id="fort-worth",
                discipline=(
                    EngineeringDiscipline
                    .STRUCTURAL
                ),
                code_family="TEST-STRUCTURAL",
                edition="2024",
                effective_from=(
                    date(
                        2025,
                        1,
                        1,
                    )
                ),
                effective_until=None,
                authority=(
                    CodeAuthority.OFFICIAL
                ),
                status=(
                    AdoptionStatus.ACTIVE
                ),
                source_fact_id=(
                    "world-fact-city"
                ),
            )
        )

        stack = service.resolve_code_stack(
            project_jurisdiction_id=(
                "fort-worth-ahj"
            ),
            discipline=(
                EngineeringDiscipline
                .STRUCTURAL
            ),
            project_date=(
                date(
                    2026,
                    8,
                    17,
                )
            ),
            code_family=(
                "TEST-STRUCTURAL"
            ),
        )

        self.assertEqual(
            stack.adoption.edition,
            "2024",
        )

        self.assertTrue(
            stack.authoritative
        )

    def test_local_amendment_is_layered(
        self,
    ):
        service = EngineeringCodeService()

        build_jurisdictions(
            service
        )

        service.add_adoption(
            CodeAdoption(
                adoption_id="city",
                jurisdiction_id="fort-worth",
                discipline=(
                    EngineeringDiscipline
                    .CONCRETE
                ),
                code_family="TEST-CONCRETE",
                edition="A",
                effective_from=(
                    date(
                        2025,
                        1,
                        1,
                    )
                ),
                effective_until=None,
                authority=(
                    CodeAuthority.OFFICIAL
                ),
                status=(
                    AdoptionStatus.ACTIVE
                ),
                source_fact_id=(
                    "fact-adoption"
                ),
            )
        )

        service.add_amendment(
            CodeAmendment(
                amendment_id="amendment",
                jurisdiction_id=(
                    "fort-worth"
                ),
                discipline=(
                    EngineeringDiscipline
                    .CONCRETE
                ),
                code_family=(
                    "TEST-CONCRETE"
                ),
                section="X.1",
                operation="replace",
                payload={
                    "requirement":
                        "local amendment"
                },
                effective_from=(
                    date(
                        2025,
                        1,
                        1,
                    )
                ),
                effective_until=None,
                source_fact_id=(
                    "fact-amendment"
                ),
            )
        )

        stack = service.resolve_code_stack(
            project_jurisdiction_id=(
                "fort-worth-ahj"
            ),
            discipline=(
                EngineeringDiscipline
                .CONCRETE
            ),
            project_date=(
                date(
                    2026,
                    8,
                    17,
                )
            ),
        )

        self.assertEqual(
            len(
                stack.amendments
            ),
            1,
        )

        self.assertIn(
            "fact-amendment",
            stack.source_fact_ids,
        )


class ApplicabilityTests(
    unittest.TestCase
):
    def test_underground_activates_geotech_waterproofing(
        self,
    ):
        service = EngineeringCodeService()

        context = ProjectEngineeringContext(
            project_id="project",
            jurisdiction_id="fort-worth",
            project_date=(
                date(
                    2026,
                    8,
                    17,
                )
            ),
            structure_context=(
                StructureContext.UNDERGROUND
            ),
            stories_below_grade=2,
            project_tags=frozenset(
                {
                    "concrete",
                    "excavation",
                }
            ),
        )

        disciplines = (
            service.applicability
            .determine(
                context
            )
        )

        self.assertIn(
            EngineeringDiscipline
            .GEOTECHNICAL,
            disciplines,
        )

        self.assertIn(
            EngineeringDiscipline
            .WATERPROOFING,
            disciplines,
        )

        self.assertIn(
            EngineeringDiscipline
            .EARTHWORK,
            disciplines,
        )

        self.assertIn(
            EngineeringDiscipline
            .CONCRETE,
            disciplines,
        )


class WaterTests(
    unittest.TestCase
):
    def test_hydrostatic_pressure(
        self,
    ):
        service = EngineeringCodeService()

        result = (
            service
            .assess_water_intrusion(
                assessment_id="water",
                inputs=(
                    WaterIntrusionInputs(
                        lowest_structural_elevation_ft=90.0,
                        groundwater_elevation_ft=100.0,
                        design_flood_elevation_ft=98.0,
                        below_grade_wall_height_ft=12.0,
                        slab_area_sf=1000.0,
                        soil_permeability_index=0.7,
                        waterproofing_reliability=0.8,
                        drainage_reliability=0.8,
                        sump_reliability=0.8,
                        redundancy_count=2,
                    )
                ),
            )
        )

        self.assertAlmostEqual(
            result.hydrostatic_head_ft,
            10.0,
        )

        self.assertAlmostEqual(
            result.base_pressure_psi,
            4.3333333333,
            places=5,
        )

        self.assertGreater(
            result.estimated_uplift_kips,
            600.0,
        )

        self.assertIn(
            result.risk_level,
            {
                WaterRiskLevel.HIGH,
                WaterRiskLevel.CRITICAL,
            },
        )

        self.assertTrue(
            result
            .professional_review_required
        )

    def test_dry_site_screening(
        self,
    ):
        service = EngineeringCodeService()

        result = service.water.assess(
            WaterIntrusionInputs(
                lowest_structural_elevation_ft=100.0,
                groundwater_elevation_ft=90.0,
                design_flood_elevation_ft=95.0,
                below_grade_wall_height_ft=4.0,
                slab_area_sf=1000,
                soil_permeability_index=0.05,
                waterproofing_reliability=0.98,
                drainage_reliability=0.98,
                sump_reliability=0.98,
                redundancy_count=2,
            )
        )

        self.assertEqual(
            result.hydrostatic_head_ft,
            0.0,
        )

        self.assertEqual(
            result.risk_level,
            WaterRiskLevel.LOW,
        )


class LoadCalculationTests(
    unittest.TestCase
):
    def test_configurable_load_combination(
        self,
    ):
        service = EngineeringCodeService()

        combination = LoadCombination(
            combination_id="combo",
            name="Official supplied combination",
            factors=(
                LoadFactor(
                    load_case="D",
                    factor=(
                        Decimal(
                            "1.2"
                        )
                    ),
                ),
                LoadFactor(
                    load_case="L",
                    factor=(
                        Decimal(
                            "1.6"
                        )
                    ),
                ),
            ),
            source_fact_id=(
                "official-load-rule"
            ),
            code_family="TEST",
            edition="X",
        )

        result, trace = (
            service
            .evaluate_load_combination(
                combination=(
                    combination
                ),
                load_cases=(
                    LoadCase(
                        name="D",
                        value=(
                            Decimal(
                                "100"
                            )
                        ),
                        unit="kip",
                    ),
                    LoadCase(
                        name="L",
                        value=(
                            Decimal(
                                "50"
                            )
                        ),
                        unit="kip",
                    ),
                ),
                source_fact_ids=(
                    "official-load-rule",
                ),
                calculation_id="calc",
            )
        )

        self.assertEqual(
            result.result,
            Decimal(
                "200.0"
            ),
        )

        self.assertTrue(
            service.calculations.verify()
        )

        self.assertEqual(
            trace.source_fact_ids,
            (
                "official-load-rule",
            ),
        )

    def test_calculation_tamper_detected(
        self,
    ):
        service = EngineeringCodeService()

        combination = LoadCombination(
            combination_id="combo",
            name="combo",
            factors=(
                LoadFactor(
                    load_case="D",
                    factor=(
                        Decimal(
                            "1"
                        )
                    ),
                ),
            ),
            source_fact_id="rule",
        )

        _, trace = (
            service
            .evaluate_load_combination(
                combination=combination,
                load_cases=(
                    LoadCase(
                        name="D",
                        value=(
                            Decimal(
                                "10"
                            )
                        ),
                        unit="kip",
                    ),
                ),
                source_fact_ids=(
                    "rule",
                ),
                calculation_id="calc",
            )
        )

        tampered = replace(
            trace,
            outputs={
                "result":
                    "tampered"
            },
        )

        with self.assertRaises(
            CalculationIntegrityError
        ):
            service.calculations.verify_trace(
                tampered
            )


class ComplianceTests(
    unittest.TestCase
):
    def test_rule_engine(
        self,
    ):
        service = EngineeringCodeService()

        context = ProjectEngineeringContext(
            project_id="project",
            jurisdiction_id="fort-worth",
            project_date=(
                date(
                    2026,
                    8,
                    17,
                )
            ),
            structure_context=(
                StructureContext.BELOW_GRADE
            ),
            project_tags=frozenset(
                {
                    "concrete"
                }
            ),
        )

        requirement = RuleRequirement(
            requirement_id="r1",
            discipline=(
                EngineeringDiscipline.CONCRETE
            ),
            name="Minimum screening value",
            field_name="strength",
            operator="gte",
            expected=4000,
            severity=(
                RequirementSeverity.MATERIAL
            ),
            source_fact_id=(
                "official-rule"
            ),
            applicable_structure_contexts=(
                StructureContext.BELOW_GRADE,
            ),
            required_tags=frozenset(
                {
                    "concrete"
                }
            ),
            professional_review_required=True,
        )

        findings = (
            service.compliance.evaluate(
                context=context,
                requirements=(
                    requirement,
                ),
                actuals={
                    "strength":
                        4500
                },
            )
        )

        self.assertEqual(
            findings[0].status,
            ComplianceStatus.PASS,
        )

        self.assertFalse(
            service.compliance
            .release_allowed(
                findings
            )
        )

    def test_missing_input_fails_closed_to_review(
        self,
    ):
        service = EngineeringCodeService()

        context = ProjectEngineeringContext(
            project_id="project",
            jurisdiction_id="fort-worth",
            project_date=date(
                2026,
                8,
                17,
            ),
            structure_context=(
                StructureContext.ABOVE_GRADE
            ),
        )

        requirement = RuleRequirement(
            requirement_id="missing",
            discipline=(
                EngineeringDiscipline.STRUCTURAL
            ),
            name="Input required",
            field_name="design_input",
            operator="gte",
            expected=1,
            severity=(
                RequirementSeverity.CRITICAL
            ),
            source_fact_id="fact",
        )

        finding = (
            service.compliance.evaluate(
                context=context,
                requirements=(
                    requirement,
                ),
                actuals={},
            )[0]
        )

        self.assertEqual(
            finding.status,
            ComplianceStatus.REVIEW,
        )


class PersistenceTests(
    unittest.TestCase
):
    def test_jurisdiction_and_adoption_persist(
        self,
    ):
        store = FakeStore()

        repository = (
            EngineeringCodeRepository(
                store,
                tenant_id="tenant",
            )
        )

        service = (
            EngineeringCodeService(
                repository=repository
            )
        )

        service.add_jurisdiction(
            Jurisdiction(
                jurisdiction_id="tx",
                name="Texas",
                jurisdiction_type=(
                    JurisdictionType.STATE
                ),
            )
        )

        service.add_adoption(
            CodeAdoption(
                adoption_id="adoption",
                jurisdiction_id="tx",
                discipline=(
                    EngineeringDiscipline
                    .STRUCTURAL
                ),
                code_family="TEST",
                edition="X",
                effective_from=(
                    date(
                        2026,
                        1,
                        1,
                    )
                ),
                effective_until=None,
                authority=(
                    CodeAuthority.OFFICIAL
                ),
                status=(
                    AdoptionStatus.ACTIVE
                ),
                source_fact_id="fact",
            )
        )

        entity_types = {
            key[1]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.engineering.jurisdiction",
            entity_types,
        )

        self.assertIn(
            "goat.engineering.code_adoption",
            entity_types,
        )


class StressTests(
    unittest.TestCase
):
    def test_20000_water_assessments(
        self,
    ):
        service = EngineeringCodeService()

        inputs = WaterIntrusionInputs(
            lowest_structural_elevation_ft=90.0,
            groundwater_elevation_ft=95.0,
            design_flood_elevation_ft=97.0,
            below_grade_wall_height_ft=10.0,
            slab_area_sf=5000.0,
            soil_permeability_index=0.5,
            waterproofing_reliability=0.9,
            drainage_reliability=0.9,
            sump_reliability=0.9,
            redundancy_count=2,
        )

        for _ in range(
            20000
        ):
            result = service.water.assess(
                inputs
            )

            self.assertGreaterEqual(
                result.base_pressure_psi,
                0.0,
            )


if __name__ == "__main__":
    unittest.main()
