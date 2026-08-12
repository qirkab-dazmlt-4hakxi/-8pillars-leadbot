from __future__ import annotations

from datetime import datetime, timezone
import requests

from leadbot_v2.enrichment.reddit_auth import load_reddit_auth
from leadbot_v2.enrichment.reddit_oauth import RedditOAuthClient

from leadbot_v2.core.models import (
    EvidenceType,
    LeadIntelligenceRecord,
)


class RedditEnricher:
    def enrich(
        self,
        lead: LeadIntelligenceRecord,
    ) -> LeadIntelligenceRecord:

        if "reddit.com" not in lead.source_url.lower():
            return lead

        auth = load_reddit_auth()
        oauth = RedditOAuthClient()

        if oauth.configured:
            from urllib.parse import urlparse

            path = urlparse(lead.source_url).path.rstrip("/") + ".json"
            data = oauth.get_json(path)

            if data is not None:
                try:
                    post = data[0]["data"]["children"][0]["data"]
                except (KeyError, IndexError, TypeError):
                    lead.metadata["reddit_parse_failed"] = True
                    return lead

                author = post.get("author")

                if author and author != "[deleted]":
                    lead.author_username = author
                    lead.author_profile_url = (
                        f"https://www.reddit.com/user/{author}/"
                    )

                    lead.add_contact(
                        channel="profile",
                        value=lead.author_profile_url,
                        verified_public=True,
                        confidence=0.94,
                        source_url=lead.source_url,
                    )

                body = post.get("selftext") or ""

                if body:
                    lead.raw_text = (
                        f"{lead.raw_text}\n{body}"
                    ).strip()

                created = post.get("created_utc")

                if created:
                    lead.published_at = datetime.fromtimestamp(
                        float(created),
                        tz=timezone.utc,
                    )

                lead.metadata["subreddit"] = post.get("subreddit")
                lead.metadata["reddit_score"] = post.get("score")
                lead.metadata["reddit_num_comments"] = post.get(
                    "num_comments"
                )
                lead.metadata["reddit_enrichment"] = "oauth"

                return lead

        url = lead.source_url.rstrip("/") + ".json?raw_json=1"

        response = requests.get(
            url,
            headers={
                "User-Agent": auth.user_agent,
            },
            timeout=12,
        )

        if response.status_code != 200:
            lead.metadata["reddit_status"] = response.status_code
            lead.metadata["reddit_enrichment"] = "blocked_unauthenticated"
            lead.tags.add("needs_reddit_oauth")
            return lead

        data = response.json()

        try:
            post = data[0]["data"]["children"][0]["data"]
        except (KeyError, IndexError, TypeError):
            lead.metadata["reddit_parse_failed"] = True
            return lead

        author = post.get("author")

        if author and author != "[deleted]":
            lead.author_username = author
            lead.author_profile_url = (
                f"https://www.reddit.com/user/{author}/"
            )

            lead.add_contact(
                channel="profile",
                value=lead.author_profile_url,
                verified_public=True,
                confidence=0.94,
                source_url=lead.source_url,
            )

        body = post.get("selftext") or ""

        if body:
            lead.raw_text = (
                f"{lead.raw_text}\n{body}"
            ).strip()

        created = post.get("created_utc")

        if created:
            lead.published_at = datetime.fromtimestamp(
                float(created),
                tz=timezone.utc,
            )

        lead.metadata["subreddit"] = post.get("subreddit")
        lead.metadata["reddit_score"] = post.get("score")
        lead.metadata["reddit_num_comments"] = post.get(
            "num_comments"
        )

        return lead
