from __future__ import annotations

from dataclasses import dataclass, field
from math import log, sqrt
from random import random


@dataclass
class QueryPerformance:
    impressions: int = 0
    qualified: int = 0
    actionable: int = 0
    junk: int = 0
    competitors: int = 0
    revenue: float = 0.0


@dataclass
class AdaptiveQuery:
    query_id: str
    source: str
    template: str
    prior_quality: float = 0.50
    exploration_weight: float = 0.20
    enabled: bool = True
    performance: QueryPerformance = field(
        default_factory=QueryPerformance
    )


class AdaptiveQueryEngine:
    def __init__(self, queries):
        self.queries = list(queries)

    def _score(self, q):
        p = q.performance

        if p.impressions == 0:
            return q.prior_quality + 1.0

        positive = (
            p.qualified * 1.5
            + p.actionable * 2.5
            + min(p.revenue / 5000.0, 5.0)
        )

        negative = (
            p.junk * 1.5
            + p.competitors * 2.5
        )

        quality = (positive - negative) / max(
            p.impressions,
            1,
        )

        exploration = sqrt(
            2 * log(max(p.impressions + 2, 2))
            / p.impressions
        )

        return quality + q.exploration_weight * exploration

    def rank(self):
        active = [q for q in self.queries if q.enabled]
        return sorted(
            active,
            key=self._score,
            reverse=True,
        )

    def choose(self, budget, exploration_chance=0.10):
        ranked = self.rank()

        if budget <= 0:
            return []

        if random() < exploration_chance:
            ranked = list(reversed(ranked))

        return ranked[:budget]
