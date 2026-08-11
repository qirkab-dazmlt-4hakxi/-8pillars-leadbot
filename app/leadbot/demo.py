from .models import Lead
from .utils import now_iso

def sample_leads():
    return [
        Lead(source="facebook-public-index",source_url="https://example.com/post/1",title="Need concrete contractor ASAP in Celina",text="Posted by John Example - Need a concrete contractor ASAP for my driveway extension in Celina. 20x20 plus 1x35, salt finish. Text 469-555-0188. Project: 123 Demo Trail, Celina TX 75009",discovered_at=now_iso(),published_at="1 hour ago",contact_channel="source-post"),
        Lead(source="marketplace-email",source_url="",title="New lead: Patio extension in Little Elm",text="Customer needs a 410 sqft concrete patio extension in Little Elm this week. Email homeowner@example.com or call 972-555-0133.",discovered_at=now_iso(),published_at=now_iso(),contact_channel="email"),
        Lead(source="web",source_url="https://example.com/ad",title="Best concrete company serving DFW",text="We offer concrete services, free estimates, licensed and insured, call us today for patios and driveways.",discovered_at=now_iso(),published_at="2 hours ago"),
    ]
