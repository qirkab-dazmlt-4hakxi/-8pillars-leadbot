import os,time,requests
from urllib.parse import urlparse
from ..config import CITIES,BRAVE_MAX_RESULTS,BRAVE_TIMEOUT_SECONDS
from ..models import Lead
from ..utils import now_iso
ENDPOINT='https://api.search.brave.com/res/v1/web/search'
QUERIES=[
    'site:tiktok.com/@ ("need concrete" OR "looking for concrete" OR "concrete contractor")',
    'site:tiktok.com/@ (driveway OR patio OR slab OR foundation) (contractor OR quote OR estimate OR recommendation)',
    'site:tiktok.com/@ ("need a contractor" OR "who does concrete" OR "concrete guy" OR "concrete crew")',
]

def scan():
    key=os.getenv('BRAVE_API_KEY')
    if not key:return []
    out=[];seen=set();h={'Accept':'application/json','X-Subscription-Token':key}
    for city in CITIES:
        for base in QUERIES:
            params={'q':f'{base} "{city.name}" Texas','country':'US','search_lang':'en','ui_lang':'en-US','count':BRAVE_MAX_RESULTS,'freshness':'pd','text_decorations':False,'extra_snippets':True}
            r=requests.get(ENDPOINT,headers=h,params=params,timeout=BRAVE_TIMEOUT_SECONDS)
            if r.status_code==429:return out
            if not r.ok:continue
            results=((r.json().get('web') or {}).get('results') or [])
            if len(results)<2:
                params['freshness']='pw'; rr=requests.get(ENDPOINT,headers=h,params=params,timeout=BRAVE_TIMEOUT_SECONDS)
                if rr.ok:results+=((rr.json().get('web') or {}).get('results') or [])
            for x in results:
                u=x.get('url') or ''
                if 'tiktok.com' not in urlparse(u).netloc.lower():continue
                if u in seen:continue
                seen.add(u);sn=[x.get('description') or '']+(x.get('extra_snippets') or [])
                out.append(Lead(source='tiktok-public',source_url=u,title=x.get('title') or '',text='\n'.join(s for s in sn if s),city=city.name,published_at=x.get('age'),discovered_at=now_iso(),contact_channel='tiktok'))
            time.sleep(.03)
    return out
