import email,imaplib,os,re
from datetime import datetime,timedelta,timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from ..models import Lead
from ..utils import now_iso
TAG_RE=re.compile(r'<[^>]+>')

def _dec(v):
    out=[]
    for p,e in decode_header(v or ""):
        out.append(p.decode(e or "utf-8","replace") if isinstance(p,bytes) else str(p))
    return "".join(out)

def _body(msg):
    plain=[];html=[]
    for p in (msg.walk() if msg.is_multipart() else [msg]):
        if p.get_content_maintype()=="multipart" or "attachment" in (p.get("Content-Disposition") or "").lower():continue
        raw=p.get_payload(decode=True)
        if not raw:continue
        txt=raw.decode(p.get_content_charset() or "utf-8","replace")
        if p.get_content_type()=="text/plain":plain.append(txt)
        elif p.get_content_type()=="text/html":html.append(TAG_RE.sub(" ",txt))
    return "\n".join(plain or html)

def scan():
    if not all(os.getenv(x) for x in ["IMAP_HOST","IMAP_USERNAME","IMAP_PASSWORD"]):return []
    cut=datetime.now(timezone.utc)-timedelta(hours=int(os.getenv("IMAP_LOOKBACK_HOURS","48")));keys=[x.strip().lower() for x in os.getenv("IMAP_SUBJECT_KEYWORDS","").split(",") if x.strip()];m=imaplib.IMAP4_SSL(os.getenv("IMAP_HOST"),int(os.getenv("IMAP_PORT","993")));m.login(os.getenv("IMAP_USERNAME"),os.getenv("IMAP_PASSWORD"));m.select(os.getenv("IMAP_FOLDER","INBOX"),readonly=True);typ,data=m.search(None,"SINCE",(cut-timedelta(days=1)).strftime("%d-%b-%Y"));out=[]
    if typ=="OK":
        for num in data[0].split()[-200:]:
            typ,md=m.fetch(num,"(RFC822)");raw=next((x[1] for x in md if isinstance(x,tuple)),None) if typ=="OK" else None
            if not raw:continue
            msg=email.message_from_bytes(raw);sub=_dec(msg.get("Subject"));body=_body(msg);combined=(sub+"\n"+body).lower()
            if keys and not any(k in combined for k in keys):continue
            try:
                dt=parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
                if dt and dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
                if dt and dt.astimezone(timezone.utc)<cut:continue
                pub=dt.astimezone(timezone.utc).isoformat() if dt else None
            except Exception:pub=None
            out.append(Lead(source="imap",source_url="",title=sub,text=f"From: {_dec(msg.get('From'))}\n{body}",discovered_at=now_iso(),published_at=pub,external_id=(msg.get("Message-ID") or "").strip() or None,contact_channel="email"))
    m.logout();return out
