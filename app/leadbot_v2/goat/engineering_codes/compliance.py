from __future__ import annotations

from decimal import Decimal

from .applicability import (
    RequirementApplicability,
)

from .models import (
    ComplianceFinding,
    ComplianceStatus,
)


class ComplianceEngine:
    def __init__(
        self,
    ) -> None:
        self.applicability = (
            RequirementApplicability()
        )

    @staticmethod
    def _compare(
        *,
        actual,
        operator,
        expected,
    ):
        if operator == "eq":
            return actual == expected

        if operator == "ne":
            return actual != expected

        if operator == "gte":
            return (
                Decimal(str(actual))
                >= Decimal(str(expected))
            )

        if operator == "gt":
            return (
                Decimal(str(actual))
                > Decimal(str(expected))
            )

        if operator == "lte":
            return (
                Decimal(str(actual))
                <= Decimal(str(expected))
            )

        if operator == "lt":
            return (
                Decimal(str(actual))
                < Decimal(str(expected))
            )

        if operator == "in":
            return actual in expected

        if operator == "contains":
            return expected in actual

        if operator == "truthy":
            return bool(actual)

        raise ValueError(
            f"unsupported compliance operator: "
            f"{operator}"
        )

    def evaluate(
        self,
        *,
        context,
        requirements,
        actuals,
    ):
        findings = []

        for requirement in requirements:
            if not self.applicability.applies(
                requirement,
                context,
            ):
                findings.append(
                    ComplianceFinding(
                        requirement_id=(
                            requirement
                            .requirement_id
                        ),
                        discipline=(
                            requirement
                            .discipline
                        ),
                        status=(
                            ComplianceStatus
                            .NOT_APPLICABLE
                        ),
                        severity=(
                            requirement
                            .severity
                        ),
                        message=(
                            "requirement not applicable "
                            "to project context"
                        ),
                        actual=None,
                        expected=(
                            requirement.expected
                        ),
                        source_fact_id=(
                            requirement
                            .source_fact_id
                        ),
                        professional_review_required=(
                            False
                        ),
                    )
                )

                continue

            actual = actuals.get(
                requirement.field_name
            )

            if actual is None:
                status = (
                    ComplianceStatus.REVIEW
                )

                message = (
                    "required engineering input "
                    "is missing"
                )

            else:
                passed = self._compare(
                    actual=actual,
                    operator=(
                        requirement.operator
                    ),
                    expected=(
                        requirement.expected
                    ),
                )

                status = (
                    ComplianceStatus.PASS
                    if passed
                    else ComplianceStatus.FAIL
                )

                message = (
                    "requirement satisfied"
                    if passed
                    else "requirement not satisfied"
                )

            if (
                requirement
                .professional_review_required
                and status
                is ComplianceStatus.PASS
            ):
                message += (
                    "; professional review remains required"
                )

            findings.append(
                ComplianceFinding(
                    requirement_id=(
                        requirement.requirement_id
                    ),
                    discipline=(
                        requirement.discipline
                    ),
                    status=status,
                    severity=(
                        requirement.severity
                    ),
                    message=message,
                    actual=actual,
                    expected=(
                        requirement.expected
                    ),
                    source_fact_id=(
                        requirement.source_fact_id
                    ),
                    professional_review_required=(
                        requirement
                        .professional_review_required
                    ),
                )
            )

        return tuple(
            findings
        )

    def release_allowed(
        self,
        findings,
    ) -> bool:
        for finding in findings:
            if finding.status in {
                ComplianceStatus.FAIL,
                ComplianceStatus.REVIEW,
            }:
                return False

            if (
                finding
                .professional_review_required
            ):
                return False

        return True
