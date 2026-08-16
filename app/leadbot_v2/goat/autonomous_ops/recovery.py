from __future__ import annotations

from .models import RecoverySweepResult


WORKFLOW_ENTITY_TYPE = "goat.workflow"

RECOVERABLE_WORKFLOW_STATES = frozenset(
    {
        "pending",
        "running",
        "compensating",
    }
)


class RecoverySweeper:
    """
    Reconciliation is intentionally conservative.

    Paused, quarantined, failed, cancelled and succeeded workflows
    are never autonomously restarted here.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        state_store,
        runtime,
    ) -> None:
        self.tenant_id = tenant_id
        self.state_store = state_store
        self.runtime = runtime

    def run(
        self,
    ) -> RecoverySweepResult:
        records = self.state_store.list_entities(
            tenant_id=self.tenant_id,
            entity_type=WORKFLOW_ENTITY_TYPE,
            include_deleted=False,
        )

        scanned = len(records)
        eligible = 0
        reconciled = 0

        failures: list[str] = []

        for record in records:
            payload = dict(
                record.payload
            )

            status = str(
                payload.get(
                    "status",
                    "",
                )
            )

            if (
                status
                not in RECOVERABLE_WORKFLOW_STATES
            ):
                continue

            eligible += 1

            workflow_id = (
                record.entity_id
            )

            try:
                self.runtime.reconcile(
                    workflow_id
                )

                reconciled += 1

            except Exception as exc:
                failures.append(
                    f"{workflow_id}:"
                    f"{type(exc).__name__}:"
                    f"{exc}"
                )

        return RecoverySweepResult(
            scanned=scanned,
            eligible=eligible,
            reconciled=reconciled,
            failures=tuple(
                failures
            ),
        )
