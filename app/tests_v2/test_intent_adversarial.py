import unittest

from leadbot_v2.intelligence.intent_ensemble import IntentLabel
from leadbot_v2.intelligence.intent_fusion import IntentFusionEngine


class IntentAdversarialTests(unittest.TestCase):

    def setUp(self):
        self.engine = IntentFusionEngine()

    def test_real_homeowner_buyer(self):
        text = (
            "Looking for a concrete contractor to replace our driveway. "
            "Our previous contractor backed out and we are ready to start."
        )
        result = self.engine.analyze(text)
        self.assertFalse(result.quarantined)
        self.assertGreaterEqual(result.assessment.buyer_probability, 0.90)
        self.assertEqual(
            result.assessment.final_label,
            IntentLabel.HOMEOWNER_READY_BUYER,
        )

    def test_clear_contractor_ad(self):
        text = (
            "Our company provides concrete installation throughout DFW. "
            "Licensed and insured. Call us today for a free estimate."
        )
        result = self.engine.analyze(text)
        self.assertGreaterEqual(result.assessment.seller_probability, 0.90)
        self.assertEqual(
            result.assessment.final_label,
            IntentLabel.CONTRACTOR_AD,
        )

    def test_buyer_seller_contradiction_quarantines(self):
        text = (
            "Looking for a concrete contractor. "
            "Our company provides concrete services throughout DFW. "
            "Licensed and insured. Call us today for a free estimate."
        )
        result = self.engine.analyze(text)
        self.assertTrue(result.quarantined)
        self.assertTrue(result.assessment.contradiction)

    def test_cleanup_only_not_buyer(self):
        text = "Need someone for trash removal and yard cleanup after construction."
        result = self.engine.analyze(text)
        self.assertNotEqual(
            result.assessment.final_label,
            IntentLabel.HOMEOWNER_READY_BUYER,
        )

    def test_diy_question_not_buyer(self):
        text = "How do I pour a concrete patio and how much rebar should I use?"
        result = self.engine.analyze(text)
        self.assertEqual(
            result.assessment.final_label,
            IntentLabel.DIY_INFORMATION,
        )

    def test_gc_subcontract_request(self):
        text = (
            "General contractor seeking concrete subcontractor. "
            "Concrete sub needed for project. Send concrete pricing."
        )
        result = self.engine.analyze(text)
        self.assertGreaterEqual(result.assessment.buyer_probability, 0.90)


if __name__ == "__main__":
    unittest.main()
