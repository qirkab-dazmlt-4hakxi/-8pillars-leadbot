from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from .classifier import classify
from .config import HOT_ALERT_SCORE,WARM_SCORE

def _age_hours(value):
    if not value:return None
    try:
        s=value.strip(); low=s.lower(); first=low.split()[0]
        if "minute" in low:return float(first)/60
        if "hour" in low:return float(first)
        if "day" in low:return float(first)*24
        if "week" in low:return float(first)*168
        try: dt=datetime.fromisoformat(s.replace("Z","+00:00"))
        except ValueError: dt=parsedate_to_datetime(s)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return max(0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()/3600)
    except Exception:return None

def score(l):
    c=classify(f"{l.title}\n{l.text}"); s=0
    s+=min(30,c["intent_hits"]*8); s+=min(20,c["concrete_hits"]*4)
    s+=8 if l.city else 0; s+=15 if l.phone else 0; s+=10 if l.email else 0
    s+=12 if l.contactability in ("DIRECT","DIRECT_DM") else (7 if l.contactability=="SOCIAL_DM" else 0)
    s+=5 if l.project_address else 0; s+=5 if l.square_feet else 0; s+=4 if l.dimensions else 0
    s+=7 if c["homeowner"] else 0; s+=8 if c["client"] else 0; s+=8 if c["trade"] else 0
    s+=8 if l.urgency=="ASAP" else (4 if l.urgency=="SOON" else 0)
    age=_age_hours(l.published_at)
    if age is not None:
        if age<=2:s+=16
        elif age<=6:s+=13
        elif age<=24:s+=10
        elif age<=72:s+=6
        elif age<=168:s+=2
        else:s-=8
    s-=min(45,c["ad_hits"]*24); s=max(0,min(100,int(round(s))))
    return s,("HOT" if s>=HOT_ALERT_SCORE else "WARM" if s>=WARM_SCORE else "COLD")
