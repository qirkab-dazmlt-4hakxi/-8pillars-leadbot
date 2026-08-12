from __future__ import annotations

from urllib.parse import urlparse

from leadbot_v2.core.models import LeadIntelligenceRecord


SUPPORTED_REPLY_HOSTS = {
    "craigslist.org",
    "facebook.com",
    "nextdoor.com",
    "reddit.com",
}


class ReplyRouteResolver:
    def resolve(
        self,
        lead: LeadIntelligenceRecord,
    ) -> LeadIntelligenceRecord:

        host = urlparse(lead.source_url).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        root = ".".join(host.split(".")[-2:])

        if root not in SUPPORTED_REPLY_HOSTS:
            return lead

        # Reddit still requires author/profile resolution
        # before we count it as actionable.
        if root == "reddit.com":
            if lead.author_profile_url:
                lead.add_contact(
                    channel="profile",
                    value=lead.author_profile_url,
                    verified_public=True,
                    confidence=0.90,
                    source_url=lead.source_url,
                )
            return lead

        # For supported public requester pages, the post URL
        # itself can be a direct reply/message route.
        lead.add_contact(
            channel="profile",
            value=lead.source_url,
            verified_public=True,
            confidence=0.82,
            source_url=lead.source_url,
        )

        lead.metadata["reply_route"] = "public_post"

        return lead
