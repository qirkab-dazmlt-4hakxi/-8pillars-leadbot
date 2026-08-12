import unittest

from leadbot_v2.core import (
    EvidenceType,
    LeadIntelligenceRecord,
    LeadStage,
)


class LeadIntelligenceRecordTests(unittest.TestCase):

    def test_fingerprint_is_deterministic(self):
        a = LeadIntelligenceRecord(
            source="reddit",
            source_url="https://example.com/post/1",
            title="Need concrete contractor",
            raw_text="Need driveway replaced in Prosper",
        )
        b = LeadIntelligenceRecord(
            source="reddit",
            source_url="https://example.com/post/1",
            title="Need concrete contractor",
            raw_text="Need driveway replaced in Prosper",
        )

        self.assertEqual(a.build_fingerprint(), b.build_fingerprint())

    def test_actionable_contact_required_for_alert(self):
        lead = LeadIntelligenceRecord(
            source="reddit",
            source_url="https://example.com/post/1",
            title="Need concrete contractor",
            raw_text="Need driveway replaced in Prosper",
            stage=LeadStage.QUALIFIED,
        )

        lead.scores.buyer_intent = 0.95
        lead.scores.concrete_scope = 0.99

        self.assertFalse(lead.can_alert)

        lead.add_contact(
            channel="dm",
            value="https://example.com/u/customer",
            verified_public=True,
            confidence=0.95,
        )

        self.assertTrue(lead.can_alert)

    def test_evidence_is_recorded(self):
        lead = LeadIntelligenceRecord(
            source="facebook",
            source_url="https://example.com/post/2",
        )

        lead.add_evidence(
            EvidenceType.BUYER_INTENT,
            "Looking for someone to replace our driveway",
            0.98,
        )

        self.assertEqual(len(lead.evidence), 1)
        self.assertEqual(
            lead.evidence[0].kind,
            EvidenceType.BUYER_INTENT,
        )


if __name__ == "__main__":
    unittest.main()
