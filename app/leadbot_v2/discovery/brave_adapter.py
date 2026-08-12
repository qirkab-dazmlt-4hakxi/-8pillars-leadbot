from __future__ import annotations

from leadbot_v2.core.models import LeadIntelligenceRecord


def from_legacy_lead(old) -> LeadIntelligenceRecord:
    record = LeadIntelligenceRecord(
        source=getattr(old, "source", "") or "brave",
        source_url=getattr(old, "source_url", "") or "",
        title=getattr(old, "title", "") or "",
        raw_text=getattr(old, "text", "") or "",
        city=getattr(old, "city", None),
        author_name=getattr(old, "poster_name", None),
        author_username=getattr(old, "platform_username", None),
        author_profile_url=getattr(old, "profile_url", None),
    )

    phone = getattr(old, "phone", None)
    email = getattr(old, "email", None)
    profile = getattr(old, "profile_url", None)

    if phone:
        record.add_contact(
            channel="phone",
            value=phone,
            verified_public=True,
            confidence=0.98,
            source_url=record.source_url,
        )

    if email:
        record.add_contact(
            channel="email",
            value=email,
            verified_public=True,
            confidence=0.98,
            source_url=record.source_url,
        )

    if profile:
        record.add_contact(
            channel="profile",
            value=profile,
            verified_public=True,
            confidence=0.90,
            source_url=record.source_url,
        )

    record.build_fingerprint()

    return record
