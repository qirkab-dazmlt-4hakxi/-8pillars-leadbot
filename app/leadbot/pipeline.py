from .config import CONTACTABLE_ONLY_ALERTS
from .deep_enrich import fetch_public_text
from .classifier import is_relevant
from .db import insert_lead
from .extract import *
from .scoring import score
from .utils import normalize_url,normalize_text,sha256
from .alerts import alert

def is_requester_source(l):
    u=(l.source_url or "").lower()
    t=f"{l.title or ''} {l.text or ''}".lower()

    blocked_url=[
        "/service-area", "/service-areas", "/directory/",
        "/blog/", "/careers", "/jobs/", "/listing/",
        "/listings/", "/near-me/"
    ]

    seller_text=[
        "our services", "request a free quote",
        "get a free quote", "call us today",
        "schedule a consultation", "our crews",
        "we specialize", "we provide",
        "serving homeowners", "service area",
        "construction providers"
    ]

    if any(x in u for x in blocked_url):
        return False

    if sum(1 for x in seller_text if x in t) >= 2:
        return False

    return True


def enrich(l):
    deep=fetch_public_text(l.source_url) if l.contact_channel=="source-post" and not (l.phone or l.email) else ""
    if deep and deep not in (l.text or ""):
        l.text=((l.text or "")+"\n"+deep).strip()
    b=f"{l.title}\n{l.text}"
    l.phone=l.phone or extract_phone(b);l.email=l.email or extract_email(b);l.project_address=l.project_address or extract_address(b);l.city=l.city or extract_city(b);l.poster_name=l.poster_name or extract_name(b)
    l.platform_username=l.platform_username or extract_social_username(b,l.source_url)
    l.profile_url=l.profile_url or (f"https://www.tiktok.com/@{l.platform_username}" if l.platform_username and "tiktok.com" in (l.source_url or "") else None)
    l.contactability=l.contactability or infer_contactability(l.phone,l.email,l.source_url,l.poster_name,l.inbound_message)
    l.contact_route=l.contact_route or ("phone/email" if (l.phone or l.email) else (l.source_url if l.source_url else None))
    d,sf=extract_measurements(b);l.dimensions=l.dimensions or d;l.square_feet=l.square_feet or sf;l.scope=l.scope or extract_scope(b);l.urgency=l.urgency or extract_urgency(b);l.source_url=normalize_url(l.source_url);l.evidence=(l.text or "")[:3000];l.fingerprint=sha256(l.source,l.external_id or "",l.source_url,normalize_text(l.title),normalize_text(l.text)[:900]);l.score,l.temperature=score(l);return l

def process(leads,minimum_score=25):
    out=[]
    for l in leads:
        if not is_relevant(f"{l.title}\n{l.text}"):continue
        if not is_requester_source(l):continue
        enrich(l)
        if l.score<minimum_score:continue
        ok,i=insert_lead(l)
        if ok:
            out.append((i,l))
            if (not CONTACTABLE_ONLY_ALERTS) or l.contactability in ("DIRECT","DIRECT_DM","SOCIAL_DM"):
                alert(i,l)
    return out
