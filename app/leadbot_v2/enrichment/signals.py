from __future__ import annotations

import re

from leadbot_v2.core.models import (
    EvidenceType,
    LeadIntelligenceRecord,
)


BUYER_PATTERNS = [
    r"\bneed(?:ing)?\s+(?:a|an|someone|somebody)?",
    r"\blooking\s+for\b",
    r"\brecommend(?:ation|ations)?\b",
    r"\bwho\s+can\b",
    r"\banyone\s+know\b",
    r"\bneed\s+(?:a\s+)?quote\b",
    r"\bneed\s+(?:an\s+)?estimate\b",
    r"\bgetting\s+estimates\b",
]


CONCRETE_TERMS = [
    "concrete",
    "driveway",
    "patio",
    "slab",
    "foundation",
    "sidewalk",
    "flatwork",
    "pool deck",
    "approach",
    "curb",
]


URGENCY_TERMS = [
    "asap",
    "urgent",
    "this week",
    "ready to pour",
    "ready for concrete",
    "contractor backed out",
    "contractor ghosted",
    "need another contractor",
]


SELLER_TERMS = [
    "skilled trade services",
    "household services",
    "farm & garden services",
    "concrete services",
    "paver services",
    "installation services",
    "we offer",
    "our company",
    "specialists",
    "free estimate",
"free estimate",
    "request a quote",
    "call us today",
    "our services",
    "we provide",
    "we specialize",
    "licensed and insured",
    "serving homeowners",
]


class SignalExtractor:
    def extract(
        self,
        lead: LeadIntelligenceRecord,
    ) -> LeadIntelligenceRecord:
        text = f"{lead.title}\n{lead.raw_text}".lower()

        buyer_hits = sum(
            1 for pattern in BUYER_PATTERNS
            if re.search(pattern, text)
        )

        concrete_hits = sum(
            1 for term in CONCRETE_TERMS
            if term in text
        )

        urgency_hits = sum(
            1 for term in URGENCY_TERMS
            if term in text
        )

        seller_hits = sum(
            1 for term in SELLER_TERMS
            if term in text
        )

        if buyer_hits:
            confidence = min(
                0.70 + buyer_hits * 0.08,
                0.99,
            )
            lead.add_evidence(
                EvidenceType.BUYER_INTENT,
                f"{buyer_hits} buyer-intent signals detected",
                confidence,
            )

        if concrete_hits:
            confidence = min(
                0.72 + concrete_hits * 0.06,
                0.99,
            )
            lead.add_evidence(
                EvidenceType.CONCRETE_SCOPE,
                f"{concrete_hits} concrete-scope signals detected",
                confidence,
            )

        if urgency_hits:
            confidence = min(
                0.72 + urgency_hits * 0.08,
                0.99,
            )
            lead.add_evidence(
                EvidenceType.URGENCY,
                f"{urgency_hits} urgency signals detected",
                confidence,
            )

        if seller_hits:
            confidence = min(
                0.70 + seller_hits * 0.08,
                0.99,
            )
            lead.add_evidence(
                EvidenceType.NEGATIVE,
                f"{seller_hits} seller/marketing signals detected",
                confidence,
            )

        if lead.city and lead.city.lower() in text:
            lead.add_evidence(
                EvidenceType.LOCATION,
                f"city matched in text: {lead.city}",
                0.95,
            )

        if lead.contacts:
            best = max(
                (
                    c.confidence
                    for c in lead.contacts
                    if c.verified_public
                ),
                default=0.0,
            )

            if best:
                lead.add_evidence(
                    EvidenceType.CONTACT,
                    "verified public contact route detected",
                    best,
                )

        return lead
