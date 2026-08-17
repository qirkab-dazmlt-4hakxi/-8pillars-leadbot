from __future__ import annotations

from dataclasses import replace

from .canonical import stable_hash

from .models import (
    ModelIntegrityError,
    ModelRevision,
    utcnow,
)


class ModelRevisionLedger:
    def __init__(self):
        self._revisions = []

    @property
    def tip_hash(self):
        return (
            self._revisions[-1].chain_hash
            if self._revisions
            else None
        )

    @staticmethod
    def payload(revision):
        return {
            "revision_id":
                revision.revision_id,
            "model_id":
                revision.model_id,
            "sequence":
                revision.sequence,
            "snapshot_hash":
                revision.snapshot_hash,
            "changed_element_ids":
                revision.changed_element_ids,
            "created_at":
                revision.created_at,
            "author_id":
                revision.author_id,
        }

    def append(
        self,
        *,
        model_id,
        snapshot,
        changed_element_ids,
        author_id,
        created_at=None,
    ):
        created_at = (
            created_at
            or utcnow()
        )

        sequence = (
            len(self._revisions)
            + 1
        )

        snapshot_hash = stable_hash(
            snapshot
        )

        changed = tuple(
            sorted(
                set(
                    changed_element_ids
                )
            )
        )

        revision_id = stable_hash(
            {
                "model_id":
                    model_id,
                "sequence":
                    sequence,
                "snapshot_hash":
                    snapshot_hash,
                "changed_element_ids":
                    changed,
            }
        )[:32]

        provisional = ModelRevision(
            revision_id=revision_id,
            model_id=model_id,
            sequence=sequence,
            snapshot_hash=snapshot_hash,
            changed_element_ids=changed,
            created_at=created_at,
            author_id=author_id,
            previous_hash=self.tip_hash,
            content_hash="",
            chain_hash="",
        )

        content_hash = stable_hash(
            self.payload(
                provisional
            )
        )

        chain_hash = stable_hash(
            {
                "content_hash":
                    content_hash,
                "previous_hash":
                    provisional
                    .previous_hash,
            }
        )

        revision = replace(
            provisional,
            content_hash=content_hash,
            chain_hash=chain_hash,
        )

        self.verify_revision(
            revision
        )

        self._revisions.append(
            revision
        )

        return revision

    def verify_revision(
        self,
        revision,
    ):
        expected_content = stable_hash(
            self.payload(
                revision
            )
        )

        if (
            expected_content
            != revision.content_hash
        ):
            raise ModelIntegrityError(
                "model revision content hash mismatch"
            )

        expected_chain = stable_hash(
            {
                "content_hash":
                    revision.content_hash,
                "previous_hash":
                    revision.previous_hash,
            }
        )

        if (
            expected_chain
            != revision.chain_hash
        ):
            raise ModelIntegrityError(
                "model revision chain hash mismatch"
            )

        return True

    def verify(self):
        previous = None

        for (
            expected_sequence,
            revision,
        ) in enumerate(
            self._revisions,
            1,
        ):
            if (
                revision.sequence
                != expected_sequence
            ):
                raise ModelIntegrityError(
                    "model revision sequence gap"
                )

            if (
                revision.previous_hash
                != previous
            ):
                raise ModelIntegrityError(
                    "model revision linkage mismatch"
                )

            self.verify_revision(
                revision
            )

            previous = (
                revision.chain_hash
            )

        return True

    def revisions(self):
        return tuple(
            self._revisions
        )
