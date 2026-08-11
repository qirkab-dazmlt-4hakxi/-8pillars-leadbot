import os,tempfile,unittest,importlib
from pathlib import Path
from datetime import datetime,timezone,timedelta

class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();os.environ['DB_PATH']=str(Path(self.tmp.name)/'rem.db')
        import leadbot.config as config;config.DB_PATH=Path(os.environ['DB_PATH']);config.REMINDER_INTERVAL_SECONDS=172800
        import leadbot.db as db;importlib.reload(db);self.db=db
        import leadbot.pipeline as pipeline;importlib.reload(pipeline);self.pipeline=pipeline
    def tearDown(self):self.tmp.cleanup()
    def _lead(self,age_hours=49,url='https://example.com/lead-a'):
        from leadbot.models import Lead
        t=datetime.now(timezone.utc)-timedelta(hours=age_hours)
        return Lead(source='facebook',source_url=url,title='Need concrete patio',text='Homeowner in Celina needs a concrete contractor for 400 sqft patio ASAP. Call 469-555-0199',discovered_at=t.isoformat(),published_at=t.isoformat())
    def test_48_hour_due_then_click_stops(self):
        added=self.pipeline.process([self._lead()],20);self.assertEqual(len(added),1);i=added[0][0]
        self.assertEqual(len(self.db.due_reminders()),1)
        self.db.mark_clicked(i)
        self.assertEqual(len(self.db.due_reminders()),0)
    def test_repeat_reminder_after_another_48_hours(self):
        added=self.pipeline.process([self._lead()],20);i=added[0][0]
        now=datetime.now(timezone.utc);self.db.mark_reminded(i,now-timedelta(hours=49))
        due=self.db.due_reminders(now=now);self.assertEqual(len(due),1);self.assertEqual(due[0]['id'],i)
    def test_status_change_stops_reminder(self):
        added=self.pipeline.process([self._lead()],20);i=added[0][0]
        self.db.set_status(i,'contacted');self.assertEqual(len(self.db.due_reminders()),0)
