from __future__ import annotations

from leadbot_v2.discovery.adaptive import AdaptiveQuery


def build_contactable_query_bank():
    return [

        AdaptiveQuery(
            query_id="classified_concrete",
            source="classified",
            template=(
                'site:dallas.craigslist.org '
                '"{city}" '
                '(concrete OR driveway OR patio OR slab) '
                '("need someone" OR "looking for someone" OR '
                '"contractor needed" OR "help wanted" OR "wanted")'
            ),
            prior_quality=0.99,
        ),

        AdaptiveQuery(
            query_id="facebook_request",
            source="facebook",
            template=(
                'site:facebook.com/groups '
                '"{city}" '
                '("looking for" OR "recommend" OR "need") '
                '(concrete OR driveway OR patio)'
            ),
            prior_quality=0.97,
        ),

        AdaptiveQuery(
            query_id="nextdoor_request",
            source="nextdoor",
            template=(
                'site:nextdoor.com '
                '"{city}" '
                '("looking for" OR "recommend") '
                '(concrete OR driveway OR patio)'
            ),
            prior_quality=0.96,
        ),

        AdaptiveQuery(
            query_id="buyer_request",
            source="web",
            template=(
                '"{city}" Texas '
                '("looking for concrete contractor" OR '
                '"need concrete contractor" OR '
                '"concrete contractor needed")'
            ),
            prior_quality=0.94,
        ),

        AdaptiveQuery(
            query_id="driveway_buyer",
            source="web",
            template=(
                '"{city}" Texas '
                '("looking for someone" OR "need someone") '
                '(driveway OR patio) concrete'
            ),
            prior_quality=0.93,
        ),

        AdaptiveQuery(
            query_id="commercial_concrete_need",
            source="web",
            template=(
                '"{city}" Texas '
                '("concrete subcontractor needed" OR '
                '"concrete crew needed" OR '
                '"concrete pricing needed")'
            ),
            prior_quality=0.92,
        ),
    ]
