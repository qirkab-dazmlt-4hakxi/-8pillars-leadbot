from __future__ import annotations

from .applicability import (
    DisciplineApplicabilityEngine,
)

from .calculations import (
    CalculationTraceChain,
    LoadCombinationEngine,
)

from .compliance import (
    ComplianceEngine,
)

from .jurisdiction import (
    JurisdictionGraph,
)

from .registry import (
    EngineeringCodeRegistry,
)

from .water import (
    WaterIntrusionEngine,
)


class EngineeringCodeService:
    def __init__(
        self,
        *,
        repository=None,
    ) -> None:
        self.repository = repository

        self.jurisdictions = (
            JurisdictionGraph()
        )

        self.codes = (
            EngineeringCodeRegistry(
                jurisdiction_graph=(
                    self.jurisdictions
                )
            )
        )

        self.applicability = (
            DisciplineApplicabilityEngine()
        )

        self.loads = (
            LoadCombinationEngine()
        )

        self.calculations = (
            CalculationTraceChain()
        )

        self.water = (
            WaterIntrusionEngine()
        )

        self.compliance = (
            ComplianceEngine()
        )

    def add_jurisdiction(
        self,
        jurisdiction,
    ):
        self.jurisdictions.add(
            jurisdiction
        )

        if self.repository:
            self.repository.save_jurisdiction(
                jurisdiction
            )

    def add_adoption(
        self,
        adoption,
    ):
        self.codes.add_adoption(
            adoption
        )

        if self.repository:
            self.repository.save_adoption(
                adoption
            )

    def add_amendment(
        self,
        amendment,
    ):
        self.codes.add_amendment(
            amendment
        )

        if self.repository:
            self.repository.save_amendment(
                amendment
            )

    def resolve_code_stack(
        self,
        **kwargs,
    ):
        return self.codes.resolve(
            **kwargs
        )

    def evaluate_load_combination(
        self,
        *,
        combination,
        load_cases,
        source_fact_ids,
        calculation_id,
    ):
        result = self.loads.evaluate(
            combination=combination,
            load_cases=load_cases,
        )

        trace = self.calculations.append(
            calculation_id=(
                calculation_id
            ),
            engine=(
                "goat.load_combination"
            ),
            engine_version="1",
            inputs={
                "combination":
                    combination,

                "load_cases":
                    tuple(
                        load_cases
                    ),
            },
            outputs={
                "result":
                    result,
            },
            source_fact_ids=(
                source_fact_ids
            ),
        )

        if self.repository:
            self.repository.save_calculation(
                trace
            )

        return result, trace

    def assess_water_intrusion(
        self,
        *,
        assessment_id,
        inputs,
    ):
        result = self.water.assess(
            inputs
        )

        if self.repository:
            self.repository.save_water_assessment(
                assessment_id=(
                    assessment_id
                ),
                assessment=result,
            )

        return result
