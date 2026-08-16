from __future__ import annotations

from difflib import SequenceMatcher

from .canonical import (
    canonical_key,
    normalize_email,
    normalize_phone,
    normalize_postal,
)

from .models import (
    CanonicalLead,
    LeadCandidate,
    clamp01,
)


class EntityResolver:
    """
    Strong identifiers dominate.
    Contradictory strong identifiers reduce confidence.
    Fuzzy fields can support identity, not override contradictions.
    """

    def similarity(
        self,
        candidate: LeadCandidate,
        existing: CanonicalLead,
    ) -> float:
        score = 0.0

        c_phone = normalize_phone(
            candidate.phone
        )

        e_phone = normalize_phone(
            existing.phone
        )

        c_email = normalize_email(
            candidate.email
        )

        e_email = normalize_email(
            existing.email
        )

        if c_phone and e_phone:
            if c_phone == e_phone:
                score += 0.65

            else:
                score -= 0.40

        if c_email and e_email:
            if c_email == e_email:
                score += 0.65

            else:
                score -= 0.40

        c_name = canonical_key(
            candidate.name
        )

        e_name = canonical_key(
            existing.name
        )

        if c_name and e_name:
            score += (
                SequenceMatcher(
                    None,
                    c_name,
                    e_name,
                ).ratio()
                * 0.14
            )

        c_street = canonical_key(
            candidate.street
        )

        e_street = canonical_key(
            existing.street
        )

        if c_street and e_street:
            score += (
                SequenceMatcher(
                    None,
                    c_street,
                    e_street,
                ).ratio()
                * 0.14
            )

        c_zip = normalize_postal(
            candidate.postal_code
        )

        e_zip = normalize_postal(
            existing.postal_code
        )

        if (
            c_zip
            and e_zip
            and c_zip == e_zip
        ):
            score += 0.08

        return clamp01(
            score
        )

    def best_match(
        self,
        candidate: LeadCandidate,
        existing: tuple[
            CanonicalLead,
            ...
        ],
        *,
        threshold: float = 0.72,
    ) -> tuple[
        CanonicalLead | None,
        float,
    ]:
        best = None
        best_score = 0.0

        for lead in existing:
            score = self.similarity(
                candidate,
                lead,
            )

            if score > best_score:
                best = lead
                best_score = score

        if best_score < threshold:
            return (
                None,
                best_score,
            )

        return (
            best,
            best_score,
        )
