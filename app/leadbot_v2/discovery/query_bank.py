from __future__ import annotations

from leadbot_v2.discovery.adaptive import AdaptiveQuery


def build_default_query_bank():
    return [

        AdaptiveQuery(
            query_id="reddit_local_concrete",
            source="reddit",
            template='site:reddit.com "{city}" Texas concrete driveway',
            prior_quality=0.98,
        ),

        AdaptiveQuery(
            query_id="reddit_recommendation",
            source="reddit",
            template='site:reddit.com "{city}" "concrete contractor" recommendation',
            prior_quality=0.97,
        ),

        AdaptiveQuery(
            query_id="reddit_need_someone",
            source="reddit",
            template='site:reddit.com "{city}" "looking for" concrete',
            prior_quality=0.96,
        ),

        AdaptiveQuery(
            query_id="facebook_local",
            source="facebook",
            template='site:facebook.com/groups "{city}" Texas concrete driveway',
            prior_quality=0.90,
        ),

        AdaptiveQuery(
            query_id="buyer_recommend",
            source="web",
            template='"{city}" Texas "recommend a concrete contractor"',
            prior_quality=0.92,
        ),

        AdaptiveQuery(
            query_id="buyer_need",
            source="web",
            template='"{city}" Texas "need a concrete contractor"',
            prior_quality=0.91,
        ),

        AdaptiveQuery(
            query_id="driveway_request",
            source="web",
            template='"{city}" Texas "looking for someone" driveway concrete',
            prior_quality=0.93,
        ),

        AdaptiveQuery(
            query_id="contractor_problem",
            source="web",
            template='"{city}" Texas concrete "contractor backed out"',
            prior_quality=0.95,
        ),

        AdaptiveQuery(
            query_id="commercial_concrete",
            source="web",
            template='"{city}" Texas "concrete subcontractor needed"',
            prior_quality=0.88,
        ),
    ]
