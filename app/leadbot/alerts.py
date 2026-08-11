import os,smtplib
from email.message import EmailMessage
from .config import HOT_ALERT_SCORE

def body(i,l):
    return f"""8 PILLARS HOT RESIDENTIAL CONCRETE LEAD - {l.score}/100
Lead ID: {i}\nTemperature: {l.temperature}\nCity: {l.city or 'Unknown'}\nNeighborhood: {l.neighborhood or 'Not shown'}\nPoster/contact: {l.poster_name or 'Not public'}\nPlatform username/ID: {l.platform_username or 'Not shown'}\nContactability: {l.contactability or 'Unknown'}\nContact route: {l.contact_route or l.source_url or 'Not shown'}\nScope: {l.scope or 'Residential concrete'}\nDimensions: {l.dimensions or 'Not stated'}\nApprox SF: {l.square_feet or 'Not stated'}\nUrgency: {l.urgency or 'Not stated'}\nPhone: {l.phone or 'Not public'}\nEmail: {l.email or 'Not public'}\nProject address: {l.project_address or 'Not published'}\nSource: {l.source}\nPost/link: {l.source_url or 'Email/import'}\nPosted: {l.published_at or 'Unknown'}\n\nEvidence:\n{(l.evidence or l.text)[:1500]}"""

def reminder_body(r):
    return f"""8 PILLARS 48-HOUR LEAD REMINDER
Lead ID: {r['id']}\nScore: {r.get('score',0)}/100 {r.get('temperature','')}\nCity: {r.get('city') or 'Unknown'}\nPoster/contact: {r.get('poster_name') or 'Not public'}\nPlatform username/ID: {r.get('platform_username') or 'Not shown'}\nContactability: {r.get('contactability') or 'Unknown'}\nContact route: {r.get('contact_route') or r.get('source_url') or 'Not shown'}\nScope: {r.get('scope') or 'Residential concrete'}\nPhone: {r.get('phone') or 'Not public'}\nEmail: {r.get('email') or 'Not public'}\nProject address: {r.get('project_address') or 'Not published'}\nOriginal post: {r.get('source_url') or 'Imported lead'}\n\nThis lead has not been clicked/reviewed in LeadBot. Reminder #{int(r.get('reminder_count') or 0)+1}."""

def _send(subject,b):
    sent=False;host=os.getenv("SMTP_HOST");to=os.getenv("ALERT_EMAIL_TO")
    if host and to:
        m=EmailMessage();m["Subject"]=subject;m["From"]=os.getenv("ALERT_EMAIL_FROM") or os.getenv("SMTP_USERNAME");m["To"]=to;m.set_content(b)
        with smtplib.SMTP(host,int(os.getenv("SMTP_PORT","587")),timeout=20) as s:s.starttls();s.login(os.getenv("SMTP_USERNAME"),os.getenv("SMTP_PASSWORD"));s.send_message(m)
        sent=True
    if os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("ALERT_SMS_TO") and os.getenv("TWILIO_FROM"):
        from twilio.rest import Client
        Client(os.getenv("TWILIO_ACCOUNT_SID"),os.getenv("TWILIO_AUTH_TOKEN")).messages.create(body=b[:1500],from_=os.getenv("TWILIO_FROM"),to=os.getenv("ALERT_SMS_TO"));sent=True
    return sent

def alert(i,l):
    if l.score<HOT_ALERT_SCORE:return False
    return _send(f"HOT concrete lead {l.score}: {l.city or ''} - {l.scope or ''}",body(i,l))

def reminder(r):
    return _send(f"48-hour concrete lead reminder: {r.get('city') or ''} - {r.get('scope') or ''}",reminder_body(r))
