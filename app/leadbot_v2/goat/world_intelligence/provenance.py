from __future__ import annotations

from dataclasses import replace

from .canonical import (
    stable_hash,
)

from .models import (
    EvidenceEnvelope,
    EvidenceIntegrityError,
)


def evidence_content_payload(
    evidence,
):
    return {
        "evidence_id":
            evidence.evidence_id,

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

        "source_url":
            evidence.source_url,

        "published_at":
            evidence.published_at,

        "acquired_at":
            evidence.acquired_at,

        "valid_from":
            evidence.valid_from,

        "valid_until":
            evidence.valid_until,

        "confidence":
            evidence.confidence,

        "status":
            evidence.status,

        "metadata":
            evidence.metadata,
    }


def seal_evidence(
    evidence: EvidenceEnvelope,
    *,
    previous_hash: str | None = None,
):
    content_hash = stable_hash(
        evidence_content_payload(
            evidence
        )
    )

    chain_hash = stable_hash(
        {
            "content_hash":
                content_hash,

            "previous_hash":
                previous_hash,
        }
    )

    return replace(
        evidence,
        content_hash=(
            content_hash
        ),
        previous_hash=(
            previous_hash
        ),
        chain_hash=(
            chain_hash
        ),
    )


def verify_evidence(
    evidence,
) -> bool:
    expected_content = stable_hash(
        evidence_content_payload(
            evidence
        )
    )

    if (
        expected_content
        != evidence.content_hash
    ):
        raise EvidenceIntegrityError(
            "evidence content hash mismatch"
        )

    expected_chain = stable_hash(
        {
            "content_hash":
                evidence.content_hash,

            "previous_hash":
                evidence.previous_hash,
        }
    )

    if (
        expected_chain
        != evidence.chain_hash
    ):
        raise EvidenceIntegrityError(
            "evidence chain hash mismatch"
        )

    return True


class EvidenceChain:
    def __init__(
        self,
    ) -> None:
        self._items = []

    @property
    def tip_hash(
        self,
    ):
        if not self._items:
            return None

        return (
            self._items[
                -1
            ].chain_hash
        )

    def append(
        self,
        evidence,
    ):
        sealed = seal_evidence(
            evidence,
            previous_hash=(
                self.tip_hash
            ),
        )

        verify_evidence(
            sealed
        )

        self._items.append(
            sealed
        )

        return sealed

    def verify(
        self,
    ) -> bool:
        previous = None

        for evidence in self._items:
            if (
                evidence.previous_hash
                != previous
            ):
                raise EvidenceIntegrityError(
                    "evidence chain linkage mismatch"
                )

            verify_evidence(
                evidence
            )

            previous = (
                evidence.chain_hash
            )

        return True

    def items(
        self,
    ):
        return tuple(
            self._items
        )
