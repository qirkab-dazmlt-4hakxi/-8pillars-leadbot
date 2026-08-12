from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse


class DomainClass(str, Enum):
    UNKNOWN = "unknown"
    REQUESTER = "requester"
    COMMUNITY = "community"
    CONTRACTOR = "contractor"
    DIRECTORY = "directory"
    MARKETPLACE = "marketplace"
    NEWS = "news"
    GOVERNMENT = "government"
    BLOCKED = "blocked"


SELLER_PHRASES = {
    "free estimate",
    "request a quote",
    "get a quote",
    "our services",
    "call us today",
    "contact us today",
    "licensed and insured",
    "we specialize",
    "we provide",
    "concrete contractor",
    "concrete company",
}


DIRECTORY_DOMAINS = {
    "angi.com",
    "homeadvisor.com",
    "thumbtack.com",
    "yelp.com",
    "yellowpages.com",
    "houzz.com",
}


COMMUNITY_DOMAINS = {
    "reddit.com",
    "facebook.com",
    "nextdoor.com",
}


def normalize_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().strip()

    if host.startswith("www."):
        host = host[4:]

    return host


def root_domain(domain: str) -> str:
    parts = domain.split(".")

    if len(parts) <= 2:
        return domain

    return ".".join(parts[-2:])


@dataclass
class DomainStats:
    domain: str
    observations: int = 0
    requester_hits: int = 0
    qualified_hits: int = 0
    actionable_hits: int = 0
    seller_hits: int = 0
    directory_hits: int = 0
    junk_hits: int = 0
    wins: int = 0
    revenue: float = 0.0
    manual_class: DomainClass | None = None

    def record(
        self,
        *,
        requester: bool = False,
        qualified: bool = False,
        actionable: bool = False,
        seller: bool = False,
        directory: bool = False,
        junk: bool = False,
        won: bool = False,
        revenue: float = 0.0,
    ) -> None:
        self.observations += 1
        self.requester_hits += int(requester)
        self.qualified_hits += int(qualified)
        self.actionable_hits += int(actionable)
        self.seller_hits += int(seller)
        self.directory_hits += int(directory)
        self.junk_hits += int(junk)
        self.wins += int(won)
        self.revenue += max(0.0, revenue)

    @property
    def requester_rate(self) -> float:
        if not self.observations:
            return 0.0
        return self.requester_hits / self.observations

    @property
    def seller_rate(self) -> float:
        if not self.observations:
            return 0.0
        return (
            self.seller_hits
            + self.directory_hits
            + self.junk_hits
        ) / self.observations


@dataclass
class DomainDecision:
    domain: str
    classification: DomainClass
    trust_score: float
    suppress: bool
    reason: str


@dataclass
class DomainReputationEngine:
    stats: dict[str, DomainStats] = field(default_factory=dict)

    def get_stats(self, domain: str) -> DomainStats:
        domain = root_domain(domain)

        if domain not in self.stats:
            self.stats[domain] = DomainStats(domain=domain)

        return self.stats[domain]

    def inspect(
        self,
        *,
        url: str,
        title: str = "",
        text: str = "",
    ) -> DomainDecision:
        domain = root_domain(normalize_domain(url))
        stats = self.get_stats(domain)
        haystack = f"{title}\n{text}".lower()

        if stats.manual_class is not None:
            cls = stats.manual_class
            return DomainDecision(
                domain=domain,
                classification=cls,
                trust_score=0.05 if cls in {
                    DomainClass.CONTRACTOR,
                    DomainClass.DIRECTORY,
                    DomainClass.BLOCKED,
                } else 0.85,
                suppress=cls in {
                    DomainClass.CONTRACTOR,
                    DomainClass.DIRECTORY,
                    DomainClass.BLOCKED,
                },
                reason="manual classification",
            )

        if domain in DIRECTORY_DOMAINS:
            return DomainDecision(
                domain=domain,
                classification=DomainClass.DIRECTORY,
                trust_score=0.02,
                suppress=True,
                reason="known contractor directory",
            )

        if domain in COMMUNITY_DOMAINS:
            return DomainDecision(
                domain=domain,
                classification=DomainClass.COMMUNITY,
                trust_score=0.80,
                suppress=False,
                reason="community/requester-capable source",
            )

        seller_hits = sum(
            1 for phrase in SELLER_PHRASES
            if phrase in haystack
        )

        if seller_hits >= 2:
            return DomainDecision(
                domain=domain,
                classification=DomainClass.CONTRACTOR,
                trust_score=0.05,
                suppress=True,
                reason=f"seller fingerprint: {seller_hits} hits",
            )

        if stats.observations >= 5 and stats.seller_rate >= 0.80:
            return DomainDecision(
                domain=domain,
                classification=DomainClass.CONTRACTOR,
                trust_score=0.05,
                suppress=True,
                reason="historically high seller/junk rate",
            )

        if stats.observations >= 5 and stats.requester_rate >= 0.60:
            return DomainDecision(
                domain=domain,
                classification=DomainClass.REQUESTER,
                trust_score=0.90,
                suppress=False,
                reason="historically strong requester source",
            )

        return DomainDecision(
            domain=domain,
            classification=DomainClass.UNKNOWN,
            trust_score=0.50,
            suppress=False,
            reason="insufficient evidence to suppress",
        )

    def mark_domain(
        self,
        domain: str,
        classification: DomainClass,
    ) -> None:
        self.get_stats(domain).manual_class = classification
