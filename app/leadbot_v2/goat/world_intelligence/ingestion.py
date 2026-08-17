from __future__ import annotations

from dataclasses import replace

from .canonical import (
    stable_hash,
)

from .models import (
    EvidenceStatus,
    SourceAuthority,
    SourceHealthState,
    SourcePolicyError,
)

from .provenance import (
    EvidenceChain,
)

from .sources import (
    AUTHORITY_WEIGHT,
)


class EvidenceIngestionGate:
    def __init__(
        self,
        *,
        source_registry,
        source_health,
        chain=None,
    ) -> None:
        self.source_registry = (
            source_registry
        )

        self.source_health = (
            source_health
        )

        self.chain = (
            chain
            or EvidenceChain()
        )

        self._fingerprints = set()

    @staticmethod
    def fingerprint(
        evidence,
    ):
        return stable_hash(
            {
                "source_id":
                    evidence.source_id,

                "domain":
                    evidence.domain,

                "subject":
                    evidence.subject,

                "predicate":
                    evidence.predicate,

                "value":
                    evidence.value,

                "jurisdiction":
                    evidence.jurisdiction,

                "published_at":
                    evidence.published_at,

                "valid_from":
                    evidence.valid_from,

                "valid_until":
                    evidence.valid_until,
            }
        )

    def ingest(
        self,
        evidence,
    ):
        source = (
            self.source_registry
            .require_domain(
                evidence.source_id,
                evidence.domain,
            )
        )

        health = (
            self.source_health
            .health(
                source.source_id
            )
        )

        fingerprint = (
            self.fingerprint(
                evidence
            )
        )

        if fingerprint in self._fingerprints:
            return None

        self._fingerprints.add(
            fingerprint
        )

        confidence = max(
            0.0,
            min(
                1.0,
                evidence.confidence
                * source.base_confidence
                * AUTHORITY_WEIGHT[
                    source.authority
                ],
            ),
        )

        status = (
            EvidenceStatus.QUARANTINED
            if health.state
            is SourceHealthState.QUARANTINED
            else evidence.status
        )

        accepted = replace(
            evidence,
            confidence=confidence,
            status=status,
        )

        return self.chain.append(
            accepted
        )
