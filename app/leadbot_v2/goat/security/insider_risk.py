from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol


class SecuritySignalType(str, Enum):

    # Data exfiltration
    RESTRICTED_EXTERNAL_SHARE = "restricted_external_share"
    PERSONAL_EMAIL_FORWARD = "personal_email_forward"
    USB_COPY = "usb_copy"
    EXTERNAL_CLOUD_UPLOAD = "external_cloud_upload"
    BULK_DOWNLOAD = "bulk_download"
    SOURCE_CODE_EXPORT = "source_code_export"
    CUSTOMER_LIST_EXPORT = "customer_list_export"

    # Endpoint controls
    SCREEN_CAPTURE_POLICY_VIOLATION = (
        "screen_capture_policy_violation"
    )
    UNAUTHORIZED_PRINT = "unauthorized_print"
    UNAUTHORIZED_CLIPBOARD_COPY = (
        "unauthorized_clipboard_copy"
    )

    # Identity / access
    PRIVILEGE_ESCALATION_ATTEMPT = (
        "privilege_escalation_attempt"
    )
    CREDENTIAL_SHARING = "credential_sharing"
    UNUSUAL_ADMIN_ACTION = "unusual_admin_action"
    DISABLED_SECURITY_CONTROL = "disabled_security_control"
    LOG_DELETION_ATTEMPT = "log_deletion_attempt"

    # Business sabotage / financial
    MASS_RECORD_DELETE = "mass_record_delete"
    UNAUTHORIZED_VENDOR_CHANGE = (
        "unauthorized_vendor_change"
    )
    PAYMENT_DESTINATION_CHANGE = (
        "payment_destination_change"
    )
    BACKUP_DISABLE_ATTEMPT = "backup_disable_attempt"


SIGNAL_SEVERITY = {
    SecuritySignalType.RESTRICTED_EXTERNAL_SHARE: 55,
    SecuritySignalType.PERSONAL_EMAIL_FORWARD: 45,
    SecuritySignalType.USB_COPY: 50,
    SecuritySignalType.EXTERNAL_CLOUD_UPLOAD: 50,
    SecuritySignalType.BULK_DOWNLOAD: 45,
    SecuritySignalType.SOURCE_CODE_EXPORT: 75,
    SecuritySignalType.CUSTOMER_LIST_EXPORT: 65,

    SecuritySignalType.SCREEN_CAPTURE_POLICY_VIOLATION: 30,
    SecuritySignalType.UNAUTHORIZED_PRINT: 25,
    SecuritySignalType.UNAUTHORIZED_CLIPBOARD_COPY: 25,

    SecuritySignalType.PRIVILEGE_ESCALATION_ATTEMPT: 70,
    SecuritySignalType.CREDENTIAL_SHARING: 65,
    SecuritySignalType.UNUSUAL_ADMIN_ACTION: 40,
    SecuritySignalType.DISABLED_SECURITY_CONTROL: 80,
    SecuritySignalType.LOG_DELETION_ATTEMPT: 85,

    SecuritySignalType.MASS_RECORD_DELETE: 80,
    SecuritySignalType.UNAUTHORIZED_VENDOR_CHANGE: 65,
    SecuritySignalType.PAYMENT_DESTINATION_CHANGE: 80,
    SecuritySignalType.BACKUP_DISABLE_ATTEMPT: 90,
}


class RiskDisposition(str, Enum):
    OBSERVE = "observe"
    REVIEW = "review"
    HIGH_RISK = "high_risk"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SecuritySignal:
    signal_id: str
    tenant_id: str
    subject_user_id: str
    signal_type: SecuritySignalType
    source_system: str
    asset_id: str
    timestamp: str
    evidence_ref: str
    verified: bool
    confidence: float
    details: str


@dataclass(frozen=True)
class InsiderRiskAssessment:
    subject_user_id: str
    score: int
    disposition: RiskDisposition
    signals: tuple[SecuritySignal, ...]
    requires_investigation: bool


@dataclass(frozen=True)
class SecurityAlert:
    subject_user_id: str
    score: int
    disposition: RiskDisposition
    recipients: tuple[str, ...]
    reason: str
    evidence_refs: tuple[str, ...]


class SecurityAlertSink(Protocol):

    def send(
        self,
        alert: SecurityAlert,
    ) -> None:
        ...


class InsiderRiskEngine:
    """
    Scores objective company-security events.

    This engine DOES NOT score loyalty, political views, workplace criticism,
    protected employee activity, relationship status, or personality.
    """

    @staticmethod
    def assess(
        *,
        subject_user_id: str,
        signals: tuple[SecuritySignal, ...],
    ) -> InsiderRiskAssessment:

        applicable = tuple(
            signal
            for signal in signals
            if signal.subject_user_id == subject_user_id
        )

        score = 0

        for signal in applicable:
            base = SIGNAL_SEVERITY[signal.signal_type]

            confidence = max(
                0.0,
                min(1.0, signal.confidence),
            )

            if not signal.verified:
                confidence *= 0.5

            score += round(base * confidence)

        score = min(score, 100)

        if score >= 85:
            disposition = RiskDisposition.CRITICAL
        elif score >= 65:
            disposition = RiskDisposition.HIGH_RISK
        elif score >= 35:
            disposition = RiskDisposition.REVIEW
        else:
            disposition = RiskDisposition.OBSERVE

        return InsiderRiskAssessment(
            subject_user_id=subject_user_id,
            score=score,
            disposition=disposition,
            signals=applicable,
            requires_investigation=(
                disposition
                in {
                    RiskDisposition.HIGH_RISK,
                    RiskDisposition.CRITICAL,
                }
            ),
        )


class ConflictAwareAlertRouter:
    """
    Never sends the subject of an investigation their own alert.

    This protects investigations involving executives/security personnel.
    """

    def __init__(
        self,
        *,
        executive_recipients: dict[str, str],
        security_recipients: dict[str, str],
    ) -> None:
        self.executive_recipients = executive_recipients
        self.security_recipients = security_recipients

    def recipients_for(
        self,
        *,
        subject_user_id: str,
    ) -> tuple[str, ...]:

        recipients: list[str] = []

        for user_id, email in {
            **self.executive_recipients,
            **self.security_recipients,
        }.items():

            if user_id == subject_user_id:
                continue

            if email and email not in recipients:
                recipients.append(email)

        return tuple(recipients)


class InsiderRiskAlertService:

    def __init__(
        self,
        *,
        router: ConflictAwareAlertRouter,
        sink: SecurityAlertSink,
    ) -> None:
        self.router = router
        self.sink = sink

    def evaluate_and_alert(
        self,
        assessment: InsiderRiskAssessment,
    ) -> SecurityAlert | None:

        if not assessment.requires_investigation:
            return None

        recipients = self.router.recipients_for(
            subject_user_id=assessment.subject_user_id,
        )

        if not recipients:
            raise RuntimeError(
                "no independent security alert recipient available"
            )

        evidence = tuple(
            signal.evidence_ref
            for signal in assessment.signals
            if signal.evidence_ref
        )

        alert = SecurityAlert(
            subject_user_id=assessment.subject_user_id,
            score=assessment.score,
            disposition=assessment.disposition,
            recipients=recipients,
            reason=(
                "Objective GOAT insider-risk controls detected "
                "security events requiring human investigation."
            ),
            evidence_refs=evidence,
        )

        self.sink.send(alert)
        return alert


class InMemorySecurityAlertSink:

    def __init__(self) -> None:
        self.alerts: list[SecurityAlert] = []

    def send(
        self,
        alert: SecurityAlert,
    ) -> None:
        self.alerts.append(alert)


@dataclass(frozen=True)
class EvidenceRecord:
    sequence: int
    timestamp: str
    signal_id: str
    evidence_ref: str
    previous_hash: str
    record_hash: str


class InvestigationEvidenceChain:
    """
    Hash-linked evidence index.

    Actual artifacts later live in access-controlled immutable storage.
    """

    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    def append(
        self,
        signal: SecuritySignal,
    ) -> EvidenceRecord:

        previous = (
            self._records[-1].record_hash
            if self._records
            else self.GENESIS
        )

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        unsigned = {
            "sequence": len(self._records) + 1,
            "timestamp": timestamp,
            "signal_id": signal.signal_id,
            "evidence_ref": signal.evidence_ref,
            "previous_hash": previous,
        }

        digest = hashlib.sha256(
            json.dumps(
                unsigned,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        record = EvidenceRecord(
            **unsigned,
            record_hash=digest,
        )

        self._records.append(record)
        return record

    def verify(self) -> bool:

        previous = self.GENESIS

        for expected, record in enumerate(
            self._records,
            start=1,
        ):
            if record.sequence != expected:
                return False

            if record.previous_hash != previous:
                return False

            unsigned = {
                "sequence": record.sequence,
                "timestamp": record.timestamp,
                "signal_id": record.signal_id,
                "evidence_ref": record.evidence_ref,
                "previous_hash": record.previous_hash,
            }

            digest = hashlib.sha256(
                json.dumps(
                    unsigned,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()

            if digest != record.record_hash:
                return False

            previous = record.record_hash

        return True
