import os,unittest
from unittest.mock import patch
from leadbot.sources import brave,nextdoor
from leadbot.config import City

class Resp:
    def __init__(self,data,status=200):self._data=data;self.status_code=status;self.ok=200<=status<300
    def json(self):return self._data
    def raise_for_status(self):
        if not self.ok:raise RuntimeError(self.status_code)

class SourceTests(unittest.TestCase):
    def test_brave_adapter(self):
        os.environ['BRAVE_API_KEY']='test'
        payload={'web':{'results':[{'url':'https://facebook.com/groups/x/posts/1','title':'Need concrete contractor','description':'My patio in Frisco is 20x20 and I need concrete ASAP','age':'1 hour ago'}]}}
        with patch.object(brave,'CITIES',[City('Frisco',33.15,-96.82)]), patch.object(brave,'QUERY_TEMPLATES',['"need concrete"']), patch('leadbot.sources.brave.requests.get',return_value=Resp(payload)):
            rows=brave.scan()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0].city,'Frisco');self.assertIn('20x20',rows[0].text)
    def test_nextdoor_adapter(self):
        os.environ['NEXTDOOR_ACCESS_TOKEN']='test'
        payload={'results':[{'id':'p1','title':'Patio concrete needed','description':'Need concrete for my patio ASAP','created_at':'2026-08-09T15:00:00-05:00','url':'https://nextdoor.com/p/p1','author':{'name':'Public Neighbor'},'neighborhood':{'name':'Example'}}]}
        with patch.object(nextdoor,'CITIES',[City('Celina',33.32,-96.78)]), patch.object(nextdoor,'QUERIES',['concrete']), patch('leadbot.sources.nextdoor.requests.get',return_value=Resp(payload)):
            rows=nextdoor.scan()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0].poster_name,'Public Neighbor');self.assertEqual(rows[0].neighborhood,'Example')

if __name__=='__main__':unittest.main()
