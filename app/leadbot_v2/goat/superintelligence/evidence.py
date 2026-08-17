from __future__ import annotations

from .canonical import (
    stable_hash,
)

from .models import (
    Evidence,
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
            Evidence
        ] = []

    def append(
        self,
        *,
        source: str,
        claim: str,
        value,
        confidence: float,
        authority: float,
        observed_at=None,
        metadata=None,
    ) -> Evidence:
        observed_at = ensure_utc(
            observed_at
        )

        previous = (
            self._entries[-1]
            .chain_hash
            if self._entries
            else GENESIS_HASH
        )

        payload_hash = stable_hash(
            value
        )

        evidence_id = stable_hash(
            {
                "source":
                    source,
                "claim":
                    claim,
                "payload_hash":
                    payload_hash,
                "observed_at":
                    observed_at,
            }
        )[:32]

        payload = {
            "evidence_id":
                evidence_id,
            "source":
                source,
            "claim":
                claim,
            "value":
                value,
            "observed_at":
                observed_at,
            "confidence":
                clamp01(
                    confidence
                ),
            "authority":
                clamp01(
                    authority
                ),
            "payload_hash":
                payload_hash,
            "previous_chain_hash":
                previous,
            "metadata":
                dict(
                    metadata or {}
                ),
        }

        chain_hash = stable_hash(
            payload
        )

        entry = Evidence(
            chain_hash=(
                chain_hash
            ),
            **payload,
        )

        self._entries.append(
            entry
        )

        return entry

    def entries(
        self,
    ) -> tuple[
        Evidence,
        ...,
    ]:
        return tuple(
            self._entries
        )

    def by_id(
        self,
        evidence_id: str,
    ) -> Evidence:
        for entry in self._entries:
            if (
                entry.evidence_id
                == evidence_id
            ):
                return entry

        raise KeyError(
            evidence_id
        )

    def verify(
        self,
    ) -> bool:
        previous = GENESIS_HASH

        for entry in self._entries:
            if (
                entry.previous_chain_hash
                != previous
            ):
                raise EvidenceIntegrityError(
                    "evidence predecessor hash mismatch"
                )

            payload = {
                "evidence_id":
                    entry.evidence_id,
                "source":
                    entry.source,
                "claim":
                    entry.claim,
                "value":
                    entry.value,
                "observed_at":
                    entry.observed_at,
                "confidence":
                    entry.confidence,
                "authority":
                    entry.authority,
                "payload_hash":
                    entry.payload_hash,
                "previous_chain_hash":
                    entry.previous_chain_hash,
                "metadata":
                    entry.metadata,
            }

            if (
                stable_hash(
                    payload
                )
                != entry.chain_hash
            ):
                raise EvidenceIntegrityError(
                    "evidence content hash mismatch"
                )

            previous = (
                entry.chain_hash
            )

        return True
