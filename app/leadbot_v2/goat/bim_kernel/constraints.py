from __future__ import annotations

from .models import (
    ConstraintDisposition,
    ConstraintFinding,
)


class ModelConstraintEngine:
    @staticmethod
    def _compare(
        actual,
        operator,
        expected,
    ):
        if operator == "gte":
            return actual >= expected

        if operator == "gt":
            return actual > expected

        if operator == "lte":
            return actual <= expected

        if operator == "lt":
            return actual < expected

        if operator == "eq":
            return actual == expected

        if operator == "ne":
            return actual != expected

        raise ValueError(
            f"unsupported constraint operator: "
            f"{operator}"
        )

    def evaluate(
        self,
        *,
        element,
        constraints,
        values,
    ):
        findings = []

        for constraint in constraints:
            if (
                constraint.applicable_categories
                and element.category
                not in constraint.applicable_categories
            ):
                continue

            actual = values.get(
                constraint.field_name
            )

            if actual is None:
                findings.append(
                    ConstraintFinding(
                        constraint_id=(
                            constraint.constraint_id
                        ),
                        element_id=(
                            element.element_id
                        ),
                        disposition=(
                            ConstraintDisposition.REVIEW
                        ),
                        actual=None,
                        expected=float(
                            constraint.expected
                        ),
                        message=(
                            "required model value missing"
                        ),
                        source_fact_id=(
                            constraint.source_fact_id
                        ),
                        professional_review_required=True,
                    )
                )

                continue

            passed = self._compare(
                float(actual),
                constraint.operator,
                float(
                    constraint.expected
                ),
            )

            findings.append(
                ConstraintFinding(
                    constraint_id=(
                        constraint.constraint_id
                    ),
                    element_id=(
                        element.element_id
                    ),
                    disposition=(
                        ConstraintDisposition.PASS
                        if passed
                        else ConstraintDisposition.FAIL
                    ),
                    actual=float(actual),
                    expected=float(
                        constraint.expected
                    ),
                    message=(
                        "constraint satisfied"
                        if passed
                        else "constraint violated"
                    ),
                    source_fact_id=(
                        constraint.source_fact_id
                    ),
                    professional_review_required=(
                        constraint
                        .professional_review_required
                    ),
                )
            )

        return tuple(findings)

    def release_allowed(
        self,
        findings,
    ):
        return all(
            finding.disposition
            is ConstraintDisposition.PASS
            and not finding
            .professional_review_required
            for finding
            in findings
        )
