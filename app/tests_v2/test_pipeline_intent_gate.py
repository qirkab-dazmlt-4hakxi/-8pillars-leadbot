import unittest
from types import SimpleNamespace

from leadbot_v2.core.pipeline import LeadIntelligencePipeline


class FakeLead:
    def __init__(self, title, text, url="https://example.com/post"):
        self.title = title
        self.raw_text = text
        self.source_url = url
        self.metadata = {}
        self.evidence = []
        self.stage = None
        self.rejection_reason = None
        self.scores = SimpleNamespace(source_trust=0.0)

    def add_evidence(
        self,
        evidence_type,
        text,
        confidence,
        source_url=None,
    ):
        self.evidence.append(
            SimpleNamespace(
                evidence_type=evidence_type,
                text=text,
                confidence=confidence,
                source_url=source_url,
            )
        )


class PipelineIntentGateTests(unittest.TestCase):

    def setUp(self):
        self.pipeline = LeadIntelligencePipeline()

    def test_real_homeowner_driveway_buyer_passes(self):
        lead = FakeLead(
            "Need driveway replaced in Frisco",
            (
                "I'm a homeowner in Frisco. My existing concrete driveway "
                "is badly cracked and I need a contractor to remove and "
                "replace it. Looking to get estimates and start soon."
            ),
        )

        passed, reason = self.pipeline._intent_gate(lead)

        self.assertTrue(passed, reason)
        self.assertGreaterEqual(
            lead.metadata["intent"]["buyer_probability"],
            0.70,
        )

    def test_contractor_ad_is_blocked(self):
        lead = FakeLead(
            "Need concrete work?",
            (
                "We are professional concrete contractors serving DFW. "
                "Driveways patios slabs and foundations. Free estimates. "
                "Call today for affordable concrete services."
            ),
        )

        passed, reason = self.pipeline._intent_gate(lead)

        self.assertFalse(passed)
        self.assertIn("blocked intent", reason)

    def test_cleanup_only_request_is_blocked(self):
        lead = FakeLead(
            "Need help cleaning driveway",
            (
                "Need someone to remove trash and dried concrete bags "
                "from around my driveway. No concrete construction or "
                "replacement needed."
            ),
        )

        passed, reason = self.pipeline._intent_gate(lead)

        self.assertFalse(passed)

    def test_diy_information_is_blocked(self):
        lead = FakeLead(
            "How thick should a driveway be?",
            (
                "I'm doing my driveway myself. What PSI concrete and "
                "rebar spacing should I use? Not looking to hire anyone."
            ),
        )

        passed, reason = self.pipeline._intent_gate(lead)

        self.assertFalse(passed)

    def test_buyer_seller_contradiction_is_quarantined(self):
        lead = FakeLead(
            "Need a concrete contractor",
            (
                "I need someone to replace my driveway, but we also offer "
                "professional concrete installation throughout DFW. "
                "Call us for free estimates and concrete services."
            ),
        )

        passed, reason = self.pipeline._intent_gate(lead)

        self.assertFalse(passed)
        self.assertTrue(
            lead.metadata["intent"]["quarantined"]
            or lead.metadata["intent"]["seller_probability"] >= 0.80
        )

    def test_blocked_intent_never_reaches_contact_enrichment(self):
        lead = FakeLead(
            "Concrete company serving Dallas",
            (
                "Professional concrete contractor. Driveways, patios, "
                "foundations and slabs. Free estimates. Call today."
            ),
        )

        self.pipeline.domains.inspect = lambda **kwargs: SimpleNamespace(
            suppress=False,
            trust_score=0.90,
            reason="trusted domain",
        )

        def forbidden_contact_enrichment(_lead):
            raise AssertionError(
                "blocked intent reached contact enrichment"
            )

        self.pipeline.public_contact.extract = forbidden_contact_enrichment

        result = self.pipeline.process_record(lead)

        self.assertFalse(result.accepted)
        self.assertTrue(result.suppressed)
        self.assertIn(
            "intent",
            result.reason.lower(),
        )


if __name__ == "__main__":
    unittest.main()
