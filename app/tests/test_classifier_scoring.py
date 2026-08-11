import unittest
from leadbot.classifier import is_relevant
from leadbot.models import Lead
from leadbot.pipeline import enrich
from leadbot.utils import now_iso
class T(unittest.TestCase):
    def test_ad(self):self.assertFalse(is_relevant("We offer concrete services, free estimates, licensed and insured, serving DFW, call us today"))
    def test_hot(self):
        l=Lead(source="x",source_url="https://x/1",title="Need concrete ASAP",text="My driveway extension in Frisco is 20x20. Call 469-555-0188",discovered_at=now_iso(),published_at="1 hour ago");enrich(l);self.assertGreaterEqual(l.score,70);self.assertEqual(l.city,"Frisco")
