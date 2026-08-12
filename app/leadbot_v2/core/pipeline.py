from __future__ import annotations

from dataclasses import dataclass

from leadbot_v2.core.models import LeadStage
from leadbot_v2.discovery.brave_adapter import from_legacy_lead
from leadbot_v2.enrichment import SignalExtractor
from leadbot_v2.enrichment.public_contact import PublicContactExtractor
from leadbot_v2.enrichment.reply_route import ReplyRouteResolver
from leadbot_v2.enrichment.reddit import RedditEnricher
from leadbot_v2.intelligence import (
    DomainReputationEngine,
    LeadRanker,
    RankingResult,
)
from leadbot_v2.qualification import EvidenceEngine


@dataclass
class PipelineResult:
    accepted: bool
    suppressed: bool
    reason: str
    record: object
    ranking: RankingResult | None = None


class LeadIntelligencePipeline:
    def __init__(self) -> None:
        self.domains = DomainReputationEngine()
        self.extractor = SignalExtractor()
        self.public_contact = PublicContactExtractor()
        self.reply_route = ReplyRouteResolver()
        self.reddit = RedditEnricher()
        self.qualifier = EvidenceEngine()
        self.ranker = LeadRanker()

    def process_record(self, lead) -> PipelineResult:
        domain = self.domains.inspect(
            url=lead.source_url,
            title=lead.title,
            text=lead.raw_text,
        )

        lead.scores.source_trust = domain.trust_score

        if domain.suppress:
            lead.stage = LeadStage.REJECTED
            lead.rejection_reason = domain.reason
            return PipelineResult(
                accepted=False,
                suppressed=True,
                reason=domain.reason,
                record=lead,
            )

        if "reddit.com" in lead.source_url.lower():
            self.reddit.enrich(lead)

        # First evaluate the content without granting a reply route.
        self.public_contact.extract(lead)
        self.extractor.extract(lead)

        preliminary = self.qualifier.summarize(lead)

        # A platform reply URL becomes actionable only after
        # requester intent, concrete scope, geography and seller checks pass.
        if (
            preliminary.buyer_intent >= 0.70
            and preliminary.concrete_scope >= 0.70
            and preliminary.location >= 0.70
            and preliminary.negatives < 0.80
        ):
            self.reply_route.resolve(lead)

            # Convert the newly proven contact route into contact evidence.
            self.extractor.extract(lead)

        if not self.qualifier.qualify(lead):
            lead.stage = LeadStage.REJECTED
            return PipelineResult(
                accepted=False,
                suppressed=False,
                reason=lead.rejection_reason or "qualification failed",
                record=lead,
            )

        lead.stage = LeadStage.QUALIFIED
        ranking = self.ranker.rank(lead)

        return PipelineResult(
            accepted=True,
            suppressed=False,
            reason=lead.qualification_reason or "qualified",
            record=lead,
            ranking=ranking,
        )

    def process_legacy(self, legacy_lead) -> PipelineResult:
        lead = from_legacy_lead(legacy_lead)

        domain = self.domains.inspect(
            url=lead.source_url,
            title=lead.title,
            text=lead.raw_text,
        )

        lead.scores.source_trust = domain.trust_score

        if domain.suppress:
            lead.stage = LeadStage.REJECTED
            lead.rejection_reason = domain.reason

            return PipelineResult(
                accepted=False,
                suppressed=True,
                reason=domain.reason,
                record=lead,
            )

        if "reddit.com" in lead.source_url.lower():
            self.reddit.enrich(lead)

        # First evaluate the content without granting a reply route.
        self.public_contact.extract(lead)
        self.extractor.extract(lead)

        preliminary = self.qualifier.summarize(lead)

        # A platform reply URL becomes actionable only after
        # requester intent, concrete scope, geography and seller checks pass.
        if (
            preliminary.buyer_intent >= 0.70
            and preliminary.concrete_scope >= 0.70
            and preliminary.location >= 0.70
            and preliminary.negatives < 0.80
        ):
            self.reply_route.resolve(lead)

            # Convert the newly proven contact route into contact evidence.
            self.extractor.extract(lead)

        qualified = self.qualifier.qualify(lead)

        if not qualified:
            lead.stage = LeadStage.REJECTED

            return PipelineResult(
                accepted=False,
                suppressed=False,
                reason=lead.rejection_reason or "qualification failed",
                record=lead,
            )

        lead.stage = LeadStage.QUALIFIED
        ranking = self.ranker.rank(lead)

        return PipelineResult(
            accepted=True,
            suppressed=False,
            reason=lead.qualification_reason or "qualified",
            record=lead,
            ranking=ranking,
        )
