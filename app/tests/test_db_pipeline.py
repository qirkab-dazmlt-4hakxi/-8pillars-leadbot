import os,tempfile,unittest,importlib
from pathlib import Path
class T(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();os.environ["DB_PATH"]=str(Path(self.tmp.name)/"test.db");import leadbot.config as c;c.DB_PATH=Path(os.environ["DB_PATH"]);import leadbot.db as db;importlib.reload(db);import leadbot.pipeline as p;importlib.reload(p);self.db=db;self.p=p
    def tearDown(self):self.tmp.cleanup()
    def test_dedupe(self):
        from leadbot.models import Lead
        from leadbot.utils import now_iso
        a=Lead(source="web",source_url="https://example.com/post?utm_source=x",title="Need concrete patio",text="Need concrete contractor for my patio in Denton ASAP. 300 sqft. Call 940-555-0199",discovered_at=now_iso(),published_at="2 hours ago");b=Lead(source="web",source_url="https://example.com/post",title=a.title,text=a.text,discovered_at=now_iso(),published_at="2 hours ago");self.assertEqual(len(self.p.process([a],20)),1);self.assertEqual(len(self.p.process([b],20)),0);self.assertEqual(self.db.stats()["total"],1)

class RepeatContractorDifferentJobs(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();os.environ["DB_PATH"]=str(Path(self.tmp.name)/"test2.db");import leadbot.config as c;c.DB_PATH=Path(os.environ["DB_PATH"]);import leadbot.db as db;importlib.reload(db);import leadbot.pipeline as p;importlib.reload(p);self.p=p
    def tearDown(self):self.tmp.cleanup()
    def test_same_phone_different_job_not_hidden(self):
        from leadbot.models import Lead
        from leadbot.utils import now_iso
        a=Lead(source="facebook",source_url="https://example.com/a",title="Need concrete patio",text="For a client in Denton need concrete contractor for a 300 sqft patio. Call 940-555-0199",discovered_at=now_iso(),published_at="1 hour ago")
        b=Lead(source="facebook",source_url="https://example.com/b",title="Need driveway crew",text="For a client in Celina need concrete crew for a 1200 sqft driveway. Call 940-555-0199",discovered_at=now_iso(),published_at="1 hour ago")
        self.assertEqual(len(self.p.process([a],20)),1)
        self.assertEqual(len(self.p.process([b],20)),1)
