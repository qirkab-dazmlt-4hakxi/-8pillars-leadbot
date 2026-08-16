from __future__ import annotations

import threading

from copy import deepcopy
from typing import Protocol

from .models import WorkflowState


class RepositoryError(RuntimeError):
    pass


class WorkflowAlreadyExists(RepositoryError):
    pass


class WorkflowNotFound(RepositoryError):
    pass


class WorkflowConcurrencyConflict(RepositoryError):
    pass


class WorkflowRepository(Protocol):
    def create(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        ...

    def load(
        self,
        workflow_id: str,
    ) -> WorkflowState:
        ...

    def save(
        self,
        state: WorkflowState,
        *,
        expected_revision: int,
    ) -> WorkflowState:
        ...


class InMemoryWorkflowRepository:
    def __init__(self) -> None:
        self._states: dict[
            str,
            WorkflowState,
        ] = {}

        self._lock = (
            threading.RLock()
        )

    def create(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        with self._lock:
            if (
                state.workflow_id
                in self._states
            ):
                raise WorkflowAlreadyExists(
                    state.workflow_id
                )

            stored = deepcopy(
                state
            )

            stored.revision = 1

            self._states[
                state.workflow_id
            ] = stored

            return deepcopy(
                stored
            )

    def load(
        self,
        workflow_id: str,
    ) -> WorkflowState:
        with self._lock:
            try:
                state = self._states[
                    workflow_id
                ]

            except KeyError as exc:
                raise WorkflowNotFound(
                    workflow_id
                ) from exc

            return deepcopy(
                state
            )

    def save(
        self,
        state: WorkflowState,
        *,
        expected_revision: int,
    ) -> WorkflowState:
        with self._lock:
            current = self._states.get(
                state.workflow_id
            )

            if current is None:
                raise WorkflowNotFound(
                    state.workflow_id
                )

            if (
                current.revision
                != expected_revision
            ):
                raise WorkflowConcurrencyConflict(
                    f"{state.workflow_id}: expected "
                    f"revision {expected_revision}, "
                    f"current {current.revision}"
                )

            stored = deepcopy(
                state
            )

            stored.revision = (
                current.revision + 1
            )

            self._states[
                state.workflow_id
            ] = stored

            return deepcopy(
                stored
            )
