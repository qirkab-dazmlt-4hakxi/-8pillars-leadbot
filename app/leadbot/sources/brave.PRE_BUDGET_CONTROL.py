import os,time,requests
from urllib.parse import urlparse
from ..config import CITIES,QUERY_TEMPLATES,BUYER_QUERY_TEMPLATES,BRAVE_MAX_RESULTS,BRAVE_TIMEOUT_SECONDS
from ..models import Lead
from ..utils import now_iso
ENDPOINT="https://api.search.brave.com/res/v1/web/search"

def scan():
    key=os.getenv("BRAVE_API_KEY")
    if not key:return []
    out=[];seen=set()
    for city in CITIES:
        for template in BUYER_QUERY_TEMPLATES:
            q=f'({template}) "{city.name}" Texas';headers={"Accept":"application/json","Accept-Encoding":"gzip","Cache-Control":"no-cache","X-Subscription-Token":key,"X-Loc-Lat":str(city.lat),"X-Loc-Long":str(city.lon),"X-Loc-City":city.name,"X-Loc-State":"TX","X-Loc-Country":"US","X-Loc-Timezone":"America/Chicago"}
            params={"q":q,"country":"US","search_lang":"en","ui_lang":"en-US","count":BRAVE_MAX_RESULTS,"freshness":"pd","safesearch":"moderate","text_decorations":False,"extra_snippets":True}
            r=requests.get(ENDPOINT,headers=headers,params=params,timeout=BRAVE_TIMEOUT_SECONDS)
            if r.status_code==429:return out
            r.raise_for_status();results=((r.json().get("web") or {}).get("results") or [])
            if len(results)<3:
                params["freshness"]="pw";r=requests.get(ENDPOINT,headers=headers,params=params,timeout=BRAVE_TIMEOUT_SECONDS)
                if r.status_code!=429 and r.ok:results+=((r.json().get("web") or {}).get("results") or [])
            for x in results:
                u=x.get("url") or "";k=(u,x.get("title") or "")
                if k in seen:continue
                seen.add(k);sn=[x.get("description") or ""]+(x.get("extra_snippets") or [])
                host=urlparse(u).netloc.lower(); channel=("tiktok" if "tiktok.com" in host else "facebook" if "facebook.com" in host else "nextdoor" if "nextdoor.com" in host else "instagram" if "instagram.com" in host else "source-post"); out.append(Lead(source=host or "brave-web",source_url=u,title=x.get("title") or "",text="\n".join(s for s in sn if s),city=city.name,published_at=x.get("age"),discovered_at=now_iso(),contact_channel=channel))
            time.sleep(.03)
    return out
