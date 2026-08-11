from __future__ import annotations
import hashlib, re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING_KEYS={"utm_source","utm_medium","utm_campaign","utm_term","utm_content","fbclid","gclid"}

def now_iso(): return datetime.now(timezone.utc).isoformat()

def normalize_url(url: str) -> str:
    if not url: return ""
    try:
        p=urlsplit(url.strip())
        q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in TRACKING_KEYS]
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),re.sub(r"/+$","",p.path or ""),urlencode(q),""))
    except Exception: return url.strip()

def normalize_text(text: str) -> str:
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9@.+ -]"," ",(text or "").lower())).strip()

def sha256(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8","ignore")).hexdigest()
