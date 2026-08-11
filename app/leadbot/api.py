import os,json,base64,hmac
from fastapi import FastAPI,HTTPException,Request,Query
from fastapi.responses import PlainTextResponse
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from .db import list_leads,get_lead,set_status,stats,mark_clicked
from .pipeline import process
from .social_dm import leads_from_payload,verify_meta_signature
from .config import WEBHOOK_SHARED_SECRET,META_VERIFY_TOKEN,META_APP_SECRET
from .dashboard import render
app=FastAPI(title=os.getenv("DASHBOARD_TITLE","8 Pillars Residential Concrete LeadBot"),version="3.1.0")

@app.middleware("http")
async def optional_basic_auth(request,call_next):
    # Keep platform webhooks reachable; each webhook validates its own signature/token.
    if request.url.path.startswith("/webhooks/"):
        return await call_next(request)
    user=os.getenv("DASHBOARD_USERNAME",""); pw=os.getenv("DASHBOARD_PASSWORD","")
    if not user or not pw:return await call_next(request)
    auth=request.headers.get("authorization","")
    ok=False
    if auth.lower().startswith("basic "):
        try:
            raw=base64.b64decode(auth.split(" ",1)[1]).decode("utf-8");u,p=raw.split(":",1)
            ok=hmac.compare_digest(u,user) and hmac.compare_digest(p,pw)
        except Exception:ok=False
    if not ok:
        from fastapi.responses import Response
        return Response(status_code=401,headers={"WWW-Authenticate":"Basic"})
    return await call_next(request)
@app.get("/",response_class=HTMLResponse)
def dashboard():return render(list_leads(250,25,contactable_only=True),os.getenv("DASHBOARD_TITLE","8 Pillars Residential Concrete LeadBot"))
@app.get("/api/leads")
def leads(limit:int=100,min_score:int=0,status:str|None=None,city:str|None=None,contactable_only:bool=True):return list_leads(limit,min_score,status,city,contactable_only)
@app.get("/api/leads/{lead_id}")
def lead(lead_id:int):
    r=get_lead(lead_id)
    if not r:raise HTTPException(404,"lead not found")
    return r
class StatusUpdate(BaseModel):status:str
@app.patch("/api/leads/{lead_id}/status")
def update_status(lead_id:int,b:StatusUpdate):
    try:set_status(lead_id,b.status)
    except ValueError as e:raise HTTPException(400,str(e))
    return {"ok":True}
@app.post("/api/leads/{lead_id}/clicked")
def clicked(lead_id:int):
    if not get_lead(lead_id):raise HTTPException(404,"lead not found")
    mark_clicked(lead_id);return {"ok":True}
@app.get("/api/stats")
def lead_stats():return stats()


def _secret_ok(token):
    return (not WEBHOOK_SHARED_SECRET) or token==WEBHOOK_SHARED_SECRET

@app.get('/webhooks/meta',response_class=PlainTextResponse)
def meta_verify(hub_mode:str|None=Query(None,alias='hub.mode'),hub_verify_token:str|None=Query(None,alias='hub.verify_token'),hub_challenge:str|None=Query(None,alias='hub.challenge')):
    if hub_mode=='subscribe' and META_VERIFY_TOKEN and hub_verify_token==META_VERIFY_TOKEN:return hub_challenge or ''
    raise HTTPException(403,'verification failed')

@app.post('/webhooks/meta')
async def meta_webhook(request:Request,token:str|None=None):
    raw=await request.body()
    if META_APP_SECRET and not verify_meta_signature(raw,request.headers.get('x-hub-signature-256'),META_APP_SECRET):raise HTTPException(403,'bad Meta signature')
    if not META_APP_SECRET and not _secret_ok(token):raise HTTPException(403,'bad webhook secret')
    payload=json.loads(raw or b'{}'); added=process(leads_from_payload('meta',payload),minimum_score=20)
    return {'ok':True,'added':len(added)}

@app.post('/webhooks/tiktok')
async def tiktok_webhook(request:Request,token:str|None=None):
    # TikTok signs official webhooks; deploy behind HTTPS and configure the platform webhook.
    # This endpoint also supports a private token in the callback URL as an additional deployment guard.
    if not _secret_ok(token):raise HTTPException(403,'bad webhook secret')
    payload=await request.json(); added=process(leads_from_payload('tiktok',payload),minimum_score=20)
    return {'ok':True,'added':len(added)}

@app.post('/webhooks/social-dm/{platform}')
async def generic_social_dm(platform:str,request:Request,token:str|None=None):
    if platform not in {'facebook','instagram','tiktok','nextdoor','other'}:raise HTTPException(400,'unsupported platform')
    if not _secret_ok(token):raise HTTPException(403,'bad webhook secret')
    payload=await request.json(); added=process(leads_from_payload(platform,payload),minimum_score=20)
    return {'ok':True,'added':len(added)}
