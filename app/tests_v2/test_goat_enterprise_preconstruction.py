import unittest

from datetime import date

from leadbot_v2.goat.preconstruction.enterprise import (
    ActivityDependency,
    AutomaticRFIEngine,
    BidReadinessEngine,
    BidReadinessInput,
    ComplianceState,
    ContractRiskCategory,
    ContractRiskEngine,
    CriticalPathEngine,
    DependencyType,
    EvidenceKind,
    EvidenceRecord,
    MissingEvidenceError,
    ProcurementLeadTimeEngine,
    ProcurementPackage,
    ProcurementRisk,
    RequirementCategory,
    RFISeverity,
    RiskSeverity,
    ScheduleActivity,
    ScheduleCycleError,
    ScopeComplianceEngine,
    ScopeRequirement,
    SourceReference,
    SpecificationIntelligence,
)


class SpecificationTests(
    unittest.TestCase
):

    def test_extracts_mandatory_submittal(self):
        result = (
            SpecificationIntelligence
            .analyze(
                source_id="spec",
                text=(
                    "SECTION 03 30 00. "
                    "Contractor shall submit "
                    "concrete mix design product data."
                ),
            )
        )

        self.assertGreater(
            result.mandatory_count,
            0,
        )

        self.assertGreater(
            result.submittal_count,
            0,
        )

    def test_extracts_testing(self):
        result = (
            SpecificationIntelligence
            .analyze(
                source_id="spec",
                text=(
                    "Field testing shall be "
                    "performed by an approved "
                    "testing laboratory."
                ),
            )
        )

        self.assertEqual(
            result.testing_count,
            1,
        )

    def test_extracts_warranty(self):
        result = (
            SpecificationIntelligence
            .analyze(
                source_id="spec",
                text=(
                    "Provide a two year "
                    "workmanship warranty."
                ),
            )
        )

        self.assertEqual(
            result.warranty_count,
            1,
        )

    def test_extracts_mockup(self):
        result = (
            SpecificationIntelligence
            .analyze(
                source_id="spec",
                text=(
                    "Contractor shall provide "
                    "a sample panel mock-up."
                ),
            )
        )

        self.assertEqual(
            result.mockup_count,
            1,
        )

    def test_numeric_values_preserved(self):
        result = (
            SpecificationIntelligence
            .analyze(
                source_id="spec",
                text=(
                    "Concrete shall achieve "
                    "5000 psi compressive strength."
                ),
            )
        )

        values = (
            result.requirements[0]
            .numeric_values
        )

        self.assertTrue(
            any(
                "5000" in value
                for value
                in values
            )
        )

    def test_empty_spec_fails(self):
        with self.assertRaises(
            MissingEvidenceError
        ):
            SpecificationIntelligence.analyze(
                source_id="spec",
                text="",
            )


class ContractRiskTests(
    unittest.TestCase
):

    def test_liquidated_damages(self):
        result = (
            ContractRiskEngine
            .analyze(
                source_id="contract",
                text=(
                    "Liquidated damages shall "
                    "be $2,500 per day."
                ),
            )
        )

        finding = result.findings[0]

        self.assertEqual(
            finding.category,
            ContractRiskCategory
            .LIQUIDATED_DAMAGES,
        )

        self.assertEqual(
            finding.severity,
            RiskSeverity.HIGH,
        )

    def test_pay_if_paid(self):
        result = (
            ContractRiskEngine
            .analyze(
                source_id="contract",
                text=(
                    "Receipt of payment from Owner "
                    "is a condition precedent to payment."
                ),
            )
        )

        self.assertTrue(
            any(
                item.category
                == ContractRiskCategory
                .PAYMENT
                for item
                in result.findings
            )
        )

    def test_notice_clause(self):
        result = (
            ContractRiskEngine
            .analyze(
                source_id="contract",
                text=(
                    "Contractor must provide "
                    "written notice within 7 days."
                ),
            )
        )

        self.assertTrue(
            any(
                item.category
                == ContractRiskCategory
                .NOTICE
                for item
                in result.findings
            )
        )

    def test_indemnity(self):
        result = (
            ContractRiskEngine
            .analyze(
                source_id="contract",
                text=(
                    "Subcontractor shall indemnify, "
                    "defend and hold harmless Contractor."
                ),
            )
        )

        self.assertTrue(
            any(
                item.category
                == ContractRiskCategory
                .INDEMNITY
                for item
                in result.findings
            )
        )

    def test_flow_down(self):
        result = (
            ContractRiskEngine
            .analyze(
                source_id="contract",
                text=(
                    "Subcontractor shall be bound "
                    "by the prime contract terms "
                    "incorporated by reference."
                ),
            )
        )

        self.assertTrue(
            any(
                item.category
                == ContractRiskCategory
                .FLOW_DOWN
                for item
                in result.findings
            )
        )

    def test_weighted_score(self):
        result = (
            ContractRiskEngine
            .analyze(
                source_id="contract",
                text=(
                    "Liquidated damages are "
                    "$1000 per day. "
                    "Subcontractor shall indemnify "
                    "Contractor. "
                    "Retainage is 10 percent."
                ),
            )
        )

        self.assertGreater(
            result.weighted_risk_score,
            0,
        )


class ScheduleTests(
    unittest.TestCase
):

    def test_basic_critical_path(self):
        activities = (
            ScheduleActivity(
                "A",
                "Excavation",
                5,
            ),
            ScheduleActivity(
                "B",
                "Foundations",
                4,
                predecessors=(
                    ActivityDependency(
                        "A"
                    ),
                ),
            ),
            ScheduleActivity(
                "C",
                "Walls",
                6,
                predecessors=(
                    ActivityDependency(
                        "B"
                    ),
                ),
            ),
        )

        result = (
            CriticalPathEngine
            .analyze(
                activities
            )
        )

        self.assertEqual(
            result.project_duration_days,
            15,
        )

        self.assertEqual(
            result.critical_path,
            (
                "A",
                "B",
                "C",
            ),
        )

    def test_parallel_float(self):
        activities = (
            ScheduleActivity(
                "A",
                "Start",
                1,
            ),
            ScheduleActivity(
                "B",
                "Long",
                10,
                predecessors=(
                    ActivityDependency(
                        "A"
                    ),
                ),
            ),
            ScheduleActivity(
                "C",
                "Short",
                2,
                predecessors=(
                    ActivityDependency(
                        "A"
                    ),
                ),
            ),
            ScheduleActivity(
                "D",
                "Finish",
                1,
                predecessors=(
                    ActivityDependency(
                        "B"
                    ),
                    ActivityDependency(
                        "C"
                    ),
                ),
            ),
        )

        result = (
            CriticalPathEngine
            .analyze(
                activities
            )
        )

        c = next(
            item
            for item
            in result.activities
            if item.activity_id
            == "C"
        )

        self.assertGreater(
            c.total_float,
            0,
        )

    def test_ss_dependency(self):
        activities = (
            ScheduleActivity(
                "A",
                "Start",
                10,
            ),
            ScheduleActivity(
                "B",
                "Concurrent",
                5,
                predecessors=(
                    ActivityDependency(
                        "A",
                        relation=(
                            DependencyType.SS
                        ),
                        lag_days=2,
                    ),
                ),
            ),
        )

        result = (
            CriticalPathEngine
            .analyze(
                activities
            )
        )

        b = next(
            item
            for item
            in result.activities
            if item.activity_id
            == "B"
        )

        self.assertEqual(
            b.early_start,
            2,
        )

    def test_cycle_detected(self):
        activities = (
            ScheduleActivity(
                "A",
                "A",
                1,
                predecessors=(
                    ActivityDependency(
                        "B"
                    ),
                ),
            ),
            ScheduleActivity(
                "B",
                "B",
                1,
                predecessors=(
                    ActivityDependency(
                        "A"
                    ),
                ),
            ),
        )

        with self.assertRaises(
            ScheduleCycleError
        ):
            CriticalPathEngine.analyze(
                activities
            )


class ProcurementTests(
    unittest.TestCase
):

    def test_release_date(self):
        package = ProcurementPackage(
            package_id="gear",
            description="Switchgear",
            submittal_days=7,
            review_days=14,
            fabrication_days=60,
            transit_days=7,
            field_buffer_days=7,
            required_on_site=(
                date(
                    2026,
                    12,
                    31,
                )
            ),
        )

        result = (
            ProcurementLeadTimeEngine
            .analyze(
                package,
                as_of=(
                    date(
                        2026,
                        8,
                        15,
                    )
                ),
            )
        )

        self.assertEqual(
            result.total_lead_days,
            95,
        )

        self.assertEqual(
            result.risk,
            ProcurementRisk
            .LONG_LEAD,
        )

    def test_late_package_is_critical(self):
        package = ProcurementPackage(
            package_id="x",
            description="Equipment",
            submittal_days=10,
            review_days=10,
            fabrication_days=60,
            transit_days=10,
            field_buffer_days=10,
            required_on_site=(
                date(
                    2026,
                    9,
                    1,
                )
            ),
        )

        result = (
            ProcurementLeadTimeEngine
            .analyze(
                package,
                as_of=(
                    date(
                        2026,
                        8,
                        15,
                    )
                ),
            )
        )

        self.assertTrue(
            result.already_late
        )

        self.assertEqual(
            result.risk,
            ProcurementRisk
            .CRITICAL,
        )


class ComplianceTests(
    unittest.TestCase
):

    def test_satisfied(self):
        requirements = (
            ScopeRequirement(
                scope_id="slab",
                description="Slab",
                trade="concrete",
                required_evidence=(
                    frozenset(
                        {
                            EvidenceKind
                            .DRAWING,
                            EvidenceKind
                            .SPECIFICATION,
                        }
                    )
                ),
            ),
        )

        evidence = (
            EvidenceRecord(
                evidence_id="drawing",
                kind=(
                    EvidenceKind
                    .DRAWING
                ),
                description="S2.1",
                trade="concrete",
                scope_id="slab",
                source=(
                    SourceReference(
                        "S2.1",
                        EvidenceKind
                        .DRAWING,
                    )
                ),
                value_fingerprint="6in",
            ),
            EvidenceRecord(
                evidence_id="spec",
                kind=(
                    EvidenceKind
                    .SPECIFICATION
                ),
                description="03 30 00",
                trade="concrete",
                scope_id="slab",
                source=(
                    SourceReference(
                        "033000",
                        EvidenceKind
                        .SPECIFICATION,
                    )
                ),
                value_fingerprint="6in",
            ),
        )

        result = (
            ScopeComplianceEngine
            .evaluate(
                requirements=requirements,
                evidence=evidence,
            )
        )

        self.assertEqual(
            result[0].state,
            ComplianceState
            .SATISFIED,
        )

    def test_missing_evidence_unresolved(self):
        requirements = (
            ScopeRequirement(
                scope_id="slab",
                description="Slab",
                trade="concrete",
                required_evidence=(
                    frozenset(
                        {
                            EvidenceKind
                            .DRAWING,
                            EvidenceKind
                            .SPECIFICATION,
                        }
                    )
                ),
            ),
        )

        evidence = (
            EvidenceRecord(
                evidence_id="drawing",
                kind=(
                    EvidenceKind
                    .DRAWING
                ),
                description="S2.1",
                trade="concrete",
                scope_id="slab",
                source=(
                    SourceReference(
                        "S2.1",
                        EvidenceKind
                        .DRAWING,
                    )
                ),
            ),
        )

        result = (
            ScopeComplianceEngine
            .evaluate(
                requirements=requirements,
                evidence=evidence,
            )
        )

        self.assertEqual(
            result[0].state,
            ComplianceState
            .UNRESOLVED,
        )

    def test_conflict(self):
        requirements = (
            ScopeRequirement(
                scope_id="slab",
                description="Slab thickness",
                trade="concrete",
                required_evidence=(
                    frozenset(
                        {
                            EvidenceKind
                            .DRAWING,
                            EvidenceKind
                            .SPECIFICATION,
                        }
                    )
                ),
            ),
        )

        evidence = (
            EvidenceRecord(
                evidence_id="drawing",
                kind=(
                    EvidenceKind
                    .DRAWING
                ),
                description="Drawing",
                trade="concrete",
                scope_id="slab",
                source=(
                    SourceReference(
                        "S2.1",
                        EvidenceKind
                        .DRAWING,
                    )
                ),
                value_fingerprint="6in",
            ),
            EvidenceRecord(
                evidence_id="spec",
                kind=(
                    EvidenceKind
                    .SPECIFICATION
                ),
                description="Spec",
                trade="concrete",
                scope_id="slab",
                source=(
                    SourceReference(
                        "033000",
                        EvidenceKind
                        .SPECIFICATION,
                    )
                ),
                value_fingerprint="8in",
            ),
        )

        result = (
            ScopeComplianceEngine
            .evaluate(
                requirements=requirements,
                evidence=evidence,
            )
        )

        self.assertEqual(
            result[0].state,
            ComplianceState.CONFLICT,
        )


class RFITests(
    unittest.TestCase
):

    def test_conflict_generates_blocking_rfi(self):
        requirements = (
            ScopeRequirement(
                scope_id="wall",
                description="Wall thickness",
                trade="concrete",
                required_evidence=(
                    frozenset(
                        {
                            EvidenceKind.DRAWING,
                            EvidenceKind
                            .SPECIFICATION,
                        }
                    )
                ),
            ),
        )

        evidence = (
            EvidenceRecord(
                evidence_id="a",
                kind=(
                    EvidenceKind.DRAWING
                ),
                description="A",
                trade="concrete",
                scope_id="wall",
                source=(
                    SourceReference(
                        "S1",
                        EvidenceKind.DRAWING,
                    )
                ),
                value_fingerprint="12in",
            ),
            EvidenceRecord(
                evidence_id="b",
                kind=(
                    EvidenceKind
                    .SPECIFICATION
                ),
                description="B",
                trade="concrete",
                scope_id="wall",
                source=(
                    SourceReference(
                        "spec",
                        EvidenceKind
                        .SPECIFICATION,
                    )
                ),
                value_fingerprint="16in",
            ),
        )

        compliance = (
            ScopeComplianceEngine
            .evaluate(
                requirements=requirements,
                evidence=evidence,
            )
        )

        rfis = (
            AutomaticRFIEngine
            .from_compliance(
                compliance=compliance,
                evidence=evidence,
            )
        )

        self.assertEqual(
            len(rfis),
            1,
        )

        self.assertEqual(
            rfis[0].severity,
            RFISeverity.BLOCKING,
        )

    def test_missing_info_generates_rfi_without_guessing(self):
        requirements = (
            ScopeRequirement(
                scope_id="feeder",
                description="Feeder conductor",
                trade="electrical",
                required_evidence=(
                    frozenset(
                        {
                            EvidenceKind.DRAWING,
                            EvidenceKind
                            .SPECIFICATION,
                        }
                    )
                ),
            ),
        )

        evidence = ()

        compliance = (
            ScopeComplianceEngine
            .evaluate(
                requirements=requirements,
                evidence=evidence,
            )
        )

        rfis = (
            AutomaticRFIEngine
            .from_compliance(
                compliance=compliance,
                evidence=evidence,
            )
        )

        self.assertEqual(
            len(rfis),
            1,
        )

        self.assertIn(
            "Please provide",
            rfis[0].question,
        )


class BidReadinessTests(
    unittest.TestCase
):

    def test_clean_bid_ready(self):
        schedule = (
            CriticalPathEngine
            .analyze(
                (
                    ScheduleActivity(
                        "A",
                        "Work",
                        5,
                    ),
                )
            )
        )

        result = (
            BidReadinessEngine
            .assess(
                BidReadinessInput(
                    contract_risk=None,
                    compliance=(),
                    rfis=(),
                    procurement=(),
                    schedule=schedule,
                )
            )
        )

        self.assertTrue(
            result.ready_for_submission
        )

        self.assertEqual(
            result.score,
            100,
        )

    def test_blocking_rfi_blocks_bid(self):
        result = (
            BidReadinessEngine
            .assess(
                BidReadinessInput(
                    contract_risk=None,
                    compliance=(
                        (
                            ScopeComplianceEngine
                            .evaluate(
                                requirements=(
                                    ScopeRequirement(
                                        scope_id="x",
                                        description="X",
                                        trade="concrete",
                                        required_evidence=(
                                            frozenset(
                                                {
                                                    EvidenceKind
                                                    .DRAWING
                                                }
                                            )
                                        ),
                                    ),
                                ),
                                evidence=(),
                            )
                        )[0],
                    ),
                    rfis=(
                        AutomaticRFIEngine
                        .from_compliance(
                            compliance=(
                                ScopeComplianceEngine
                                .evaluate(
                                    requirements=(
                                        ScopeRequirement(
                                            scope_id="x",
                                            description="X",
                                            trade="concrete",
                                            required_evidence=(
                                                frozenset(
                                                    {
                                                        EvidenceKind
                                                        .DRAWING
                                                    }
                                                )
                                            ),
                                        ),
                                    ),
                                    evidence=(),
                                )
                            ),
                            evidence=(),
                        )
                    ),
                    procurement=(),
                    schedule=None,
                )
            )
        )

        self.assertFalse(
            result.ready_for_submission
        )

        self.assertGreater(
            result.blocker_count,
            0,
        )


if __name__ == "__main__":
    unittest.main()
