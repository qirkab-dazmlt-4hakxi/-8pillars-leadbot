from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol


class CommunicationChannel(str, Enum):
    VOICE = "voice"
    SMS = "sms"
    EMAIL = "email"
    WEB_CHAT = "web_chat"


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class RecordingState(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    NOTICE_REQUIRED = "notice_required"
    CONSENT_PENDING = "consent_pending"
    CONSENTED = "consented"
    DECLINED = "declined"
    RECORDING = "recording"


class CommunicationComplianceError(PermissionError):
    pass


@dataclass(frozen=True)
class CompanyCommunication:
    communication_id: str
    tenant_id: str
    business_unit: str
    channel: CommunicationChannel
    direction: Direction
    company_identity: str
    counterparty: str
    actor_id: str | None
    created_at: str
    recording_state: RecordingState
    project_id: str | None = None
    opportunity_id: str | None = None
    contact_id: str | None = None


@dataclass(frozen=True)
class RecordingPolicy:
    recording_enabled: bool = True
    disclosure_required: bool = True
    affirmative_consent_required: bool = True

    def may_record(
        self,
        *,
        notice_given: bool,
        consent_received: bool,
    ) -> bool:

        if not self.recording_enabled:
            return False

        if self.disclosure_required and not notice_given:
            return False

        if (
            self.affirmative_consent_required
            and not consent_received
        ):
            return False

        return True


class CommunicationArchive(Protocol):

    def store(
        self,
        communication: CompanyCommunication,
    ) -> None:
        ...


class CompanyCommunicationsGateway:
    """
    Central entry point for GOAT-managed company communications.

    Provider integrations such as business telephony/SMS/email are adapters
    behind this boundary.

    Personal devices/accounts are not silently intercepted.
    """

    def __init__(
        self,
        *,
        recording_policy: RecordingPolicy,
        archive: CommunicationArchive,
    ) -> None:
        self.recording_policy = recording_policy
        self.archive = archive

    def create_call(
        self,
        *,
        communication_id: str,
        tenant_id: str,
        business_unit: str,
        direction: Direction,
        company_identity: str,
        counterparty: str,
        actor_id: str | None,
        notice_given: bool,
        consent_received: bool,
        project_id: str | None = None,
        opportunity_id: str | None = None,
        contact_id: str | None = None,
    ) -> CompanyCommunication:

        may_record = self.recording_policy.may_record(
            notice_given=notice_given,
            consent_received=consent_received,
        )

        state = (
            RecordingState.RECORDING
            if may_record
            else RecordingState.DECLINED
        )

        call = CompanyCommunication(
            communication_id=communication_id,
            tenant_id=tenant_id,
            business_unit=business_unit,
            channel=CommunicationChannel.VOICE,
            direction=direction,
            company_identity=company_identity,
            counterparty=counterparty,
            actor_id=actor_id,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
            recording_state=state,
            project_id=project_id,
            opportunity_id=opportunity_id,
            contact_id=contact_id,
        )

        self.archive.store(call)
        return call

    def create_sms(
        self,
        *,
        communication_id: str,
        tenant_id: str,
        business_unit: str,
        direction: Direction,
        company_identity: str,
        counterparty: str,
        actor_id: str | None,
        project_id: str | None = None,
        opportunity_id: str | None = None,
        contact_id: str | None = None,
    ) -> CompanyCommunication:

        message = CompanyCommunication(
            communication_id=communication_id,
            tenant_id=tenant_id,
            business_unit=business_unit,
            channel=CommunicationChannel.SMS,
            direction=direction,
            company_identity=company_identity,
            counterparty=counterparty,
            actor_id=actor_id,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
            recording_state=RecordingState.NOT_APPLICABLE,
            project_id=project_id,
            opportunity_id=opportunity_id,
            contact_id=contact_id,
        )

        self.archive.store(message)
        return message


class InMemoryCommunicationArchive:

    def __init__(self) -> None:
        self.items: list[CompanyCommunication] = []

    def store(
        self,
        communication: CompanyCommunication,
    ) -> None:
        self.items.append(communication)
