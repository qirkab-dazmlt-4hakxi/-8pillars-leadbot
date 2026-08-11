import csv,sqlite3
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from .config import DB_PATH, REMINDER_INTERVAL_SECONDS
from .utils import normalize_text,normalize_url

DDL="""
CREATE TABLE IF NOT EXISTS leads(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 fingerprint TEXT UNIQUE NOT NULL,
 external_id TEXT,source TEXT NOT NULL,source_url TEXT,title TEXT,text TEXT,evidence TEXT,
 city TEXT,neighborhood TEXT,poster_name TEXT,phone TEXT,email TEXT,project_address TEXT,
 scope TEXT,dimensions TEXT,square_feet REAL,urgency TEXT,contact_channel TEXT,
 platform_username TEXT,profile_url TEXT,contactability TEXT,contact_route TEXT,inbound_message INTEGER NOT NULL DEFAULT 0,
 score INTEGER NOT NULL DEFAULT 0,temperature TEXT NOT NULL DEFAULT 'COLD',
 discovered_at TEXT NOT NULL,published_at TEXT,status TEXT NOT NULL DEFAULT 'new',
 notes TEXT NOT NULL DEFAULT '',last_contacted_at TEXT,
 clicked_at TEXT,reminder_sent_at TEXT,reminder_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_clicked ON leads(clicked_at);
"""
VALID_STATUSES={"new","contacted","site_visit","quoted","won","lost","archived"}

MIGRATIONS={
    "clicked_at":"ALTER TABLE leads ADD COLUMN clicked_at TEXT",
    "reminder_sent_at":"ALTER TABLE leads ADD COLUMN reminder_sent_at TEXT",
    "reminder_count":"ALTER TABLE leads ADD COLUMN reminder_count INTEGER NOT NULL DEFAULT 0",
    "platform_username":"ALTER TABLE leads ADD COLUMN platform_username TEXT",
    "profile_url":"ALTER TABLE leads ADD COLUMN profile_url TEXT",
    "contactability":"ALTER TABLE leads ADD COLUMN contactability TEXT",
    "contact_route":"ALTER TABLE leads ADD COLUMN contact_route TEXT",
    "inbound_message":"ALTER TABLE leads ADD COLUMN inbound_message INTEGER NOT NULL DEFAULT 0",
}

def _utcnow(): return datetime.now(timezone.utc)
def _iso(dt=None): return (dt or _utcnow()).isoformat()
def _parse_iso(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:return None

def connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB_PATH);c.row_factory=sqlite3.Row;c.executescript(DDL)
    cols={r[1] for r in c.execute("PRAGMA table_info(leads)")}
    for name,sql in MIGRATIONS.items():
        if name not in cols:c.execute(sql)
    c.commit();return c

def is_probable_duplicate(c,l):
    rows=c.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 250").fetchall()
    nt=normalize_text(f"{l.title} {l.text}");nu=normalize_url(l.source_url)
    for r in rows:
        # Exact canonical source URL is always the same lead.
        if nu and normalize_url(r["source_url"] or "")==nu:return True
        # Explicit source-side IDs are preferred when available.
        if l.external_id and r["external_id"] and l.source==r["source"] and l.external_id==r["external_id"]:return True
        ot=normalize_text(f"{r['title'] or ''} {r['text'] or ''}")
        sim=SequenceMatcher(None,nt[:1600],ot[:1600]).ratio() if nt and ot else 0
        same_city=bool(l.city and r["city"]==l.city)
        same_scope=bool(l.scope and r["scope"]==l.scope)
        # Same contractor may publish many projects. Phone/email alone never dedupes.
        # Require same city + scope + substantial text similarity.
        if same_city and same_scope and sim>=0.82 and ((l.phone and r["phone"]==l.phone) or (l.email and r["email"]==l.email)):return True
        # Near-identical text catches reposts mirrored across search engines.
        if sim>=0.93:return True
    return False

def insert_lead(l):
    c=connect()
    try:
        if is_probable_duplicate(c,l):return False,None
        d=l.asdict();d["source_url"]=normalize_url(d.get("source_url") or "");cols=list(d)
        cur=c.execute(f"INSERT INTO leads ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",[d[k] for k in cols]);c.commit();return True,cur.lastrowid
    except sqlite3.IntegrityError:return False,None
    finally:c.close()

def list_leads(limit=100,min_score=0,status=None,city=None,contactable_only=False):
    c=connect();where=["score>=?"];params=[min_score]
    if status:where.append("status=?");params.append(status)
    if city:where.append("city=?");params.append(city)
    if contactable_only:where.append("contactability IN ('DIRECT','DIRECT_DM','SOCIAL_DM')")
    params.append(limit);rows=c.execute(f"SELECT * FROM leads WHERE {' AND '.join(where)} ORDER BY score DESC,id DESC LIMIT ?",params).fetchall();c.close();return [dict(x) for x in rows]

def get_lead(i):
    c=connect();r=c.execute("SELECT * FROM leads WHERE id=?",(i,)).fetchone();c.close();return dict(r) if r else None

def set_status(i,s):
    if s not in VALID_STATUSES:raise ValueError("invalid status")
    c=connect();c.execute("UPDATE leads SET status=? WHERE id=?",(s,i));c.commit();c.close()

def mark_clicked(i,when=None):
    c=connect();c.execute("UPDATE leads SET clicked_at=? WHERE id=?",(_iso(when),i));c.commit();c.close()

def due_reminders(now=None):
    """Return untouched NEW leads due for their first or repeated 48-hour reminder."""
    now=now or _utcnow();interval=timedelta(seconds=REMINDER_INTERVAL_SECONDS)
    c=connect();rows=c.execute("SELECT * FROM leads WHERE status='new' AND clicked_at IS NULL ORDER BY id").fetchall();c.close()
    due=[]
    for row in rows:
        r=dict(row);created=_parse_iso(r.get("discovered_at"));last=_parse_iso(r.get("reminder_sent_at"))
        if not created:continue
        anchor=last or created
        if now-anchor>=interval:due.append(r)
    return due

def mark_reminded(i,when=None):
    c=connect();c.execute("UPDATE leads SET reminder_sent_at=?, reminder_count=COALESCE(reminder_count,0)+1 WHERE id=?",(_iso(when),i));c.commit();c.close()

def stats():
    c=connect();total=c.execute("SELECT COUNT(*) FROM leads").fetchone()[0];hot=c.execute("SELECT COUNT(*) FROM leads WHERE temperature='HOT'").fetchone()[0];won=c.execute("SELECT COUNT(*) FROM leads WHERE status='won'").fetchone()[0];untouched=c.execute("SELECT COUNT(*) FROM leads WHERE status='new' AND clicked_at IS NULL").fetchone()[0];by_city={r[0]:r[1] for r in c.execute("SELECT COALESCE(city,'Unknown'),COUNT(*) FROM leads GROUP BY city ORDER BY COUNT(*) DESC")};c.close();return {"total":total,"hot":hot,"won":won,"untouched":untouched,"by_city":by_city}

def export_csv(path):
    rows=list_leads(100000,0);p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    if not rows:p.write_text("",encoding="utf-8");return p
    with p.open("w",newline="",encoding="utf-8") as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return p
