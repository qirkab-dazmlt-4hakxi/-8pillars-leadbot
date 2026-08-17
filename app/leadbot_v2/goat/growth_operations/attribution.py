from __future__ import annotations

from leadbot_v2.goat.growth_intelligence import (
    AttributionTouch,
    GrowthChannel,
)


CHANNEL_MAP = {
    "organic":
        GrowthChannel.ORGANIC_SEARCH,
    "organic_search":
        GrowthChannel.ORGANIC_SEARCH,
    "local":
        GrowthChannel.LOCAL_SEARCH,
    "local_search":
        GrowthChannel.LOCAL_SEARCH,
    "paid":
        GrowthChannel.PAID_SEARCH,
    "paid_search":
        GrowthChannel.PAID_SEARCH,
    "social":
        GrowthChannel.SOCIAL,
    "email":
        GrowthChannel.EMAIL,
    "referral":
        GrowthChannel.REFERRAL,
    "direct":
        GrowthChannel.DIRECT,
    "video":
        GrowthChannel.VIDEO,
}


class AttributionBridge:
    def normalize_touch(
        self,
        touch,
    ):
        channel = CHANNEL_MAP.get(
            touch.channel.lower()
        )

        if channel is None:
            raise ValueError(
                f"unknown external channel: "
                f"{touch.channel}"
            )

        return AttributionTouch(
            customer_id=(
                touch.customer_id
            ),
            timestamp=(
                touch.timestamp
            ),
            channel=channel,
            campaign_id=(
                touch.campaign_id
            ),
        )
