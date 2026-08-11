from __future__ import annotations
import re,requests
from urllib.parse import urlparse
from .config import SOCIAL_DOMAINS,DEEP_FETCH_ENABLED,DEEP_FETCH_TIMEOUT_SECONDS

UA='Mozilla/5.0 (compatible; 8PillarsLeadBot/3.0; +https://8pillars.local)'
TAG_RE=re.compile(r'<[^>]+>')
SPACE_RE=re.compile(r'\s+')

def _host(url):
    try:return (urlparse(url).hostname or '').lower()
    except Exception:return ''

def allowed(url):
    if not DEEP_FETCH_ENABLED or not url or not url.startswith(('http://','https://')):return False
    h=_host(url)
    return h not in SOCIAL_DOMAINS and not any(h.endswith('.'+d) for d in SOCIAL_DOMAINS)

def fetch_public_text(url):
    """Best-effort enrichment for ordinary public web pages only; social networks use official APIs/search snippets."""
    if not allowed(url):return ''
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'},timeout=DEEP_FETCH_TIMEOUT_SECONDS,allow_redirects=True)
        if not r.ok or 'text/html' not in (r.headers.get('content-type') or '').lower():return ''
        txt=r.text[:600000]
        # Preserve useful mailto/tel values before stripping markup.
        extras=' '.join(re.findall(r'(?:mailto:|tel:)[^\"\'<>\s]+',txt,re.I))
        txt=re.sub(r'(?is)<script.*?</script>|<style.*?</style>',' ',txt)
        txt=TAG_RE.sub(' ',txt)
        return SPACE_RE.sub(' ',txt+' '+extras).strip()[:12000]
    except requests.RequestException:return ''
