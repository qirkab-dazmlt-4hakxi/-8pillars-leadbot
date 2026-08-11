from __future__ import annotations
import hashlib,hmac,json,os
from .models import Lead
from .utils import now_iso

TEXT_KEYS={'text','message','body','description','caption','content'}
NAME_KEYS={'name','display_name','author_name','sender_name','username','user_name','nickname'}
ID_KEYS={'sender_id','from_id','user_id','open_id','psid','sender'}
URL_KEYS={'url','profile_url','web_url','post_url','video_url'}

def _walk(obj,path=''):
    if isinstance(obj,dict):
        for k,v in obj.items():
            yield path+'/'+str(k),k,v
            yield from _walk(v,path+'/'+str(k))
    elif isinstance(obj,list):
        for i,v in enumerate(obj):yield from _walk(v,path+f'/{i}')

def _first(payload,keys):
    for _,k,v in _walk(payload):
        if k.lower() in keys and isinstance(v,(str,int,float)) and str(v).strip():return str(v).strip()
    return None

def _all_text(payload):
    vals=[]
    for _,k,v in _walk(payload):
        if k.lower() in TEXT_KEYS and isinstance(v,str) and v.strip():vals.append(v.strip())
    # Preserve useful context but avoid dumping arbitrary tokens/metadata into lead text.
    seen=[]
    for v in vals:
        if v not in seen:seen.append(v)
    return '\n'.join(seen)[:12000]

def _sender_id(payload):
    # Common Meta Messenger shape: messaging[].sender.id
    try:
        for entry in payload.get('entry',[]):
            for m in entry.get('messaging',[]):
                if isinstance(m.get('sender'),dict) and m['sender'].get('id'):return str(m['sender']['id'])
    except Exception:pass
    v=_first(payload,ID_KEYS)
    if v and v.startswith('{'):return None
    return v

def leads_from_payload(platform,payload,source_url=''):
    text=_all_text(payload)
    if not text:return []
    name=_first(payload,NAME_KEYS); sid=_sender_id(payload); url=_first(payload,URL_KEYS) or source_url
    title=f'{platform.title()} inbound business message' + (f' from {name}' if name else '')
    return [Lead(source=f'{platform}-dm',source_url=url or '',title=title,text=text,discovered_at=now_iso(),external_id=_first(payload,{'message_id','mid','id','event_id'}),poster_name=name,platform_username=name or sid,contact_channel=f'{platform}-dm',contact_route=f'{platform} business inbox',inbound_message=True)]

def verify_meta_signature(raw,header,secret):
    if not secret:return True
    if not header or not header.startswith('sha256='):return False
    expected='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,header)
