import unittest
from leadbot.extract import *
class T(unittest.TestCase):
    def test_contacts(self):
        t="Call (469) 555-0188 or email owner@example.com at 123 Demo Trail, Celina TX 75009";self.assertEqual(extract_phone(t),"469-555-0188");self.assertEqual(extract_email(t),"owner@example.com");self.assertIn("123 Demo Trail",extract_address(t));self.assertEqual(extract_city(t),"Celina")
    def test_measure(self):
        d,s=extract_measurements("driveway 20x20 plus 1x35");self.assertEqual(d,"20x20, 1x35");self.assertEqual(s,435);self.assertEqual(extract_measurements("Need 410 sqft patio")[1],410)
    def test_scope(self):self.assertIn("Patio",extract_scope("ASAP stamped patio concrete"));self.assertEqual(extract_urgency("Need this ASAP"),"ASAP")
