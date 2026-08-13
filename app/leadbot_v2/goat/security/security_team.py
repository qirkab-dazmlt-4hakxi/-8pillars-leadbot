from __future__ import annotations

import hashlib
import json
import secrets

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum

from leadbot_v2.goat.access_control import (
    EXECUTIVE_ROLES,
    Principal,
    Role,
)


class SecurityAction(str, Enum):
    VIEW_EVENTS = "view_events"
    CREATE_INCIDENT = "create_incident"
    QUARANTINE_SESSION = "quarantine_session"
    REVOKE_SESSION = "revoke_session"
    REVOKE_DEVICE = "revoke_device"

    ROTATE_ROOT_KEY = "rotate_root_key"
    GLOBAL_SAFE_MODE = "global_safe_mode"
    GLOBAL_HALT = "global_halt"
    DISABLE_EXECUTIVE = "disable_executive"


CRITICAL_ACTIONS = frozenset({
    SecurityAction.ROTATE_ROOT_KEY,
    SecurityAction.GLOBAL_HALT,
    SecurityAction.DISABLE_EXECUTIVE,
})


MUTATING_ACTIONS = frozenset({
    SecurityAction.CREATE_INCIDENT,
    SecurityAction.QUARANTINE_SESSION,
    SecurityAction.REVOKE_SESSION,
    SecurityAction.REVOKE_DEVICE,
})


class SecurityAuthorizationError(PermissionError):
    pass


class DualControlError(PermissionError):
    pass


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: str
    actor_id: str
    action: str
    target: str
    reason: str
    previous_hash: str
    event_hash: str


class TamperEvidentAuditLog:
    """
    Append-only hash-chained security audit log.

    Production persistence will later use immutable/WORM-capable storage.
    """

    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    @staticmethod
    def _digest(payload: dict) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(encoded).hexdigest()

    def append(
        self,
        *,
        actor_id: str,
        action: str,
        target: str,
        reason: str,
    ) -> AuditEvent:

        if not actor_id.strip():
            raise ValueError("actor_id required")

        if not action.strip():
            raise ValueError("action required")

        if not target.strip():
            raise ValueError("target required")

        if not reason.strip():
            raise ValueError("security action reason required")

        sequence = len(self._events) + 1

        previous_hash = (
            self._events[-1].event_hash
            if self._events
            else self.GENESIS
        )

        timestamp = datetime.now(timezone.utc).isoformat()

        unsigned = {
            "sequence": sequence,
            "timestamp": timestamp,
            "actor_id": actor_id,
            "action": action,
            "target": target,
            "reason": reason,
            "previous_hash": previous_hash,
        }

        event_hash = self._digest(unsigned)

        event = AuditEvent(
            **unsigned,
            event_hash=event_hash,
        )

        self._events.append(event)
        return event

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def verify(self) -> bool:
        previous = self.GENESIS

        for expected_sequence, event in enumerate(
            self._events,
            start=1,
        ):
            if event.sequence != expected_sequence:
                return False

            if event.previous_hash != previous:
                return False

            unsigned = {
                "sequence": event.sequence,
                "timestamp": event.timestamp,
                "actor_id": event.actor_id,
                "action": event.action,
                "target": event.target,
                "reason": event.reason,
                "previous_hash": event.previous_hash,
            }

            if self._digest(unsigned) != event.event_hash:
                return False

            previous = event.event_hash

        return True


@dataclass(frozen=True)
class CriticalActionRequest:
    request_id: str
    action: SecurityAction
    target: str
    reason: str
    requested_by: str
    approvals: tuple[tuple[str, str], ...]
    executed: bool = False


class DualControlGate:
    """
    Critical operations require independent security + executive approval.

    One compromised account is insufficient.
    """

    def __init__(self) -> None:
        self._requests: dict[str, CriticalActionRequest] = {}

    @staticmethod
    def _approval_class(principal: Principal) -> str | None:
        if principal.role == Role.SECURITY_ADMIN:
            return "security"

        if principal.role in EXECUTIVE_ROLES:
            return "executive"

        return None

    def request(
        self,
        *,
        principal: Principal,
        action: SecurityAction,
        target: str,
        reason: str,
    ) -> CriticalActionRequest:

        if action not in CRITICAL_ACTIONS:
            raise ValueError(
                "dual-control gate only accepts critical actions"
            )

        approval_class = self._approval_class(principal)

        if approval_class is None:
            raise DualControlError(
                "critical request requires security admin or executive"
            )

        if not reason.strip():
            raise ValueError("reason required")

        request_id = secrets.token_hex(16)

        request = CriticalActionRequest(
            request_id=request_id,
            action=action,
            target=target,
            reason=reason,
            requested_by=principal.user_id,
            approvals=((principal.user_id, approval_class),),
        )

        self._requests[request_id] = request
        return request

    def approve(
        self,
        *,
        request_id: str,
        principal: Principal,
    ) -> CriticalActionRequest:

        request = self._requests[request_id]

        approval_class = self._approval_class(principal)

        if approval_class is None:
            raise DualControlError(
                "approver is not authorized for dual control"
            )

        if principal.user_id in {
            user_id for user_id, _ in request.approvals
        }:
            raise DualControlError(
                "same identity cannot approve twice"
            )

        approvals = request.approvals + (
            (principal.user_id, approval_class),
        )

        updated = replace(
            request,
            approvals=approvals,
        )

        self._requests[request_id] = updated
        return updated

    def is_approved(self, request_id: str) -> bool:
        request = self._requests[request_id]

        classes = {
            approval_class
            for _, approval_class in request.approvals
        }

        users = {
            user_id
            for user_id, _ in request.approvals
        }

        return (
            len(users) >= 2
            and "security" in classes
            and "executive" in classes
        )

    def mark_executed(
        self,
        request_id: str,
    ) -> CriticalActionRequest:

        if not self.is_approved(request_id):
            raise DualControlError(
                "critical operation lacks dual approval"
            )

        request = self._requests[request_id]

        if request.executed:
            raise DualControlError(
                "critical operation already executed"
            )

        updated = replace(
            request,
            executed=True,
        )

        self._requests[request_id] = updated
        return updated


class SecurityTeamPolicy:

    @staticmethod
    def may_view(principal: Principal) -> bool:
        return (
            principal.role in EXECUTIVE_ROLES
            or principal.role in {
                Role.SECURITY_ANALYST,
                Role.SECURITY_ADMIN,
            }
        )

    @staticmethod
    def may_mutate(principal: Principal) -> bool:
        return (
            principal.role in EXECUTIVE_ROLES
            or principal.role == Role.SECURITY_ADMIN
        )

    @staticmethod
    def require_view(principal: Principal) -> None:
        if not SecurityTeamPolicy.may_view(principal):
            raise SecurityAuthorizationError(
                "security-console access denied"
            )

    @staticmethod
    def require_mutate(principal: Principal) -> None:
        if not SecurityTeamPolicy.may_mutate(principal):
            raise SecurityAuthorizationError(
                "security mutation denied"
            )


class SecurityControlPlane:
    """
    Defensive security state controller.

    No hack-back or offensive functionality exists here.
    """

    def __init__(self) -> None:
        self.audit = TamperEvidentAuditLog()
        self.dual_control = DualControlGate()

        self.revoked_sessions: set[str] = set()
        self.revoked_devices: set[str] = set()
        self.quarantined_sessions: set[str] = set()

    def quarantine_session(
        self,
        *,
        principal: Principal,
        session_id: str,
        reason: str,
    ) -> None:

        SecurityTeamPolicy.require_mutate(principal)

        self.quarantined_sessions.add(session_id)

        self.audit.append(
            actor_id=principal.user_id,
            action=SecurityAction.QUARANTINE_SESSION.value,
            target=session_id,
            reason=reason,
        )

    def revoke_session(
        self,
        *,
        principal: Principal,
        session_id: str,
        reason: str,
    ) -> None:

        SecurityTeamPolicy.require_mutate(principal)

        self.revoked_sessions.add(session_id)
        self.quarantined_sessions.discard(session_id)

        self.audit.append(
            actor_id=principal.user_id,
            action=SecurityAction.REVOKE_SESSION.value,
            target=session_id,
            reason=reason,
        )

    def revoke_device(
        self,
        *,
        principal: Principal,
        device_id: str,
        reason: str,
    ) -> None:

        SecurityTeamPolicy.require_mutate(principal)

        self.revoked_devices.add(device_id)

        self.audit.append(
            actor_id=principal.user_id,
            action=SecurityAction.REVOKE_DEVICE.value,
            target=device_id,
            reason=reason,
        )

    def request_critical_action(
        self,
        *,
        principal: Principal,
        action: SecurityAction,
        target: str,
        reason: str,
    ) -> CriticalActionRequest:

        request = self.dual_control.request(
            principal=principal,
            action=action,
            target=target,
            reason=reason,
        )

        self.audit.append(
            actor_id=principal.user_id,
            action=f"request:{action.value}",
            target=target,
            reason=reason,
        )

        return request

    def approve_critical_action(
        self,
        *,
        principal: Principal,
        request_id: str,
    ) -> CriticalActionRequest:

        request = self.dual_control.approve(
            request_id=request_id,
            principal=principal,
        )

        self.audit.append(
            actor_id=principal.user_id,
            action=f"approve:{request.action.value}",
            target=request.target,
            reason=request.reason,
        )

        return request

    def execute_critical_action(
        self,
        *,
        principal: Principal,
        request_id: str,
    ) -> CriticalActionRequest:

        SecurityTeamPolicy.require_mutate(principal)

        request = self.dual_control.mark_executed(
            request_id
        )

        self.audit.append(
            actor_id=principal.user_id,
            action=f"execute:{request.action.value}",
            target=request.target,
            reason=request.reason,
        )

        return request
