from __future__ import annotations

import os
import requests
from time import monotonic

from leadbot_v2.core.source_health import SourceCircuitBreaker
from leadbot_v2.core.health_store import HealthStore

from leadbot_v2.core import LeadIntelligenceRecord
from leadbot_v2.discovery.adaptive import AdaptiveQueryEngine
from leadbot_v2.discovery.query_bank import build_default_query_bank
from leadbot_v2.discovery.contactable_queries import build_contactable_query_bank

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

NEGATIVES = (
    " -angi -yelp -homeadvisor -thumbtack "
    '-"free estimate" -"our services" '
    '-"concrete company"'
)


class BraveV2Discovery:
    def __init__(self) -> None:
        queries = (
            build_default_query_bank()
            + build_contactable_query_bank()
        )

        self.engine = AdaptiveQueryEngine(queries)
        self.breaker = SourceCircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=60,
        )

        self.health_store = HealthStore()
        self.health_store.load_into(self.breaker)

    def search(
        self,
        city: str,
        budget: int = 3,
    ) -> list[LeadIntelligenceRecord]:
        key = os.getenv("BRAVE_API_KEY")

        if not key:
            raise RuntimeError("BRAVE_API_KEY is missing")

        ranked = self.engine.rank()

        contactable_ids = {
            "classified_concrete",
            "facebook_request",
            "nextdoor_request",
            "buyer_request",
            "driveway_buyer",
            "commercial_concrete_need",
        }

        contactable = [
            q for q in ranked
            if q.query_id in contactable_ids
        ]

        general = [
            q for q in ranked
            if q.query_id not in contactable_ids
        ]

        selected = []

        # Portfolio allocation:
        # preserve high-yield discovery while preventing
        # contactable-buyer lanes from being starved.
        if budget >= 2 and contactable:
            selected.append(contactable[0])

        for q in general:
            if len(selected) >= budget:
                break
            selected.append(q)

        for q in contactable[1:]:
            if len(selected) >= budget:
                break
            selected.append(q)

        results: list[LeadIntelligenceRecord] = []

        for query in selected:
            q = query.template.format(city=city)

            if query.source == "web":
                q += NEGATIVES

            source_name = f"brave:{query.source}"

            if not self.breaker.allow_request(source_name):
                continue

            started = monotonic()

            try:
                response = requests.get(
                    ENDPOINT,
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": key,
                    },
                    params={
                        "q": q,
                        "country": "US",
                        "search_lang": "en",
                        "ui_lang": "en-US",
                        "count": 20,
                        "safesearch": "moderate",
                        "text_decorations": False,
                        "extra_snippets": True,
                    },
                    timeout=20,
                )

                response.raise_for_status()

                latency_ms = (
                    monotonic() - started
                ) * 1000.0

                self.breaker.record_success(
                    source_name,
                    latency_ms=latency_ms,
                )
                self.health_store.save(self.breaker)

            except Exception as exc:
                self.breaker.record_failure(
                    source_name,
                    error=exc,
                )
                self.health_store.save(self.breaker)
                continue

            web = response.json().get("web") or {}

            for item in web.get("results") or []:
                text_parts = [
                    item.get("description") or "",
                    *(item.get("extra_snippets") or []),
                ]

                record = LeadIntelligenceRecord(
                    source=query.source,
                    source_url=item.get("url") or "",
                    source_query=query.query_id,
                    title=item.get("title") or "",
                    raw_text="\n".join(
                        x for x in text_parts if x
                    ),
                    city=city,
                )

                record.build_fingerprint()
                results.append(record)

        return results
