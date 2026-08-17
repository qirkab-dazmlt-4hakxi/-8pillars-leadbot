from __future__ import annotations

from .canonical import to_primitive


BIM_ELEMENT_ENTITY = "goat.bim.element"
BIM_CLASH_ENTITY = "goat.bim.clash"
BIM_REVISION_ENTITY = "goat.bim.revision"

BIM_OVERLAY_ENTITY = (
    "goat.bim.engineering_overlay"
)

BIM_CONSTRAINT_ENTITY = (
    "goat.bim.constraint_finding"
)

BIM_CORRECTION_ENTITY = (
    "goat.bim.correction_alternative"
)


class BIMRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id,
        actor_id="goat-bim-kernel",
    ):
        self.store = store
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def _upsert(
        self,
        *,
        entity_type,
        entity_id,
        payload,
    ):
        current = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        expected = (
            None
            if current is None
            else int(
                current.version
            )
        )

        return self.store.put_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=to_primitive(
                payload
            ),
            actor_id=self.actor_id,
            expected_version=expected,
        )

    def save_element(
        self,
        element,
    ):
        return self._upsert(
            entity_type=(
                BIM_ELEMENT_ENTITY
            ),
            entity_id=(
                element.element_id
            ),
            payload=element,
        )

    def save_clash(
        self,
        clash,
    ):
        return self._upsert(
            entity_type=(
                BIM_CLASH_ENTITY
            ),
            entity_id=(
                clash.clash_id
            ),
            payload=clash,
        )

    def save_revision(
        self,
        revision,
    ):
        return self._upsert(
            entity_type=(
                BIM_REVISION_ENTITY
            ),
            entity_id=(
                revision.revision_id
            ),
            payload=revision,
        )

    def save_overlay(
        self,
        overlay,
    ):
        return self._upsert(
            entity_type=(
                BIM_OVERLAY_ENTITY
            ),
            entity_id=(
                overlay.overlay_id
            ),
            payload=overlay,
        )

    def save_constraint_finding(
        self,
        finding,
    ):
        return self._upsert(
            entity_type=(
                BIM_CONSTRAINT_ENTITY
            ),
            entity_id=(
                f"{finding.element_id}:"
                f"{finding.constraint_id}"
            ),
            payload=finding,
        )

    def save_correction(
        self,
        alternative,
    ):
        return self._upsert(
            entity_type=(
                BIM_CORRECTION_ENTITY
            ),
            entity_id=(
                alternative
                .alternative_id
            ),
            payload=alternative,
        )
