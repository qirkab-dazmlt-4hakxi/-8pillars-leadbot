from __future__ import annotations

import uuid

from copy import deepcopy
from datetime import timedelta
from typing import Any, Protocol

from leadbot_v2.goat.workflow_control import (
    WorkflowAlreadyExists,
    WorkflowConcurrencyConflict,
    WorkflowNotFound,
    WorkflowState,
    state_from_dict,
    state_to_dict,
)


WORKFLOW_ENTITY_TYPE = "goat.workflow"


class EnterpriseStoreContract(Protocol):
    def get_entity(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        include_deleted: bool = False,
    ) -> Any:
        ...

    def put_entity(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        actor_id: str,
        expected_version: int | None = None,
    ) -> Any:
        ...

    def acquire_lease(
        self,
        *,
        lease_name: str,
        owner_id: str,
        ttl: timedelta,
        now=None,
    ) -> Any:
        ...


def _is_occ_error(
    exc: BaseException,
) -> bool:
    """
    Translate persistence-layer OCC failures without coupling the
    execution fabric to a concrete persistence exception class.
    """

    evidence = (
        type(exc).__name__
        + " "
        + str(exc)
    ).lower()

    markers = (
        "optimistic",
        "concurrency",
        "version conflict",
        "versionconflict",
        "expected version",
    )

    return any(
        marker in evidence
        for marker in markers
    )


class EnterpriseWorkflowRepository:
    def __init__(
        self,
        store: EnterpriseStoreContract,
        *,
        actor_id: str = "goat-workflow-runtime",
        repository_instance_id: str | None = None,
        creation_lease_ttl: timedelta = timedelta(
            seconds=15
        ),
    ) -> None:
        self.store = store
        self.actor_id = actor_id

        self.repository_instance_id = (
            repository_instance_id
            or uuid.uuid4().hex
        )

        self.creation_lease_ttl = creation_lease_ttl

    def create(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        lease_name = (
            "workflow-create:"
            f"{state.tenant_id}:"
            f"{state.workflow_id}"
        )

        self.store.acquire_lease(
            lease_name=lease_name,
            owner_id=self.repository_instance_id,
            ttl=self.creation_lease_ttl,
        )

        existing = self.store.get_entity(
            tenant_id=state.tenant_id,
            entity_type=WORKFLOW_ENTITY_TYPE,
            entity_id=state.workflow_id,
        )

        if existing is not None:
            raise WorkflowAlreadyExists(
                state.workflow_id
            )

        payload = state_to_dict(state)

        try:
            record = self.store.put_entity(
                tenant_id=state.tenant_id,
                entity_type=WORKFLOW_ENTITY_TYPE,
                entity_id=state.workflow_id,
                payload=payload,
                actor_id=self.actor_id,
                expected_version=None,
            )

        except Exception as exc:
            if _is_occ_error(exc):
                raise WorkflowAlreadyExists(
                    state.workflow_id
                ) from exc

            raise

        result = deepcopy(state)

        result.revision = int(
            record.version
        )

        return result

    def load(
        self,
        workflow_id: str,
        *,
        tenant_id: str | None = None,
    ) -> WorkflowState:
        if tenant_id is None:
            raise WorkflowNotFound(
                "tenant_id required for durable workflow load"
            )

        record = self.store.get_entity(
            tenant_id=tenant_id,
            entity_type=WORKFLOW_ENTITY_TYPE,
            entity_id=workflow_id,
        )

        if record is None:
            raise WorkflowNotFound(
                workflow_id
            )

        state = state_from_dict(
            dict(record.payload)
        )

        state.revision = int(
            record.version
        )

        return state

    def load_for_tenant(
        self,
        *,
        workflow_id: str,
        tenant_id: str,
    ) -> WorkflowState:
        return self.load(
            workflow_id,
            tenant_id=tenant_id,
        )

    def save(
        self,
        state: WorkflowState,
        *,
        expected_revision: int,
    ) -> WorkflowState:
        payload = state_to_dict(state)

        try:
            record = self.store.put_entity(
                tenant_id=state.tenant_id,
                entity_type=WORKFLOW_ENTITY_TYPE,
                entity_id=state.workflow_id,
                payload=payload,
                actor_id=self.actor_id,
                expected_version=expected_revision,
            )

        except Exception as exc:
            if _is_occ_error(exc):
                raise WorkflowConcurrencyConflict(
                    f"{state.workflow_id}: "
                    f"expected revision "
                    f"{expected_revision}"
                ) from exc

            raise

        result = deepcopy(state)

        result.revision = int(
            record.version
        )

        return result


class TenantBoundWorkflowRepository:
    """
    Keeps tenant selection outside WorkflowService while preserving
    the existing WorkflowRepository protocol.
    """

    def __init__(
        self,
        repository: EnterpriseWorkflowRepository,
        *,
        tenant_id: str,
    ) -> None:
        if not tenant_id.strip():
            raise ValueError(
                "tenant_id cannot be blank"
            )

        self.repository = repository
        self.tenant_id = tenant_id

    def create(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        if state.tenant_id != self.tenant_id:
            raise ValueError(
                "tenant boundary violation"
            )

        return self.repository.create(state)

    def load(
        self,
        workflow_id: str,
    ) -> WorkflowState:
        return self.repository.load_for_tenant(
            workflow_id=workflow_id,
            tenant_id=self.tenant_id,
        )

    def save(
        self,
        state: WorkflowState,
        *,
        expected_revision: int,
    ) -> WorkflowState:
        if state.tenant_id != self.tenant_id:
            raise ValueError(
                "tenant boundary violation"
            )

        return self.repository.save(
            state,
            expected_revision=expected_revision,
        )
