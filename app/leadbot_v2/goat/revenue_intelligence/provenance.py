from __future__ import annotations

from dataclasses import replace

from .canonical import (
    normalize_text,
    normalize_uri,
    stable_hash,
)

from .models import (
    EvidenceRecord,
    LeadCandidate,
    clamp01,
    ensure_utc,
)


GENESIS_HASH = "0" * 64


class EvidenceIntegrityError(
    RuntimeError
):
    pass


class EvidenceLedger:
    def __init__(
        self,
    ) -> None:
        self._entries: list[
            EvidenceRecord
        ] = []

    def append(
        self,
        candidate: LeadCandidate,
    ) -> EvidenceRecord:
        previous = (
            self._entries[-1]
            .evidence_hash
            if self._entries
            else GENESIS_HASH
        )

        observed_at = ensure_utc(
            candidate.observed_at
        )

        source_uri = normalize_uri(
            candidate.source_uri
        )

        text = normalize_text(
            candidate.raw_text
        )

        evidence_id = stable_hash(
            {
                "candidate_id":
                    candidate.candidate_id,
                "source_type":
                    candidate.source_type.value,
                "source_uri":
                    source_uri,
                "observed_at":
                    observed_at,
                "text":
                    text,
            }
        )[:32]

        confidence = clamp01(
            float(
                candidate.metadata.get(
                    "source_confidence",
                    0.50,
                )
            )
        )

        payload = {
            "evidence_id":
                evidence_id,
            "source_type":
                candidate.source_type.value,
            "source_uri":
                source_uri,
            "observed_at":
                observed_at,
            "text":
                text,
            "confidence":
                confidence,
            "metadata":
                dict(
                    candidate.metadata
                ),
            "previous_hash":
                previous,
        }

        evidence_hash = stable_hash(
            payload
        )

        entry = EvidenceRecord(
            evidence_id=evidence_id,
            source_type=(
                candidate.source_type
            ),
            source_uri=source_uri,
            observed_at=observed_at,
            text=text,
            confidence=confidence,
            previous_hash=previous,
            evidence_hash=(
                evidence_hash
            ),
            metadata=dict(
                candidate.metadata
            ),
        )

        self._entries.append(
            entry
        )

        return entry

    def entries(
        self,
    ) -> tuple[
        EvidenceRecord,
        ...
    ]:
        return tuple(
            self._entries
        )

    def verify(
        self,
    ) -> bool:
        previous = GENESIS_HASH

        for entry in self._entries:
            if entry.previous_hash != previous:
                raise EvidenceIntegrityError(
                    "evidence chain predecessor mismatch"
                )

            payload = {
                "evidence_id":
                    entry.evidence_id,
                "source_type":
                    entry.source_type.value,
                "source_uri":
                    entry.source_uri,
                "observed_at":
                    entry.observed_at,
                "text":
                    entry.text,
                "confidence":
                    entry.confidence,
                "metadata":
                    entry.metadata,
                "previous_hash":
                    entry.previous_hash,
            }

            calculated = stable_hash(
                payload
            )

            if calculated != entry.evidence_hash:
                raise EvidenceIntegrityError(
                    "evidence payload hash mismatch"
                )

            previous = (
                entry.evidence_hash
            )

        return True

    def tamper_for_test(
        self,
        index: int,
        *,
        text: str,
    ) -> None:
        self._entries[
            index
        ] = replace(
            self._entries[
                index
            ],
            text=text,
        )
