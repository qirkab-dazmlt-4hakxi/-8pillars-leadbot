import re
from .config import CONCRETE_TERMS, AD_TERMS

BUYER_PATTERNS = [
    r"\bneed(?:ing)?\s+(?:a\s+|an\s+|someone\s+|somebody\s+)?(?:concrete|contractor|crew|sub)",
    r"\blooking\s+for\s+(?:a\s+|an\s+|someone\s+|somebody\s+)?",
    r"\bseeking\s+(?:a\s+|an\s+)?(?:concrete|contractor|crew|sub)",
    r"\bwho\s+(?:can|does|would)\b",
    r"\banyone\s+(?:know|recommend|have)\b",
    r"\brecommend(?:ation|ations)?\s+(?:for|on)\b",
    r"\bneed\s+(?:a\s+)?quote\b",
    r"\bneed\s+(?:an\s+)?estimate\b",
    r"\bgetting\s+(?:a\s+)?quote\b",
    r"\brequesting\s+(?:a\s+)?quote\b",
    r"\brequesting\s+(?:an\s+)?estimate\b",
    r"\bcontractor\s+needed\b",
    r"\bcrew\s+needed\b",
    r"\bsub(?:contractor)?\s+needed\b",
    r"\bconcrete\s+(?:guy|company|contractor|crew|sub)\s+needed\b",
    r"\bready\s+to\s+(?:pour|start|hire)\b",
    r"\btrying\s+to\s+(?:get|find|hire)\b",
    r"\bcan\s+someone\b",
]

FIRST_PERSON_PROJECT = [
    "my driveway",
    "my patio",
    "my house",
    "our driveway",
    "our patio",
    "our house",
    "my backyard",
    "our backyard",
    "my slab",
    "our slab",
    "my garage",
    "our garage",
    "my pool",
    "our pool",
]

PROJECT_ACTIONS = [
    "pour", "poured", "replace", "replacement",
    "extend", "extension", "repair", "demo",
    "demolish", "remove and replace", "install",
    "form", "finish", "add concrete", "new concrete",
]

TRADE_REQUEST = [
    "sub needed",
    "subcontractor needed",
    "concrete sub",
    "concrete crew needed",
    "foundation crew",
    "builder needs",
    "looking for subs",
    "seeking subcontractor",
    "send pricing",
    "need pricing",
    "bid this",
]

MARKETING_PHRASES = [
    "we offer",
    "our services",
    "call us today",
    "free estimate",
    "free estimates",
    "serving homeowners",
    "years of experience",
    "licensed and insured",
    "contact us today",
    "get a free quote",
    "request a free quote",
    "concrete company serving",
    "best concrete contractor",
    "top rated",
    "our team",
    "our customers",
    "we specialize",
    "learn more",
    "cost guide",
    "material guide",
    "how much does",
]

DIRECTORY_PHRASES = [
    "top 10",
    "near me",
    "find local pros",
    "compare contractors",
    "reviews",
    "directory",
    "job openings",
    "salary",
    "careers",
]

def classify(text):
    t = (text or "").lower()

    concrete_hits = sum(1 for x in CONCRETE_TERMS if x in t)
    ad_hits = sum(1 for x in AD_TERMS if x in t)
    buyer_hits = sum(1 for p in BUYER_PATTERNS if re.search(p, t))
    first_person = any(x in t for x in FIRST_PERSON_PROJECT)
    trade_request = any(x in t for x in TRADE_REQUEST)
    marketing_hits = sum(1 for x in MARKETING_PHRASES if x in t)
    directory_hits = sum(1 for x in DIRECTORY_PHRASES if x in t)

    return {
        "concrete_hits": concrete_hits,
        "ad_hits": ad_hits,
        "buyer_hits": buyer_hits,
        "intent_hits": buyer_hits,
        "homeowner": first_person or "homeowner" in t,
        "client": any(x in t for x in ["my client","for a client","client needs","for this client"]),
        "trade": trade_request,
        "first_person": first_person,
        "trade_request": trade_request,
        "marketing_hits": marketing_hits,
        "directory_hits": directory_hits,
    }

def is_relevant(text):
    c = classify(text)

    # Must actually concern concrete.
    if c["concrete_hits"] < 1:
        return False

    # Reject directories, employment pages and generic listings.
    if c["directory_hits"] >= 1 and c["buyer_hits"] == 0 and not c["trade_request"]:
        return False

    # Strong marketing/service pages are not leads unless there is an
    # unmistakable customer/subcontractor request in the captured text.
    if (c["marketing_hits"] >= 2 or c["ad_hits"] >= 2) and c["buyer_hits"] == 0 and not c["trade_request"]:
        return False

    # A valid lead needs explicit purchase/request intent.
    if c["buyer_hits"] >= 1:
        return True

    # Or a first-person project plus obvious concrete context.
    if c["first_person"] and c["concrete_hits"] >= 1:
        return True

    # Or an actual GC/builder subcontractor solicitation.
    if c["trade_request"]:
        return True

    return False
