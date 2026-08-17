from __future__ import annotations

from dataclasses import replace

from .canonical import (
    stable_hash,
    to_primitive,
)

from .models import (
    AnalysisTrace,
    CalculationIntegrityError,
    utcnow,
)


ANALYSIS_TRACE_ENTITY = (
    "goat.multiphysics.analysis_trace"
)

DIAGNOSTIC_ENTITY = (
    "goat.multiphysics.diagnostic"
)

UNCERTAINTY_ENTITY = (
    "goat.multiphysics.uncertainty"
)


class AnalysisTraceChain:
    def __init__(self) -> None:
        self._traces = []

    @property
    def tip_hash(self):
        if not self._traces:
            return None

        return self._traces[
            -1
        ].chain_hash

    @staticmethod
    def payload(trace):
        return {
            "analysis_id":
                trace.analysis_id,

            "engine":
                trace.engine,

            "engine_version":
                trace.engine_version,

            "domain":
                trace.domain,

            "inputs":
                trace.inputs,

            "outputs":
                trace.outputs,

            "source_fact_ids":
                trace.source_fact_ids,

            "executed_at":
                trace.executed_at,
        }

    def append(
        self,
        *,
        analysis_id,
        engine,
        engine_version,
        domain,
        inputs,
        outputs,
        source_fact_ids,
        executed_at=None,
    ):
        executed_at = (
            executed_at
            or utcnow()
        )

        primitive_inputs = (
            to_primitive(
                inputs
            )
        )

        primitive_outputs = (
            to_primitive(
                outputs
            )
        )

        provisional = AnalysisTrace(
            analysis_id=analysis_id,
            engine=engine,
            engine_version=(
                engine_version
            ),
            domain=domain,
            inputs=(
                primitive_inputs
            ),
            outputs=(
                primitive_outputs
            ),
            source_fact_ids=tuple(
                source_fact_ids
            ),
            executed_at=(
                executed_at
            ),
            content_hash="",
            previous_hash=(
                self.tip_hash
            ),
            chain_hash="",
        )

        content_hash = stable_hash(
            self.payload(
                provisional
            )
        )

        chain_hash = stable_hash(
            {
                "content_hash":
                    content_hash,

                "previous_hash":
                    provisional
                    .previous_hash,
            }
        )

        trace = replace(
            provisional,
            content_hash=(
                content_hash
            ),
            chain_hash=(
                chain_hash
            ),
        )

        self.verify_trace(
            trace
        )

        self._traces.append(
            trace
        )

        return trace

    def verify_trace(
        self,
        trace,
    ):
        expected_content = stable_hash(
            self.payload(
                trace
            )
        )

        if (
            expected_content
            != trace.content_hash
        ):
            raise CalculationIntegrityError(
                "analysis trace content hash mismatch"
            )

        expected_chain = stable_hash(
            {
                "content_hash":
                    trace.content_hash,

                "previous_hash":
                    trace.previous_hash,
            }
        )

        if (
            expected_chain
            != trace.chain_hash
        ):
            raise CalculationIntegrityError(
                "analysis trace chain hash mismatch"
            )

        return True

    def verify(self):
        previous = None

        for trace in self._traces:
            if (
                trace.previous_hash
                != previous
            ):
                raise CalculationIntegrityError(
                    "analysis trace chain linkage mismatch"
                )

            self.verify_trace(
                trace
            )

            previous = (
                trace.chain_hash
            )

        return True

    def traces(self):
        return tuple(
            self._traces
        )


class MultiphysicsRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id,
        actor_id=(
            "goat-multiphysics-engineering"
        ),
    ) -> None:
        self.store = store
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def _upsert(
        self,
        *,
        entity_type,
        entity_id,
        payload,
    ):
        current = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        expected = (
            None
            if current is None
            else int(
                current.version
            )
        )

        return self.store.put_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=(
                to_primitive(
                    payload
                )
            ),
            actor_id=self.actor_id,
            expected_version=expected,
        )

    def save_trace(
        self,
        trace,
    ):
        return self._upsert(
            entity_type=(
                ANALYSIS_TRACE_ENTITY
            ),
            entity_id=(
                trace.analysis_id
            ),
            payload={
                "engine":
                    trace.engine,

                "engine_version":
                    trace.engine_version,

                "domain":
                    trace.domain.value,

                "inputs":
                    trace.inputs,

                "outputs":
                    trace.outputs,

                "source_fact_ids":
                    list(
                        trace.source_fact_ids
                    ),

                "executed_at":
                    trace.executed_at
                    .isoformat(),

                "content_hash":
                    trace.content_hash,

                "previous_hash":
                    trace.previous_hash,

                "chain_hash":
                    trace.chain_hash,
            },
        )

    def save_diagnostic(
        self,
        diagnostic,
    ):
        return self._upsert(
            entity_type=(
                DIAGNOSTIC_ENTITY
            ),
            entity_id=(
                diagnostic
                .diagnostic_id
            ),
            payload={
                "domain":
                    diagnostic
                    .domain
                    .value,

                "disposition":
                    diagnostic
                    .disposition
                    .value,

                "severity":
                    diagnostic.severity,

                "message":
                    diagnostic.message,

                "evidence":
                    diagnostic.evidence,

                "professional_review_required":
                    diagnostic
                    .professional_review_required,
            },
        )

    def save_uncertainty(
        self,
        *,
        analysis_id,
        result,
    ):
        return self._upsert(
            entity_type=(
                UNCERTAINTY_ENTITY
            ),
            entity_id=analysis_id,
            payload={
                "samples":
                    result.samples,

                "seed":
                    result.seed,

                "mean":
                    result.mean,

                "standard_deviation":
                    result
                    .standard_deviation,

                "p05":
                    result.p05,

                "p50":
                    result.p50,

                "p95":
                    result.p95,

                "minimum":
                    result.minimum,

                "maximum":
                    result.maximum,
            },
        )
