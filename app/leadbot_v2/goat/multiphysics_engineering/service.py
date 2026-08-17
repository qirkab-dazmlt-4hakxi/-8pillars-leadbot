from __future__ import annotations

from .diagnostics import (
    EngineeringDiagnostics,
)

from .geotechnical import (
    EarthPressureEngine,
    EffectiveStressEngine,
    FoundationEngine,
)

from .graph import (
    MultiphysicsGraph,
)

from .materials import (
    ConcreteSectionEngine,
    SteelYieldEngine,
)

from .mep import (
    ElectricalDemandEngine,
    HVACLoadEngine,
)

from .persistence import (
    AnalysisTraceChain,
)

from .structural import (
    Truss2DSolver,
)

from .uncertainty import (
    UncertaintyEngine,
)


class MultiphysicsEngineeringService:
    def __init__(
        self,
        *,
        repository=None,
    ) -> None:
        self.repository = repository

        self.structural = (
            Truss2DSolver()
        )

        self.effective_stress = (
            EffectiveStressEngine()
        )

        self.foundations = (
            FoundationEngine()
        )

        self.earth_pressure = (
            EarthPressureEngine()
        )

        self.concrete = (
            ConcreteSectionEngine()
        )

        self.steel = (
            SteelYieldEngine()
        )

        self.hvac = (
            HVACLoadEngine()
        )

        self.electrical = (
            ElectricalDemandEngine()
        )

        self.graph = (
            MultiphysicsGraph()
        )

        self.uncertainty = (
            UncertaintyEngine()
        )

        self.diagnostics = (
            EngineeringDiagnostics()
        )

        self.traces = (
            AnalysisTraceChain()
        )

    def record_analysis(
        self,
        **kwargs,
    ):
        trace = (
            self.traces.append(
                **kwargs
            )
        )

        if self.repository:
            self.repository.save_trace(
                trace
            )

        return trace

    def record_diagnostic(
        self,
        diagnostic,
    ):
        if self.repository:
            self.repository.save_diagnostic(
                diagnostic
            )

        return diagnostic

    def run_uncertainty(
        self,
        *,
        analysis_id,
        **kwargs,
    ):
        result = (
            self.uncertainty
            .simulate(
                **kwargs
            )
        )

        if self.repository:
            self.repository.save_uncertainty(
                analysis_id=(
                    analysis_id
                ),
                result=result,
            )

        return result
