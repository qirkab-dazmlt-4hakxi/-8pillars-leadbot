import unittest
from types import SimpleNamespace

from leadbot_v2.core.pipeline import LeadIntelligencePipeline


class FakeLead:
    def __init__(self, title, text):
        self.title = title
        self.raw_text = text
        self.source_url = "https://example.com/post"
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


class PipelineIntentCounterexampleTests(unittest.TestCase):

    def setUp(self):
        self.pipeline = LeadIntelligencePipeline()

    def assertBuyerPasses(self, title, text):
        lead = FakeLead(title, text)
        passed, reason = self.pipeline._intent_gate(lead)
        self.assertTrue(
            passed,
            f"legitimate buyer incorrectly blocked: {reason} | "
            f"{lead.metadata.get('intent')}",
        )

    def test_cleanup_is_only_preparation_for_real_project(self):
        self.assertBuyerPasses(
            "Need driveway replacement in Prosper",
            (
                "I need some debris removed first, then I need my existing "
                "concrete driveway demolished and completely replaced. "
                "I'm the homeowner and want to hire a concrete contractor."
            ),
        )

    def test_demolition_plus_replacement_is_real_concrete_scope(self):
        self.assertBuyerPasses(
            "Looking for concrete contractor in Frisco",
            (
                "Need someone to demo my cracked driveway and pour a new "
                "concrete driveway. Looking for pricing and availability."
            ),
        )

    def test_previous_contractor_free_estimate_does_not_make_buyer_seller(self):
        self.assertBuyerPasses(
            "Concrete contractor backed out",
            (
                "The previous contractor gave me a free estimate and then "
                "ghosted me. I still need my patio poured and I'm looking "
                "to hire another concrete contractor in Celina."
            ),
        )

    def test_homeowner_mentions_diy_but_wants_professional(self):
        self.assertBuyerPasses(
            "Need professional concrete help",
            (
                "I considered doing the patio myself but decided against it. "
                "I want to hire a professional contractor to form and pour "
                "the new concrete patio."
            ),
        )

    def test_cleanup_and_concrete_are_separate_scopes(self):
        self.assertBuyerPasses(
            "Backyard concrete project",
            (
                "There is junk that needs to be cleared from the area, but "
                "the actual project is a new 20 by 30 concrete patio. "
                "I need a contractor to pour and finish it."
            ),
        )

    def test_contractor_word_alone_does_not_mean_seller(self):
        self.assertBuyerPasses(
            "Need contractor recommendation",
            (
                "Can anyone recommend a good concrete contractor? "
                "I need my driveway replaced at my house in McKinney."
            ),
        )


if __name__ == "__main__":
    unittest.main()
