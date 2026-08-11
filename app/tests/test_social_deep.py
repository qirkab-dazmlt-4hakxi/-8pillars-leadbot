import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from leadbot.extract import extract_social_username,infer_contactability
from leadbot.social_dm import leads_from_payload
from leadbot.pipeline import enrich
from leadbot.models import Lead
from leadbot.deep_enrich import allowed

class SocialDeepTests(unittest.TestCase):
    def test_tiktok_username_from_url(self):
        self.assertEqual(extract_social_username('', 'https://www.tiktok.com/@northtexasdad/video/123'),'northtexasdad')

    def test_inbound_tiktok_dm_is_direct_contact(self):
        payload={'event_id':'evt1','sender_name':'John R','open_id':'u123','message':{'text':'Need a concrete contractor for my 20x20 driveway extension in Celina ASAP'}}
        ls=leads_from_payload('tiktok',payload)
        self.assertEqual(len(ls),1)
        l=enrich(ls[0])
        self.assertTrue(l.inbound_message)
        self.assertEqual(l.contactability,'DIRECT_DM')
        self.assertEqual(l.city,'Celina')
        self.assertIn('Driveway',l.scope)
        self.assertEqual(l.square_feet,400)

    def test_meta_dm_parser(self):
        payload={'entry':[{'messaging':[{'sender':{'id':'psid-55'},'message':{'mid':'m1','text':'Looking for concrete quote for patio slab in Frisco this week'}}]}]}
        l=enrich(leads_from_payload('meta',payload)[0])
        self.assertEqual(l.platform_username,'psid-55')
        self.assertEqual(l.contactability,'DIRECT_DM')
        self.assertEqual(l.city,'Frisco')

    def test_public_social_route_contactability(self):
        self.assertEqual(infer_contactability(None,None,'https://www.facebook.com/groups/x/posts/1','Jane D',False),'SOCIAL_DM')
        self.assertEqual(infer_contactability(None,None,'',None,False),'NONE')

    def test_social_pages_not_deep_fetched(self):
        self.assertFalse(allowed('https://www.facebook.com/groups/x/posts/1'))
        self.assertFalse(allowed('https://www.tiktok.com/@abc/video/1'))
        self.assertTrue(allowed('https://example.com/concrete-request'))

if __name__=='__main__':unittest.main()
