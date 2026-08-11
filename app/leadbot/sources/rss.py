import os
from ..models import Lead
from ..utils import now_iso

def scan():
    urls=[x.strip() for x in os.getenv("RSS_FEEDS","").split(",") if x.strip()]
    if not urls:return []
    try: import feedparser
    except ImportError as e: raise RuntimeError("RSS source requires: pip install feedparser") from e
    out=[]
    for u in urls:
        for e in feedparser.parse(u).entries:
            out.append(Lead(source="rss",source_url=e.get("link",u),title=e.get("title",""),text=e.get("summary","") or e.get("description",""),discovered_at=now_iso(),published_at=e.get("published") or e.get("updated"),external_id=e.get("id"),contact_channel="source-post"))
    return out
