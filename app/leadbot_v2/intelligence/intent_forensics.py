from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class IntentClass(str, Enum):
    HOMEOWNER_BUYER = "homeowner_buyer"
    COMMERCIAL_BUYER = "commercial_buyer"
    GC_SUBCONTRACT = "gc_subcontract"
    RECOMMENDATION = "recommendation"
    CONTRACTOR_AD = "contractor_ad"
    DIY_INFORMATION = "diy_information"
    CLEANUP_GENERAL = "cleanup_general"
    UNKNOWN = "unknown"


@dataclass
class IntentDecision:
    classification: IntentClass
    confidence: float
    buyer: bool
    seller: bool
    reason: str


BUYER_PHRASES = [
    r"\blooking for (someone|a contractor|concrete)\b",
    r"\bneed (someone|a contractor|concrete|a quote|an estimate)\b",
    r"\bwho can\b",
    r"\banyone know\b",
    r"\brecommend (someone|a contractor)\b",
    r"\bgetting estimates\b",
    r"\bneed pricing\b",
]

TRADE_BUYER_PHRASES = [
    "concrete sub needed",
    "concrete subcontractor needed",
    "concrete crew needed",
    "looking for concrete subs",
    "need concrete pricing",
    "bid this concrete",
    "send pricing",
]

SELLER_PHRASES = [
    "free estimate",
    "call us today",
    "contact us today",
    "our services",
    "we provide",
    "we specialize",
    "licensed and insured",
    "serving homeowners",
    "skilled trade services",
    "household services",
]

DIY_PHRASES = [
    "how do i",
    "can i pour",
    "should i use",
    "what mix",
    "how thick",
    "how much rebar",
    "diy",
]

CLEANUP_PHRASES = [
    "trash removal",
    "junk removal",
    "haul away",
    "clean up",
    "cleanup",
    "yard cleanup",
]
