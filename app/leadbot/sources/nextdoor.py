import os,requests
from ..config import CITIES
from ..models import Lead
from ..utils import now_iso
QUERIES=["concrete","driveway","patio","foundation","slab","sidewalk","pool deck","patio cover"]

def scan():
    token=os.getenv("NEXTDOOR_ACCESS_TOKEN")
    if not token:return []
    ep=os.getenv("NEXTDOOR_BASE_URL","https://nextdoor.com/content_api/v2/search_post");radius=float(os.getenv("NEXTDOOR_RADIUS_MILES","12"));inc=os.getenv("NEXTDOOR_INCLUDE_COMMENTS","true").lower()=="true";h={"Authorization":f"Bearer {token}","Accept":"application/json"};out=[];seen=set()
    for city in CITIES:
        for q in QUERIES:
            r=requests.get(ep,headers=h,params={"query":q,"lat":city.lat,"lon":city.lon,"radius":radius,"include_comments":str(inc).lower()},timeout=20)
            if r.status_code in (401,403):raise RuntimeError("Nextdoor API authorization failed")
            if not r.ok:continue
            d=r.json();items=d.get("results") or d.get("posts") or (d if isinstance(d,list) else [])
            for x in items:
                xid=str(x.get("id") or x.get("post_id") or "");u=x.get("url") or x.get("web_url") or x.get("embed_url") or "";key=xid or u
                if key and key in seen:continue
                if key:seen.add(key)
                a=x.get("author") or {};n=x.get("neighborhood") or {};comments=x.get("comments") if inc else None;ct=""
                if isinstance(comments,list):ct="\n".join(str(c.get("text") or c.get("body") or "") for c in comments[:20])
                out.append(Lead(source="nextdoor",source_url=u,title=x.get("title") or "",text=((x.get("description") or x.get("body") or "")+"\n"+ct).strip(),discovered_at=now_iso(),published_at=x.get("created_at") or x.get("published_at"),external_id=xid or None,city=city.name,neighborhood=(n.get("name") if isinstance(n,dict) else str(n or "")) or None,poster_name=(a.get("name") if isinstance(a,dict) else str(a or "")) or x.get("author_name"),platform_username=(a.get("username") if isinstance(a,dict) else None),profile_url=(a.get("profile_url") if isinstance(a,dict) else None),contact_channel="nextdoor",contact_route=u))
    return out
