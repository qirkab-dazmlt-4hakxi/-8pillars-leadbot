from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Lead:
    source: str
    source_url: str
    title: str
    text: str
    discovered_at: str
    published_at: Optional[str] = None
    external_id: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    poster_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    project_address: Optional[str] = None
    scope: Optional[str] = None
    dimensions: Optional[str] = None
    square_feet: Optional[float] = None
    urgency: Optional[str] = None
    contact_channel: Optional[str] = None
    platform_username: Optional[str] = None
    profile_url: Optional[str] = None
    contactability: Optional[str] = None
    contact_route: Optional[str] = None
    inbound_message: bool = False
    score: int = 0
    temperature: str = "COLD"
    fingerprint: Optional[str] = None
    evidence: Optional[str] = None
    def asdict(self):
        return asdict(self)
