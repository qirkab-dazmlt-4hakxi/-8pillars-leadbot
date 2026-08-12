from __future__ import annotations

from dataclasses import dataclass

from leadbot_v2.core.models import EvidenceType, LeadStage
from leadbot_v2.discovery.brave_adapter import from_legacy_lead
from leadbot_v2.enrichment import SignalExtractor
from leadbot_v2.enrichment.public_contact import PublicContactExtractor
from leadbot_v2.enrichment.reply_route import ReplyRouteResolver
from leadbot_v2.enrichment.reddit import RedditEnricher
from leadbot_v2.intelligence.geography import GeographicIntelligence
from leadbot_v2.intelligence.intent_fusion import IntentFusionEngine
from leadbot_v2.intelligence.intent_ensemble import IntentLabel
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
        self.geo = GeographicIntelligence()
        self.intent = IntentFusionEngine()

    _INTENT_BLOCKS = frozenset({
        IntentLabel.CONTRACTOR_AD,
        IntentLabel.DIRECTORY,
        IntentLabel.LEAD_RESELLER,
        IntentLabel.MARKETING_CONTENT,
        IntentLabel.DIY_INFORMATION,
        IntentLabel.CLEANUP_ONLY,
        IntentLabel.DEMOLITION_ONLY,
        IntentLabel.NON_CONCRETE,
        IntentLabel.STALE_REQUEST,
        IntentLabel.LOCATION_CONFLICT,
    })

    def _intent_gate(self, lead) -> tuple[bool, str]:
        text = f"{lead.title}\n{lead.raw_text}".strip()
        fusion = self.intent.analyze(text)
        assessment = fusion.assessment

        label = getattr(
            assessment.final_label,
            "value",
            str(assessment.final_label),
        )

        lead.metadata["intent"] = {
            "label": label,
            "buyer_probability": assessment.buyer_probability,
            "seller_probability": assessment.seller_probability,
            "ambiguity": assessment.ambiguity,
            "contradiction": assessment.contradiction,
            "quarantined": fusion.quarantined,
            "reason": fusion.reason,
        }

        if fusion.quarantined:
            lead.add_evidence(
                EvidenceType.NEGATIVE,
                f"intent quarantine: {fusion.reason}",
                max(0.80, assessment.ambiguity),
                source_url=lead.source_url,
            )
            return False, f"intent quarantine: {fusion.reason}"

        if (
            assessment.final_label in self._INTENT_BLOCKS
            or assessment.seller_probability >= 0.80
        ):
            confidence = max(
                assessment.seller_probability,
                0.90,
            )
            lead.add_evidence(
                EvidenceType.NEGATIVE,
                f"blocked intent: {label}",
                confidence,
                source_url=lead.source_url,
            )
            return False, f"blocked intent: {label}"

        if assessment.buyer_probability >= 0.70:
            lead.add_evidence(
                EvidenceType.BUYER_INTENT,
                f"intent fusion buyer classification: {label}",
                assessment.buyer_probability,
                source_url=lead.source_url,
            )

        return True, "intent passed"

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

        intent_ok, intent_reason = self._intent_gate(lead)
        if not intent_ok:
            lead.stage = LeadStage.REJECTED
            lead.rejection_reason = intent_reason
            return PipelineResult(
                accepted=False,
                suppressed=True,
                reason=intent_reason,
                record=lead,
            )

        if "reddit.com" in lead.source_url.lower():
            self.reddit.enrich(lead)

        # First evaluate the content without granting a reply route.
        self.public_contact.extract(lead)

        geo = self.geo.analyze(
            target_city=lead.city,
            title=lead.title,
            text=lead.raw_text,
            url=lead.source_url,
        )

        if geo.in_market:
            from leadbot_v2.core.models import EvidenceType
            lead.add_evidence(
                EvidenceType.LOCATION,
                geo.reason,
                geo.confidence,
                source_url=lead.source_url,
            )
        elif geo.conflict:
            from leadbot_v2.core.models import EvidenceType
            lead.add_evidence(
                EvidenceType.NEGATIVE,
                geo.reason,
                0.99,
                source_url=lead.source_url,
            )

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

        intent_ok, intent_reason = self._intent_gate(lead)
        if not intent_ok:
            lead.stage = LeadStage.REJECTED
            lead.rejection_reason = intent_reason
            return PipelineResult(
                accepted=False,
                suppressed=True,
                reason=intent_reason,
                record=lead,
            )

        if "reddit.com" in lead.source_url.lower():
            self.reddit.enrich(lead)

        # First evaluate the content without granting a reply route.
        self.public_contact.extract(lead)

        geo = self.geo.analyze(
            target_city=lead.city,
            title=lead.title,
            text=lead.raw_text,
            url=lead.source_url,
        )

        if geo.in_market:
            from leadbot_v2.core.models import EvidenceType
            lead.add_evidence(
                EvidenceType.LOCATION,
                geo.reason,
                geo.confidence,
                source_url=lead.source_url,
            )
        elif geo.conflict:
            from leadbot_v2.core.models import EvidenceType
            lead.add_evidence(
                EvidenceType.NEGATIVE,
                geo.reason,
                0.99,
                source_url=lead.source_url,
            )

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
