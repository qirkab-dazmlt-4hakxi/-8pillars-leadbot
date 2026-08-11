from pathlib import Path

def ask(label, default=""):
    v=input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip()
    return v or default

def main():
    template=Path('.env.example').read_text(encoding='utf-8').splitlines()
    current={}
    if Path('.env').exists():
        for line in Path('.env').read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);current[k]=v
    print('8 Pillars LeadBot configuration. Leave optional fields blank.')
    current['BRAVE_API_KEY']=ask('Brave Search API key',current.get('BRAVE_API_KEY',''))
    current['ALERT_EMAIL_TO']=ask('Email to receive HOT leads (optional)',current.get('ALERT_EMAIL_TO',''))
    current['IMAP_HOST']=ask('Lead inbox IMAP host (optional)',current.get('IMAP_HOST',''))
    if current['IMAP_HOST']:
        current['IMAP_USERNAME']=ask('IMAP username',current.get('IMAP_USERNAME',''))
        current['IMAP_PASSWORD']=ask('IMAP password/app password',current.get('IMAP_PASSWORD',''))
    current['NEXTDOOR_ACCESS_TOKEN']=ask('Approved Nextdoor OAuth token (optional)',current.get('NEXTDOOR_ACCESS_TOKEN',''))
    current['WEBHOOK_SHARED_SECRET']=ask('Private webhook URL token for social DMs (recommended)',current.get('WEBHOOK_SHARED_SECRET',''))
    current['META_VERIFY_TOKEN']=ask('Meta webhook verify token (optional)',current.get('META_VERIFY_TOKEN',''))
    current['META_APP_SECRET']=ask('Meta App Secret for webhook signature verification (optional)',current.get('META_APP_SECRET',''))
    current['DASHBOARD_USERNAME']=ask('Dashboard username (recommended)',current.get('DASHBOARD_USERNAME',''))
    if current['DASHBOARD_USERNAME']:
        current['DASHBOARD_PASSWORD']=ask('Dashboard password',current.get('DASHBOARD_PASSWORD',''))
    out=[]
    for line in template:
        if '=' in line and not line.lstrip().startswith('#'):
            k=line.split('=',1)[0]; out.append(f"{k}={current.get(k,line.split('=',1)[1])}")
        else: out.append(line)
    Path('.env').write_text('\n'.join(out)+'\n',encoding='utf-8')
    print('Saved .env. Run: python -m leadbot.main scan-now')
if __name__=='__main__':main()
