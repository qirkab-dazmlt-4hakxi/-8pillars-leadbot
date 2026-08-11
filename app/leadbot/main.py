import argparse,json,time
from .config import SCAN_INTERVAL_SECONDS
from .db import export_csv,stats
from .pipeline import process
from .sources import brave,tiktok_public,nextdoor,imap_source,rss,json_drop
from .demo import sample_leads
from .reminders import run_reminders
SOURCES=[("brave",brave),("tiktok",tiktok_public),("nextdoor",nextdoor),("imap",imap_source),("rss",rss),("json",json_drop)]

def scan_live():
    cand=[];counts={};errors=[]
    for name,mod in SOURCES:
        try:items=mod.scan();counts[name]=len(items);cand.extend(items)
        except Exception as e:errors.append(f"{name}: {e}");counts[name]=0
    added=process(cand);rem=run_reminders()
    print(json.dumps({"candidates":len(cand),"added":len(added),"reminders":len(rem),"sources":counts,"errors":errors},indent=2))
    for i,l in sorted(added,key=lambda x:x[1].score,reverse=True)[:30]:print(f"{i:4} | {l.score:3} {l.temperature:4} | {l.city or '-':11} | {l.scope:28} | {l.phone or '-':12} | {l.source_url or l.source}")
    for r,delivered in rem:print(f"REMINDER | lead {r['id']} | {r.get('city') or '-'} | {r.get('scope') or '-'} | delivered={delivered}")
    return 0 if not errors else 2

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True);sub.add_parser("scan-now");sub.add_parser("watch");sub.add_parser("selftest");sub.add_parser("stats");sub.add_parser("reminders-now");ex=sub.add_parser("export-csv");ex.add_argument("--output",default="data/leads.csv");a=p.parse_args()
    if a.cmd=="scan-now":return scan_live()
    if a.cmd=="stats":print(json.dumps(stats(),indent=2));return 0
    if a.cmd=="reminders-now":print(json.dumps({"reminders":len(run_reminders())}));return 0
    if a.cmd=="export-csv":print(export_csv(a.output));return 0
    if a.cmd=="selftest":
        import tempfile
        from pathlib import Path
        from datetime import datetime,timezone,timedelta
        from . import db as dbmod
        old=dbmod.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                dbmod.DB_PATH=Path(td)/"selftest.db"
                added=process(sample_leads(),20)
                assert len(added)==2,f"expected 2 leads got {len(added)}"
                ls=[l for _,l in added]
                assert any(l.city=="Celina" and l.phone=="469-555-0188" and l.square_feet==435 for l in ls)
                assert any(l.city=="Little Elm" and l.email=="homeowner@example.com" and l.square_feet==410 for l in ls)
                assert dbmod.stats()["total"]==2
                lead_id=added[0][0]
                old_time=datetime.now(timezone.utc)-timedelta(hours=49)
                c=dbmod.connect();c.execute("UPDATE leads SET discovered_at=? WHERE id=?",(old_time.isoformat(),lead_id));c.commit();c.close()
                assert len(dbmod.due_reminders())==1
                dbmod.mark_clicked(lead_id)
                assert len(dbmod.due_reminders())==0
            print("SELFTEST PASS")
            return 0
        finally:dbmod.DB_PATH=old
    while True:
        try:scan_live()
        except Exception as e:print("watch scan failed",repr(e))
        time.sleep(SCAN_INTERVAL_SECONDS)
if __name__=="__main__":raise SystemExit(main())
