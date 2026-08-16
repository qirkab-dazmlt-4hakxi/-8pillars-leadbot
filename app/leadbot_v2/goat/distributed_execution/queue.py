from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from leadbot_v2.goat.workflow_control import (
    ActionRisk,
    Effect,
    EffectKind,
)

from .models import (
    EXECUTION_TOPIC,
    WAKE_TOPIC,
)


def _dt(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        raise ValueError(
            "datetime must be timezone-aware"
        )

    return value.astimezone(
        timezone.utc
    ).isoformat()


def _parse_dt(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError(
            "datetime must be timezone-aware"
        )

    return parsed.astimezone(
        timezone.utc
    )


def effect_payload(
    effect: Effect,
) -> dict[str, Any]:
    return {
        "message_type": "effect",
        "effect_id": effect.effect_id,
        "workflow_id": effect.workflow_id,
        "tenant_id": effect.tenant_id,
        "kind": effect.kind.value,
        "step_id": effect.step_id,
        "action": effect.action,
        "idempotency_key": effect.idempotency_key,
        "payload": dict(effect.payload),
        "not_before": _dt(effect.not_before),
        "deadline_at": _dt(effect.deadline_at),
        "risk": effect.risk.value,
        "requires_approval": effect.requires_approval,
    }


def effect_from_payload(
    payload: dict[str, Any],
) -> Effect:
    if payload.get("message_type") != "effect":
        raise ValueError(
            "not an execution effect payload"
        )

    not_before = _parse_dt(
        payload.get("not_before")
    )

    if not_before is None:
        raise ValueError(
            "effect not_before missing"
        )

    return Effect(
        effect_id=payload["effect_id"],
        workflow_id=payload["workflow_id"],
        tenant_id=payload["tenant_id"],
        kind=EffectKind(payload["kind"]),
        step_id=payload.get("step_id"),
        action=payload["action"],
        idempotency_key=payload["idempotency_key"],
        payload=dict(
            payload.get("payload", {})
        ),
        not_before=not_before,
        deadline_at=_parse_dt(
            payload.get("deadline_at")
        ),
        risk=ActionRisk(
            payload.get(
                "risk",
                ActionRisk.LOW.value,
            )
        ),
        requires_approval=bool(
            payload.get(
                "requires_approval",
                False,
            )
        ),
    )


class DurableExecutionQueue:
    def __init__(
        self,
        store,
    ) -> None:
        self.store = store

    def enqueue_effect(
        self,
        effect: Effect,
    ) -> str:
        if effect.kind not in {
            EffectKind.RUN_STEP,
            EffectKind.RUN_COMPENSATION,
        }:
            raise ValueError(
                "control effects are not worker-executable"
            )

        return self.store.enqueue_outbox(
            tenant_id=effect.tenant_id,
            topic=EXECUTION_TOPIC,
            payload=effect_payload(effect),
            aggregate_type="workflow",
            aggregate_id=effect.workflow_id,
            dedupe_key=(
                f"effect:{effect.effect_id}"
            ),
            available_at=effect.not_before,
        )

    def enqueue_wake(
        self,
        *,
        workflow_id: str,
        tenant_id: str,
        available_at: datetime,
        reason: str,
    ) -> str:
        payload = {
            "message_type": "wake",
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
            "reason": reason,
            "available_at": _dt(available_at),
        }

        dedupe_key = (
            f"wake:{workflow_id}:"
            f"{_dt(available_at)}:"
            f"{reason}"
        )

        return self.store.enqueue_outbox(
            tenant_id=tenant_id,
            topic=WAKE_TOPIC,
            payload=payload,
            aggregate_type="workflow",
            aggregate_id=workflow_id,
            dedupe_key=dedupe_key,
            available_at=available_at,
        )
