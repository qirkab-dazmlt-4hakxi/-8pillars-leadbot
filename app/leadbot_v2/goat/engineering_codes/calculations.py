from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .canonical import (
    stable_hash,
)

from .models import (
    CalculationIntegrityError,
    CalculationTrace,
    LoadCombinationResult,
    utcnow,
)


def decimal(value) -> Decimal:
    if isinstance(
        value,
        Decimal,
    ):
        return value

    return Decimal(
        str(value)
    )


class LoadCombinationEngine:
    """
    Executes supplied load-combination coefficients.

    Coefficients are deliberately NOT embedded as universal constants.
    They must come from the effective governing code/reference-standard data
    selected by the jurisdiction/code resolver.
    """

    def evaluate(
        self,
        *,
        combination,
        load_cases,
    ):
        case_map = {
            case.name:
                case
            for case
            in load_cases
        }

        contributions = []

        unit = None
        total = Decimal("0")

        for factor in combination.factors:
            if (
                factor.load_case
                not in case_map
            ):
                raise ValueError(
                    f"missing load case: "
                    f"{factor.load_case}"
                )

            case = case_map[
                factor.load_case
            ]

            if unit is None:
                unit = case.unit

            elif case.unit != unit:
                raise ValueError(
                    "load combination requires "
                    "consistent units"
                )

            contribution = (
                decimal(
                    case.value
                )
                * decimal(
                    factor.factor
                )
            )

            total += contribution

            contributions.append(
                (
                    factor.load_case,
                    contribution,
                )
            )

        return LoadCombinationResult(
            combination_id=(
                combination.combination_id
            ),
            result=total,
            unit=unit or "",
            contributions=tuple(
                contributions
            ),
        )


class CalculationTraceChain:
    def __init__(
        self,
    ) -> None:
        self._traces = []

    @property
    def tip_hash(self):
        if not self._traces:
            return None

        return self._traces[
            -1
        ].chain_hash

    @staticmethod
    def content_payload(
        trace,
    ):
        return {
            "calculation_id":
                trace.calculation_id,

            "engine":
                trace.engine,

            "engine_version":
                trace.engine_version,

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
        calculation_id,
        engine,
        engine_version,
        inputs,
        outputs,
        source_fact_ids,
        executed_at=None,
    ):
        executed_at = (
            executed_at
            or utcnow()
        )

        provisional = CalculationTrace(
            calculation_id=(
                calculation_id
            ),
            engine=engine,
            engine_version=(
                engine_version
            ),
            inputs=dict(
                inputs
            ),
            outputs=dict(
                outputs
            ),
            source_fact_ids=tuple(
                source_fact_ids
            ),
            executed_at=(
                executed_at
            ),
            previous_hash=(
                self.tip_hash
            ),
            content_hash="",
            chain_hash="",
        )

        content_hash = stable_hash(
            self.content_payload(
                provisional
            )
        )

        chain_hash = stable_hash(
            {
                "content_hash":
                    content_hash,

                "previous_hash":
                    self.tip_hash,
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
            self.content_payload(
                trace
            )
        )

        if (
            expected_content
            != trace.content_hash
        ):
            raise CalculationIntegrityError(
                "calculation content hash mismatch"
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
                "calculation chain hash mismatch"
            )

        return True

    def verify(
        self,
    ):
        previous = None

        for trace in self._traces:
            if (
                trace.previous_hash
                != previous
            ):
                raise CalculationIntegrityError(
                    "calculation trace chain linkage mismatch"
                )

            self.verify_trace(
                trace
            )

            previous = (
                trace.chain_hash
            )

        return True

    def traces(
        self,
    ):
        return tuple(
            self._traces
        )
