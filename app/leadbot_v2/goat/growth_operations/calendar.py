from __future__ import annotations

from datetime import timedelta

from leadbot_v2.goat.growth_intelligence import (
    stable_hash,
)

from .models import (
    ContentCalendarItem,
    utcnow,
)


class ContentCalendar:
    def __init__(self) -> None:
        self._items = {}

    def schedule(
        self,
        *,
        title,
        channel,
        scheduled_for,
        brief_id=None,
        campaign_id=None,
    ):
        item_id = stable_hash(
            {
                "title": title,
                "channel": channel,
                "scheduled_for": scheduled_for,
                "brief_id": brief_id,
                "campaign_id": campaign_id,
            }
        )[:24]

        item = ContentCalendarItem(
            item_id=item_id,
            title=title,
            channel=channel,
            scheduled_for=scheduled_for,
            brief_id=brief_id,
            campaign_id=campaign_id,
        )

        self._items[
            item_id
        ] = item

        return item

    def due(
        self,
        *,
        now=None,
        horizon_hours=1,
    ):
        now = now or utcnow()

        cutoff = (
            now
            + timedelta(
                hours=horizon_hours
            )
        )

        return tuple(
            sorted(
                (
                    item
                    for item
                    in self._items.values()
                    if (
                        now
                        <= item.scheduled_for
                        <= cutoff
                    )
                ),
                key=lambda item: (
                    item.scheduled_for,
                    item.item_id,
                ),
            )
        )
