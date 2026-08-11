import json
from ..config import JSON_DROP_DIR
from ..models import Lead
from ..utils import now_iso

def scan():
    JSON_DROP_DIR.mkdir(parents=True,exist_ok=True);proc=JSON_DROP_DIR/"processed";proc.mkdir(exist_ok=True);out=[]
    for p in sorted(JSON_DROP_DIR.glob("*.json")):
        try:
            d=json.loads(p.read_text(encoding="utf-8"));items=d if isinstance(d,list) else [d]
            for x in items:out.append(Lead(source=x.get("source","json-import"),source_url=x.get("source_url",x.get("url","")),title=x.get("title",""),text=x.get("text",x.get("description","")),discovered_at=x.get("discovered_at",now_iso()),published_at=x.get("published_at"),external_id=str(x.get("external_id")) if x.get("external_id") is not None else None,city=x.get("city"),neighborhood=x.get("neighborhood"),poster_name=x.get("poster_name"),phone=x.get("phone"),email=x.get("email"),project_address=x.get("project_address"),contact_channel=x.get("contact_channel","import")))
            p.rename(proc/p.name)
        except Exception:continue
    return out
