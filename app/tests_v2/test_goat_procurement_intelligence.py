import unittest

from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)

from decimal import Decimal

from leadbot_v2.goat.preconstruction.procurement.engine import (
    CostTreatment,
    FindingSeverity,
    ProcurementBlocked,
    ProcurementService,
    ProcurementTrade,
    QuoteCommercialTerms,
    QuoteDisposition,
    QuoteLine,
    QuoteState,
    RFQScopeLine,
    RFQState,
    SupplierCompliance,
    SupplierContact,
    SupplierKind,
    SupplierPerformance,
)


UTC = timezone.utc


def now():
    return datetime(
        2026,
        8,
        15,
        18,
        0,
        tzinfo=UTC,
    )


def today():
    return date(
        2026,
        8,
        15,
    )


def good_terms(
    *,
    validity_days=30,
    freight=0,
    tax=0,
    mobilization=0,
    bond=0,
    delivery_days=14,
):
    return QuoteCommercialTerms(
        tax_treatment=(
            CostTreatment.ADDITIONAL
            if tax
            else CostTreatment.INCLUDED
        ),
        tax_cents=(
            tax
            if tax
            else None
        ),
        freight_treatment=(
            CostTreatment.ADDITIONAL
            if freight
            else CostTreatment.INCLUDED
        ),
        freight_cents=(
            freight
            if freight
            else None
        ),
        mobilization_treatment=(
            CostTreatment.ADDITIONAL
            if mobilization
            else CostTreatment.INCLUDED
        ),
        mobilization_cents=(
            mobilization
            if mobilization
            else None
        ),
        bond_treatment=(
            CostTreatment.ADDITIONAL
            if bond
            else CostTreatment.INCLUDED
        ),
        bond_cents=(
            bond
            if bond
            else None
        ),
        escalation_treatment=(
            CostTreatment.INCLUDED
        ),
        payment_terms="Net 30",
        retainage_percent=(
            Decimal("10")
        ),
        validity_through=(
            today()
            + timedelta(
                days=validity_days
            )
        ),
        estimated_lead_days=(
            delivery_days
        ),
        earliest_delivery_date=(
            today()
            + timedelta(
                days=delivery_days
            )
        ),
    )


def scope_lines():
    return (
        RFQScopeLine(
            scope_line_id="s1",
            scope_key="CONCRETE-5000",
            description=(
                "5000 PSI concrete"
            ),
            trade=(
                ProcurementTrade.CONCRETE
            ),
            quantity=(
                Decimal("100")
            ),
            unit="CY",
            cost_code="03-3000",
            drawing_refs=(
                "S2.1",
            ),
            specification_refs=(
                "03 30 00",
            ),
        ),
        RFQScopeLine(
            scope_line_id="s2",
            scope_key="CONCRETE-6000",
            description=(
                "6000 PSI concrete"
            ),
            trade=(
                ProcurementTrade.CONCRETE
            ),
            quantity=(
                Decimal("50")
            ),
            unit="CY",
            cost_code="03-3000",
            drawing_refs=(
                "S3.1",
            ),
        ),
    )


def quote_lines(
    *,
    price_5000=17000,
    price_6000=19000,
    quantity_5000=100,
    quantity_6000=50,
):
    return (
        QuoteLine(
            quote_line_id="q1",
            scope_key="CONCRETE-5000",
            description="5000 PSI",
            quoted_quantity=(
                Decimal(
                    str(
                        quantity_5000
                    )
                )
            ),
            unit="CY",
            unit_price_cents=(
                price_5000
            ),
            lump_sum_cents=None,
            included=True,
            source_refs=(
                "quote:p1",
            ),
        ),
        QuoteLine(
            quote_line_id="q2",
            scope_key="CONCRETE-6000",
            description="6000 PSI",
            quoted_quantity=(
                Decimal(
                    str(
                        quantity_6000
                    )
                )
            ),
            unit="CY",
            unit_price_cents=(
                price_6000
            ),
            lump_sum_cents=None,
            included=True,
            source_refs=(
                "quote:p1",
            ),
        ),
    )


def create_supplier(
    service,
    name,
    *,
    strong=True,
):
    if strong:
        compliance = SupplierCompliance(
            w9_on_file=True,
            insurance_required=True,
            insurance_expiration=(
                today()
                + timedelta(
                    days=180
                )
            ),
            safety_program_required=True,
            safety_program_on_file=True,
            license_required=False,
            approved_vendor=True,
        )

        performance = SupplierPerformance(
            completed_projects=20,
            on_time_projects=19,
            quality_issue_count=0,
            change_order_issue_count=1,
            payment_dispute_count=0,
            safety_issue_count=0,
            response_count=20,
            invitation_count=20,
            award_count=8,
        )

    else:
        compliance = SupplierCompliance(
            w9_on_file=False,
            insurance_required=True,
            insurance_expiration=None,
            safety_program_required=True,
            safety_program_on_file=False,
        )

        performance = SupplierPerformance(
            completed_projects=0,
            on_time_projects=0,
        )

    return service.create_supplier(
        tenant_id="tenant",
        business_unit_id="twins",
        name=name,
        kind=(
            SupplierKind
            .MATERIAL_SUPPLIER
        ),
        trades=(
            ProcurementTrade.CONCRETE,
        ),
        regions=(
            "DFW",
        ),
        contacts=(
            SupplierContact(
                name="Sales",
                email=(
                    "sales@example.com"
                ),
            ),
        ),
        compliance=compliance,
        performance=performance,
        actor_id="procurement",
    )


def create_rfq(
    service,
    suppliers,
):
    rfq = service.create_rfq(
        tenant_id="tenant",
        business_unit_id="twins",
        project_id="project-1",
        opportunity_id="opp-1",
        estimate_id="estimate-1",
        project_name="Medical Office",
        trade=(
            ProcurementTrade.CONCRETE
        ),
        scope_lines=scope_lines(),
        invited_supplier_ids=tuple(
            supplier.supplier_id
            for supplier
            in suppliers
        ),
        due_at=(
            now()
            + timedelta(
                days=2
            )
        ),
        actor_id="estimator",
    )

    return service.issue_rfq(
        rfq_id=rfq.rfq_id,
        actor_id="estimator",
    )


def receive(
    service,
    rfq,
    supplier,
    *,
    lines=None,
    terms=None,
    number="Q-1",
    exclusions=(),
):
    return service.receive_quote(
        rfq_id=rfq.rfq_id,
        supplier_id=(
            supplier.supplier_id
        ),
        actor_id="estimator",
        lines=(
            lines
            or quote_lines()
        ),
        terms=(
            terms
            or good_terms()
        ),
        received_at=now(),
        quote_number=number,
        exclusions=exclusions,
        source_refs=(
            f"file:{number}",
        ),
    )


class SupplierTests(
    unittest.TestCase
):

    def test_supplier_creation(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Ready Mix One",
        )

        self.assertTrue(
            supplier.active
        )

        self.assertIn(
            ProcurementTrade.CONCRETE,
            supplier.trades,
        )

    def test_supplier_name_is_idempotent(self):
        service = ProcurementService()

        first = create_supplier(
            service,
            "Ready Mix One",
        )

        second = create_supplier(
            service,
            "Ready Mix One",
        )

        self.assertEqual(
            first.supplier_id,
            second.supplier_id,
        )


class RFQTests(
    unittest.TestCase
):

    def test_create_and_issue_rfq(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        self.assertEqual(
            rfq.state,
            RFQState.ISSUED,
        )

    def test_duplicate_scope_key_rejected(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        duplicate = (
            scope_lines()[0],
            scope_lines()[0],
        )

        with self.assertRaises(
            Exception
        ):
            service.create_rfq(
                tenant_id="tenant",
                business_unit_id="twins",
                project_name="Project",
                trade=(
                    ProcurementTrade.CONCRETE
                ),
                scope_lines=duplicate,
                invited_supplier_ids=(
                    supplier.supplier_id,
                ),
                actor_id="user",
            )


class QuoteIntakeTests(
    unittest.TestCase
):

    def test_quote_moves_rfq_to_receiving(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
        )

        self.assertEqual(
            quote.state,
            QuoteState.RECEIVED,
        )

        self.assertEqual(
            service
            .rfq(
                rfq.rfq_id
            )
            .state,
            RFQState.RECEIVING,
        )

    def test_quote_number_idempotent(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        first = receive(
            service,
            rfq,
            supplier,
        )

        second = receive(
            service,
            rfq,
            supplier,
        )

        self.assertEqual(
            first.quote_id,
            second.quote_id,
        )


class LevelingTests(
    unittest.TestCase
):

    def test_complete_quote_normalizes_total(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        expected = (
            100 * 17000
            + 50 * 19000
        )

        self.assertEqual(
            leveled
            .normalized_total_cents,
            expected,
        )

        self.assertTrue(
            leveled.comparable
        )

        self.assertEqual(
            leveled.coverage_percent,
            100.0,
        )

    def test_quantity_difference_normalizes_to_rfq(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            lines=quote_lines(
                quantity_5000=90
            ),
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        self.assertEqual(
            leveled
            .scope_lines[0]
            .normalized_cost_cents,
            100 * 17000,
        )

        self.assertIn(
            "QUOTE_QUANTITY_NORMALIZED",
            {
                finding.code
                for finding
                in leveled
                .scope_lines[0]
                .findings
            },
        )

    def test_missing_required_scope_is_blocker(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            lines=(
                quote_lines()[0],
            ),
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        self.assertFalse(
            leveled.comparable
        )

        self.assertIn(
            "RFQ_SCOPE_MISSING_FROM_QUOTE",
            {
                finding.code
                for finding
                in leveled.findings
            },
        )

    def test_unit_mismatch_is_blocker(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        bad_line = QuoteLine(
            quote_line_id="q1",
            scope_key="CONCRETE-5000",
            description="5000 PSI",
            quoted_quantity=Decimal("100"),
            unit="TON",
            unit_price_cents=17000,
            lump_sum_cents=None,
            included=True,
        )

        quote = receive(
            service,
            rfq,
            supplier,
            lines=(
                bad_line,
                quote_lines()[1],
            ),
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        self.assertIn(
            "QUOTE_UNIT_MISMATCH",
            {
                finding.code
                for finding
                in leveled.findings
            },
        )

        self.assertFalse(
            leveled.comparable
        )

    def test_additional_freight_is_added(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            terms=good_terms(
                freight=25000
            ),
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        base = (
            100 * 17000
            + 50 * 19000
        )

        self.assertEqual(
            leveled
            .normalized_total_cents,
            base + 25000,
        )

    def test_unknown_freight_prevents_final_total(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        terms = good_terms()

        terms = terms.__class__(
            tax_treatment=(
                terms.tax_treatment
            ),
            tax_cents=(
                terms.tax_cents
            ),
            freight_treatment=(
                CostTreatment.UNKNOWN
            ),
            freight_cents=None,
            mobilization_treatment=(
                terms
                .mobilization_treatment
            ),
            mobilization_cents=(
                terms
                .mobilization_cents
            ),
            bond_treatment=(
                terms.bond_treatment
            ),
            bond_cents=(
                terms.bond_cents
            ),
            escalation_treatment=(
                terms
                .escalation_treatment
            ),
            payment_terms=(
                terms.payment_terms
            ),
            retainage_percent=(
                terms
                .retainage_percent
            ),
            validity_through=(
                terms
                .validity_through
            ),
            estimated_lead_days=(
                terms
                .estimated_lead_days
            ),
            earliest_delivery_date=(
                terms
                .earliest_delivery_date
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            terms=terms,
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        self.assertIsNone(
            leveled
            .normalized_total_cents
        )

        self.assertFalse(
            leveled.comparable
        )

    def test_expired_quote_is_blocked(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            terms=good_terms(
                validity_days=-1
            ),
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        self.assertTrue(
            leveled.expired
        )

        self.assertFalse(
            leveled.comparable
        )

    def test_delivery_after_required_date_blocks(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            terms=good_terms(
                delivery_days=30
            ),
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
                required_by=(
                    today()
                    + timedelta(
                        days=20
                    )
                ),
            )
        )

        self.assertIn(
            "DELIVERY_AFTER_REQUIRED_DATE",
            {
                finding.code
                for finding
                in leveled.findings
            },
        )


class ComplianceTests(
    unittest.TestCase
):

    def test_missing_required_insurance_blocks(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Risky Supplier",
            strong=False,
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
        )

        leveled = (
            service
            .leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=today(),
            )
        )

        self.assertIn(
            "INSURANCE_MISSING",
            {
                finding.code
                for finding
                in leveled.findings
            },
        )

        self.assertFalse(
            leveled.comparable
        )


class RecommendationTests(
    unittest.TestCase
):

    def test_best_value_can_beat_raw_low_price(self):
        service = ProcurementService()

        strong = create_supplier(
            service,
            "Strong Supplier",
            strong=True,
        )

        weak = create_supplier(
            service,
            "Weak Supplier",
            strong=False,
        )

        rfq = create_rfq(
            service,
            (
                strong,
                weak,
            ),
        )

        receive(
            service,
            rfq,
            strong,
            number="STRONG",
            lines=quote_lines(
                price_5000=17000,
                price_6000=19000,
            ),
        )

        receive(
            service,
            rfq,
            weak,
            number="WEAK",
            lines=quote_lines(
                price_5000=16000,
                price_6000=18000,
            ),
        )

        recommendations = (
            service.recommendations(
                rfq_id=(
                    rfq.rfq_id
                ),
                as_of=today(),
            )
        )

        recommended = next(
            (
                item
                for item
                in recommendations
                if item.disposition
                == QuoteDisposition
                .RECOMMENDED
            ),
            None,
        )

        self.assertIsNotNone(
            recommended
        )

        self.assertEqual(
            recommended
            .supplier_id,
            strong.supplier_id,
        )

    def test_missing_scope_quote_is_not_recommended(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        receive(
            service,
            rfq,
            supplier,
            lines=(
                quote_lines()[0],
            ),
        )

        recommendations = (
            service.recommendations(
                rfq_id=(
                    rfq.rfq_id
                ),
                as_of=today(),
            )
        )

        self.assertNotIn(
            QuoteDisposition.RECOMMENDED,
            {
                item.disposition
                for item
                in recommendations
            },
        )


class AwardTests(
    unittest.TestCase
):

    def test_recommended_quote_can_be_awarded(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
        )

        award = service.award(
            rfq_id=(
                rfq.rfq_id
            ),
            quote_id=(
                quote.quote_id
            ),
            actor_id="president",
            note=(
                "Approved procurement award."
            ),
            as_of=today(),
        )

        self.assertGreater(
            award
            .awarded_amount_cents,
            0,
        )

        self.assertEqual(
            service
            .rfq(
                rfq.rfq_id
            )
            .state,
            RFQState.AWARDED,
        )

        self.assertEqual(
            service
            .quote(
                quote.quote_id
            )
            .state,
            QuoteState.AWARDED,
        )

    def test_noncomparable_quote_cannot_award(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            lines=(
                quote_lines()[0],
            ),
        )

        with self.assertRaises(
            ProcurementBlocked
        ):
            service.award(
                rfq_id=(
                    rfq.rfq_id
                ),
                quote_id=(
                    quote.quote_id
                ),
                actor_id="president",
                note="award",
                as_of=today(),
            )


class PriceCandidateTests(
    unittest.TestCase
):

    def test_comparable_quote_exports_rate_candidates(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
        )

        candidates = (
            service.price_candidates(
                quote_id=(
                    quote.quote_id
                ),
                as_of=today(),
            )
        )

        self.assertEqual(
            len(
                candidates
            ),
            2,
        )

        self.assertEqual(
            candidates[0]
            .normalized_unit_price_cents,
            17000,
        )

        self.assertGreater(
            candidates[0]
            .confidence,
            0,
        )

    def test_noncomparable_quote_cannot_export_price(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        quote = receive(
            service,
            rfq,
            supplier,
            lines=(
                quote_lines()[0],
            ),
        )

        with self.assertRaises(
            ProcurementBlocked
        ):
            service.price_candidates(
                quote_id=(
                    quote.quote_id
                ),
                as_of=today(),
            )


class AuditTests(
    unittest.TestCase
):

    def test_rfq_audit_chain_verifies(self):
        service = ProcurementService()

        supplier = create_supplier(
            service,
            "Supplier",
        )

        rfq = create_rfq(
            service,
            (
                supplier,
            ),
        )

        receive(
            service,
            rfq,
            supplier,
        )

        service.level_rfq(
            rfq_id=(
                rfq.rfq_id
            ),
            actor_id="estimator",
            as_of=today(),
        )

        self.assertTrue(
            service.verify_audit(
                rfq.rfq_id
            )
        )


if __name__ == "__main__":
    unittest.main()
