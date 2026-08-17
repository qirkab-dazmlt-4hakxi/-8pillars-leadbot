from __future__ import annotations

from datetime import timedelta

from leadbot_v2.goat.growth_intelligence import (
    stable_hash,
)

from .models import (
    CrawlTask,
    utcnow,
)


class CrawlPlanner:
    def __init__(
        self,
        *,
        normal_interval_hours=24,
        degraded_interval_hours=4,
    ) -> None:
        self.normal_interval_hours = int(
            normal_interval_hours
        )
        self.degraded_interval_hours = int(
            degraded_interval_hours
        )

    def schedule(
        self,
        *,
        url,
        seo_score,
        reason="scheduled audit",
        now=None,
    ):
        now = now or utcnow()

        if seo_score < 60:
            hours = (
                self.degraded_interval_hours
            )
            priority = 100

        elif seo_score < 80:
            hours = 12
            priority = 70

        else:
            hours = (
                self.normal_interval_hours
            )
            priority = 40

        due_at = (
            now
            + timedelta(
                hours=hours
            )
        )

        task_id = stable_hash(
            {
                "url": url,
                "reason": reason,
                "due": due_at,
            }
        )[:24]

        return CrawlTask(
            task_id=task_id,
            url=url,
            due_at=due_at,
            priority=priority,
            reason=reason,
        )
