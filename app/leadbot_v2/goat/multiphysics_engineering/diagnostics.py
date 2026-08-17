from __future__ import annotations

from .canonical import (
    stable_hash,
)

from .models import (
    AnalysisDisposition,
    EngineeringDiagnostic,
    PhysicsDomain,
)


class EngineeringDiagnostics:
    def utilization(
        self,
        *,
        domain,
        name,
        demand,
        capacity,
        review_threshold=0.90,
        professional_review_required=True,
    ):
        if capacity <= 0:
            ratio = float("inf")
        else:
            ratio = (
                demand / capacity
            )

        if ratio > 1.0:
            disposition = (
                AnalysisDisposition.FAIL
            )

            severity = 1.0

            message = (
                f"{name} demand exceeds "
                f"screening capacity"
            )

        elif ratio >= review_threshold:
            disposition = (
                AnalysisDisposition.REVIEW
            )

            severity = min(
                1.0,
                max(
                    0.0,
                    ratio,
                ),
            )

            message = (
                f"{name} utilization is inside "
                f"engineering review band"
            )

        else:
            disposition = (
                AnalysisDisposition.PASS
            )

            severity = max(
                0.0,
                ratio,
            )

            message = (
                f"{name} screening utilization "
                f"is below review threshold"
            )

        diagnostic_id = stable_hash(
            {
                "domain":
                    domain,
                "name":
                    name,
                "demand":
                    demand,
                "capacity":
                    capacity,
                "ratio":
                    ratio,
            }
        )[:24]

        return EngineeringDiagnostic(
            diagnostic_id=(
                diagnostic_id
            ),
            domain=domain,
            disposition=(
                disposition
            ),
            severity=severity,
            message=message,
            evidence={
                "demand":
                    demand,
                "capacity":
                    capacity,
                "utilization":
                    ratio,
                "review_threshold":
                    review_threshold,
            },
            professional_review_required=(
                professional_review_required
            ),
        )

    def linear_solver(
        self,
        solver_result,
        *,
        domain=(
            PhysicsDomain.STRUCTURAL
        ),
        pivot_ratio_review=1.0e10,
    ):
        if not solver_result.converged:
            disposition = (
                AnalysisDisposition
                .NONCONVERGED
            )

            message = (
                "numerical solver did not satisfy "
                "residual tolerance"
            )

            severity = 1.0

        elif (
            solver_result.pivot_ratio
            >= pivot_ratio_review
        ):
            disposition = (
                AnalysisDisposition.REVIEW
            )

            message = (
                "linear system is numerically "
                "ill-conditioned by pivot-ratio screen"
            )

            severity = 0.8

        else:
            disposition = (
                AnalysisDisposition.PASS
            )

            message = (
                "linear solver residual and "
                "pivot screens acceptable"
            )

            severity = min(
                0.5,
                solver_result
                .relative_residual,
            )

        diagnostic_id = stable_hash(
            {
                "domain":
                    domain,
                "relative_residual":
                    solver_result
                    .relative_residual,
                "pivot_ratio":
                    solver_result
                    .pivot_ratio,
                "converged":
                    solver_result
                    .converged,
            }
        )[:24]

        return EngineeringDiagnostic(
            diagnostic_id=(
                diagnostic_id
            ),
            domain=domain,
            disposition=(
                disposition
            ),
            severity=severity,
            message=message,
            evidence={
                "relative_residual":
                    solver_result
                    .relative_residual,
                "pivot_ratio":
                    solver_result
                    .pivot_ratio,
            },
            professional_review_required=True,
        )

    def release_allowed(
        self,
        diagnostics,
    ):
        for diagnostic in diagnostics:
            if (
                diagnostic.disposition
                is not AnalysisDisposition.PASS
            ):
                return False

            if (
                diagnostic
                .professional_review_required
            ):
                return False

        return True
