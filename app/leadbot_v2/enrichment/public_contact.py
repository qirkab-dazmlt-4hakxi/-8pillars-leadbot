from __future__ import annotations

import re
from urllib.parse import urlparse

from leadbot_v2.core.models import LeadIntelligenceRecord


EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.I,
)

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?"
    r"(?:\(?\d{3}\)?[-.\s]?)"
    r"\d{3}[-.\s]?\d{4}(?!\d)"
)

SOCIAL_HOSTS = {
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "nextdoor.com",
}


class PublicContactExtractor:
    def extract(
        self,
        lead: LeadIntelligenceRecord,
    ) -> LeadIntelligenceRecord:
        text = f"{lead.title}\n{lead.raw_text}"

        for email in sorted(set(EMAIL_RE.findall(text))):
            lead.add_contact(
                channel="email",
                value=email,
                verified_public=True,
                confidence=0.96,
                source_url=lead.source_url,
            )

        for phone in sorted(set(PHONE_RE.findall(text))):
            lead.add_contact(
                channel="phone",
                value=phone,
                verified_public=True,
                confidence=0.96,
                source_url=lead.source_url,
            )

        host = urlparse(lead.source_url).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        if host in SOCIAL_HOSTS and lead.author_profile_url:
            lead.add_contact(
                channel="profile",
                value=lead.author_profile_url,
                verified_public=True,
                confidence=0.90,
                source_url=lead.source_url,
            )

        return lead
