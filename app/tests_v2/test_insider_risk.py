import unittest
from dataclasses import replace

from leadbot_v2.goat.communications.company_gateway import (
    CompanyCommunicationsGateway,
    Direction,
    InMemoryCommunicationArchive,
    RecordingPolicy,
    RecordingState,
)
from leadbot_v2.goat.security.insider_risk import (
    ConflictAwareAlertRouter,
    InMemorySecurityAlertSink,
    InsiderRiskAlertService,
    InsiderRiskEngine,
    InvestigationEvidenceChain,
    RiskDisposition,
    SecuritySignal,
    SecuritySignalType,
)


def signal(
    *,
    signal_id: str,
    user: str,
    signal_type: SecuritySignalType,
    confidence: float = 1.0,
    verified: bool = True,
) -> SecuritySignal:

    return SecuritySignal(
        signal_id=signal_id,
        tenant_id="twins-development",
        subject_user_id=user,
        signal_type=signal_type,
        source_system="endpoint-dlp",
        asset_id="device-1",
        timestamp="2026-08-13T00:00:00+00:00",
        evidence_ref=f"evidence://{signal_id}",
        verified=verified,
        confidence=confidence,
        details="test security event",
    )


class CompanyCommunicationsTests(unittest.TestCase):

    def setUp(self):
        self.archive = InMemoryCommunicationArchive()

        self.gateway = CompanyCommunicationsGateway(
            recording_policy=RecordingPolicy(
                recording_enabled=True,
                disclosure_required=True,
                affirmative_consent_required=True,
            ),
            archive=self.archive,
        )

    def test_call_records_after_notice_and_consent(self):
        call = self.gateway.create_call(
            communication_id="call-1",
            tenant_id="twins-development",
            business_unit="twins-development",
            direction=Direction.INBOUND,
            company_identity="940-510-1880",
            counterparty="+15555550101",
            actor_id="sales-1",
            notice_given=True,
            consent_received=True,
        )

        self.assertEqual(
            call.recording_state,
            RecordingState.RECORDING,
        )

    def test_call_does_not_record_without_consent(self):
        call = self.gateway.create_call(
            communication_id="call-2",
            tenant_id="twins-development",
            business_unit="twins-development",
            direction=Direction.OUTBOUND,
            company_identity="940-510-1880",
            counterparty="+15555550102",
            actor_id="sales-1",
            notice_given=True,
            consent_received=False,
        )

        self.assertEqual(
            call.recording_state,
            RecordingState.DECLINED,
        )

    def test_sms_is_archived(self):
        self.gateway.create_sms(
            communication_id="sms-1",
            tenant_id="twins-development",
            business_unit="twins-development",
            direction=Direction.OUTBOUND,
            company_identity="940-510-1880",
            counterparty="+15555550103",
            actor_id="sales-1",
        )

        self.assertEqual(len(self.archive.items), 1)


class InsiderRiskTests(unittest.TestCase):

    def test_usb_and_customer_export_raise_risk(self):
        signals = (
            signal(
                signal_id="a",
                user="employee-1",
                signal_type=SecuritySignalType.USB_COPY,
            ),
            signal(
                signal_id="b",
                user="employee-1",
                signal_type=(
                    SecuritySignalType.CUSTOMER_LIST_EXPORT
                ),
            ),
        )

        result = InsiderRiskEngine.assess(
            subject_user_id="employee-1",
            signals=signals,
        )

        self.assertEqual(
            result.disposition,
            RiskDisposition.CRITICAL,
        )

    def test_unverified_event_has_reduced_weight(self):
        event = signal(
            signal_id="a",
            user="employee-1",
            signal_type=(
                SecuritySignalType.SOURCE_CODE_EXPORT
            ),
            verified=False,
        )

        result = InsiderRiskEngine.assess(
            subject_user_id="employee-1",
            signals=(event,),
        )

        self.assertLess(result.score, 65)

    def test_financial_manipulation_is_high_risk(self):
        result = InsiderRiskEngine.assess(
            subject_user_id="employee-1",
            signals=(
                signal(
                    signal_id="a",
                    user="employee-1",
                    signal_type=(
                        SecuritySignalType
                        .PAYMENT_DESTINATION_CHANGE
                    ),
                ),
            ),
        )

        self.assertTrue(result.requires_investigation)

    def test_subject_is_excluded_from_alert(self):
        router = ConflictAwareAlertRouter(
            executive_recipients={
                "president": "president@company.com",
                "vp": "vp@company.com",
            },
            security_recipients={
                "security": "security@company.com",
            },
        )

        recipients = router.recipients_for(
            subject_user_id="vp",
        )

        self.assertNotIn(
            "vp@company.com",
            recipients,
        )

        self.assertIn(
            "president@company.com",
            recipients,
        )

    def test_president_investigation_routes_independently(self):
        router = ConflictAwareAlertRouter(
            executive_recipients={
                "president": "president@company.com",
                "vp": "vp@company.com",
            },
            security_recipients={
                "security": "security@company.com",
            },
        )

        recipients = router.recipients_for(
            subject_user_id="president",
        )

        self.assertNotIn(
            "president@company.com",
            recipients,
        )

        self.assertIn(
            "vp@company.com",
            recipients,
        )

        self.assertIn(
            "security@company.com",
            recipients,
        )

    def test_high_risk_creates_alert(self):
        router = ConflictAwareAlertRouter(
            executive_recipients={
                "president": "president@company.com",
                "vp": "vp@company.com",
            },
            security_recipients={
                "security": "security@company.com",
            },
        )

        sink = InMemorySecurityAlertSink()

        service = InsiderRiskAlertService(
            router=router,
            sink=sink,
        )

        assessment = InsiderRiskEngine.assess(
            subject_user_id="employee-1",
            signals=(
                signal(
                    signal_id="a",
                    user="employee-1",
                    signal_type=(
                        SecuritySignalType
                        .BACKUP_DISABLE_ATTEMPT
                    ),
                ),
            ),
        )

        alert = service.evaluate_and_alert(
            assessment
        )

        self.assertIsNotNone(alert)
        self.assertEqual(len(sink.alerts), 1)

    def test_low_risk_does_not_email_executives(self):
        router = ConflictAwareAlertRouter(
            executive_recipients={
                "president": "president@company.com",
                "vp": "vp@company.com",
            },
            security_recipients={
                "security": "security@company.com",
            },
        )

        sink = InMemorySecurityAlertSink()

        service = InsiderRiskAlertService(
            router=router,
            sink=sink,
        )

        assessment = InsiderRiskEngine.assess(
            subject_user_id="employee-1",
            signals=(
                signal(
                    signal_id="a",
                    user="employee-1",
                    signal_type=(
                        SecuritySignalType
                        .UNAUTHORIZED_PRINT
                    ),
                    confidence=0.5,
                ),
            ),
        )

        alert = service.evaluate_and_alert(
            assessment
        )

        self.assertIsNone(alert)
        self.assertEqual(sink.alerts, [])

    def test_evidence_chain_verifies(self):
        chain = InvestigationEvidenceChain()

        chain.append(
            signal(
                signal_id="a",
                user="employee-1",
                signal_type=SecuritySignalType.USB_COPY,
            )
        )

        chain.append(
            signal(
                signal_id="b",
                user="employee-1",
                signal_type=(
                    SecuritySignalType.BULK_DOWNLOAD
                ),
            )
        )

        self.assertTrue(chain.verify())

    def test_evidence_tampering_detected(self):
        chain = InvestigationEvidenceChain()

        chain.append(
            signal(
                signal_id="a",
                user="employee-1",
                signal_type=SecuritySignalType.USB_COPY,
            )
        )

        original = chain._records[0]

        chain._records[0] = replace(
            original,
            evidence_ref="tampered",
        )

        self.assertFalse(chain.verify())


if __name__ == "__main__":
    unittest.main()
