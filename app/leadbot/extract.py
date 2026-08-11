from __future__ import annotations
import re
from typing import Optional
from .config import CITIES

PHONE_RE=re.compile(r'(?<!\d)(?:\+?1[\s.\-]?)?\(?([2-9]\d{2})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})(?!\d)')
EMAIL_RE=re.compile(r'\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b',re.I)
ADDRESS_RE=re.compile(r"\b\d{1,6}\s+[A-Za-z0-9 .#'\-]{2,55}\s(?:St|Street|Rd|Road|Ave|Avenue|Dr|Drive|Ln|Lane|Ct|Court|Blvd|Boulevard|Pkwy|Parkway|Way|Cir|Circle|Trl|Trail|Pl|Place)\b(?:\s*,?\s*(?:Aubrey|Little Elm|Prosper|Denton|Frisco|McKinney|Celina)\s*,?\s*TX(?:\s+\d{5})?)?",re.I)
DIM_RE=re.compile(r"\b(\d{1,4}(?:\.\d+)?)\s*(?:ft|feet|')?\s*[x×]\s*(\d{1,4}(?:\.\d+)?)\s*(?:ft|feet|')?\b",re.I)
SF_RE=re.compile(r'\b([\d,]+(?:\.\d+)?)\s*(?:sf|sq\.?\s*ft\.?|square\s*feet|sqft)\b',re.I)
LINEAR_RE=re.compile(r'\b([\d,]+(?:\.\d+)?)\s*(?:lf|linear\s*feet|linear\s*ft)\b',re.I)
NAME_PATTERNS=[
    re.compile(r'\b(?:posted by|poster|contact|name)\s*[:\-]\s*([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+){0,2})'),
    re.compile(r'\b([A-Z][A-Za-z\'\-]+\s+[A-Z][A-Za-z\'\-]+)\s+(?:is looking for|needs|need|looking for)\b'),
    re.compile(r'\b([A-Z][A-Za-z\'\-]+\s+[A-Z][A-Za-z\'\-]+)\s+and\s+\d+\s+others\b'),
]

def extract_phone(text):
    m=PHONE_RE.search(text or ""); return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

def extract_email(text):
    m=EMAIL_RE.search(text or ""); return m.group(0) if m else None

def extract_address(text):
    m=ADDRESS_RE.search(text or ""); return re.sub(r'\s+',' ',m.group(0)).strip() if m else None

def extract_city(text):
    t=(text or "").lower()
    for c in CITIES:
        if re.search(rf'\b{re.escape(c.name.lower())}\b',t): return c.name
    return None

def extract_name(text):
    for p in NAME_PATTERNS:
        m=p.search(text or "")
        if m: return m.group(1).strip()
    return None

def extract_measurements(text):
    text=text or ""; dims=[]; total=0.0
    for m in DIM_RE.finditer(text):
        a,b=float(m.group(1)),float(m.group(2))
        if 0<a<=2000 and 0<b<=2000:
            dims.append(f"{a:g}x{b:g}"); total+=a*b
    explicit=[float(m.group(1).replace(',','')) for m in SF_RE.finditer(text)]
    sf=max(explicit) if explicit else (total if dims and total<=250000 else None)
    linear=[float(m.group(1).replace(',','')) for m in LINEAR_RE.finditer(text)]
    d=", ".join(dims[:6])
    if linear: d=(d+( ", " if d else "")+", ".join(f"{x:g} LF" for x in linear[:3]))
    return d or None,sf

def extract_scope(text):
    t=(text or "").lower(); out=[]
    pairs=[("driveway","Driveway"),("patio","Patio"),("foundation","Foundation"),("slab","Slab"),("sidewalk","Sidewalk"),("walkway","Walkway"),("pool","Pool deck"),("stamped","Stamped/decorative"),("salt finish","Salt finish"),("rv pad","RV pad"),("garage","Garage slab"),("footing","Footing"),("tear out","Demo/replacement"),("demol","Demo/replacement")]
    for k,v in pairs:
        if k in t and v not in out: out.append(v)
    return ", ".join(out) if out else "Residential concrete"

def extract_urgency(text):
    t=(text or "").lower()
    if any(x in t for x in ["asap","today","tomorrow","immediately","this week","ready now","ready to start"]): return "ASAP"
    if any(x in t for x in ["soon","next week","within 2 weeks","need quote","need estimate"]): return "SOON"
    return None


SOCIAL_USER_PATTERNS=[
    re.compile(r'https?://(?:www\.)?tiktok\.com/@([A-Za-z0-9._-]+)',re.I),
    re.compile(r'\bTikTok\s*[:@]\s*@?([A-Za-z0-9._-]{2,40})',re.I),
    re.compile(r'\bInstagram\s*[:@]\s*@?([A-Za-z0-9._-]{2,40})',re.I),
    re.compile(r'\bFacebook\s*[:@]\s*([A-Za-z0-9 ._-]{2,60})',re.I),
]

def extract_social_username(text,url=''):
    blob=f"{url}\n{text or ''}"
    for p in SOCIAL_USER_PATTERNS:
        m=p.search(blob)
        if m:return m.group(1).strip()
    return None

def infer_contactability(phone,email,source_url,poster_name=None,inbound_message=False):
    if phone or email:return 'DIRECT'
    if inbound_message:return 'DIRECT_DM'
    u=(source_url or '').lower()
    if any(d in u for d in ['facebook.com','tiktok.com','nextdoor.com','instagram.com']):
        return 'SOCIAL_DM' if (poster_name or source_url) else 'WEAK'
    return 'SOURCE' if source_url else 'NONE'
