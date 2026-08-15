from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
import uuid

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum
from typing import Any


# ============================================================
# EXCEPTIONS
# ============================================================


class PlatformRuntimeError(RuntimeError):
    pass


class PlatformAccessDenied(PlatformRuntimeError):
    pass


class DeviceNotFound(PlatformRuntimeError):
    pass


class DeviceRevoked(PlatformRuntimeError):
    pass


class UnsupportedClient(PlatformRuntimeError):
    pass


class ReplayDetected(PlatformRuntimeError):
    pass


class ApiVersionError(PlatformRuntimeError):
    pass


class SyncConflictError(PlatformRuntimeError):
    pass


class SyncQueueError(PlatformRuntimeError):
    pass


class AuditIntegrityError(PlatformRuntimeError):
    pass


# ============================================================
# ENUMS
# ============================================================


class DevicePlatform(str, Enum):
    IOS = "ios"
    IPADOS = "ipados"
    ANDROID = "android"
    MACOS = "macos"
    WINDOWS = "windows"
    WEB = "web"


class FormFactor(str, Enum):
    PHONE = "phone"
    TABLET = "tablet"
    DESKTOP = "desktop"
    BROWSER = "browser"


class ClientSurface(str, Enum):
    EXECUTIVE = "executive"
    SALES = "sales"
    MARKETING = "marketing"
    ESTIMATING = "estimating"
    PROJECT_MANAGEMENT = "project_management"
    FIELD = "field"
    FINANCE = "finance"
    SECURITY = "security"
    CLIENT_PORTAL = "client_portal"


class DataClassification(IntEnum):
    PUBLIC = 10
    INTERNAL = 20
    CONFIDENTIAL = 30
    RESTRICTED = 40
    FINANCIAL = 50


class AuthStrength(IntEnum):
    PASSWORD = 10
    MFA = 20
    PASSKEY = 30
    STEP_UP = 40


class DeviceTrust(str, Enum):
    TRUSTED = "trusted"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class RiskSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    BLOCKER = "blocker"


class SyncMutationState(str, Enum):
    PENDING = "pending"
    RETRY = "retry"
    ACKNOWLEDGED = "acknowledged"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class ConflictPolicy(str, Enum):
    SERVER_WINS = "server_wins"
    CLIENT_WINS = "client_wins"
    MERGE_DISJOINT = "merge_disjoint"
    MANUAL_REVIEW = "manual_review"


class ConflictDisposition(str, Enum):
    RESOLVED = "resolved"
    MANUAL_REVIEW = "manual_review"


class CacheDisposition(str, Enum):
    ALLOW = "allow"
    MEMORY_ONLY = "memory_only"
    DENY = "deny"


class NotificationVisibility(str, Enum):
    FULL = "full"
    GENERIC = "generic"
    HIDDEN = "hidden"


# ============================================================
# UTILITY
# ============================================================


SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z.-]+))?$"
)


def _now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _id(
    prefix: str,
) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _required(
    value: Any,
    field: str,
) -> str:
    result = str(
        value
        or ""
    ).strip()

    if not result:
        raise ValueError(
            f"{field} is required"
        )

    return result


def _aware(
    value: datetime,
    field: str,
) -> datetime:
    if (
        value.tzinfo is None
        or value.utcoffset()
        is None
    ):
        raise ValueError(
            f"{field} must be timezone-aware"
        )

    return value


def _stable(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key):
                _stable(item)
            for key, item
            in sorted(
                value.items()
            )
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        return [
            _stable(item)
            for item
            in value
        ]

    if hasattr(
        value,
        "__dict__",
    ):
        return {
            key:
                _stable(item)
            for key, item
            in sorted(
                vars(value).items()
            )
            if not key.startswith(
                "_"
            )
        }

    return value


def _canonical_json(
    value: Any,
) -> str:
    return json.dumps(
        _stable(value),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        default=str,
    )


def _hash(
    value: Any,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            value
        ).encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# SEMANTIC VERSION
# ============================================================


@dataclass(
    frozen=True,
    order=False,
)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    @classmethod
    def parse(
        cls,
        value: str,
    ) -> "SemanticVersion":
        raw = _required(
            value,
            "version",
        )

        match = SEMVER_RE.fullmatch(
            raw
        )

        if not match:
            raise ValueError(
                f"invalid semantic version: {value}"
            )

        return cls(
            major=int(
                match.group(1)
            ),
            minor=int(
                match.group(2)
            ),
            patch=int(
                match.group(3)
            ),
            prerelease=(
                match.group(4)
            ),
        )

    def _core(
        self,
    ) -> tuple[
        int,
        int,
        int,
    ]:
        return (
            self.major,
            self.minor,
            self.patch,
        )

    def __lt__(
        self,
        other: "SemanticVersion",
    ) -> bool:
        if not isinstance(
            other,
            SemanticVersion,
        ):
            return NotImplemented

        if (
            self._core()
            != other._core()
        ):
            return (
                self._core()
                < other._core()
            )

        if (
            self.prerelease
            is None
            and other.prerelease
            is not None
        ):
            return False

        if (
            self.prerelease
            is not None
            and other.prerelease
            is None
        ):
            return True

        return (
            str(
                self.prerelease
                or ""
            )
            < str(
                other.prerelease
                or ""
            )
        )

    def __le__(
        self,
        other: "SemanticVersion",
    ) -> bool:
        return (
            self == other
            or self < other
        )

    def __gt__(
        self,
        other: "SemanticVersion",
    ) -> bool:
        return not (
            self <= other
        )

    def __ge__(
        self,
        other: "SemanticVersion",
    ) -> bool:
        return not (
            self < other
        )

    def __str__(
        self,
    ) -> str:
        core = (
            f"{self.major}."
            f"{self.minor}."
            f"{self.patch}"
        )

        if self.prerelease:
            return (
                core
                + "-"
                + self.prerelease
            )

        return core


# ============================================================
# DEVICE MODEL
# ============================================================


@dataclass(frozen=True)
class ClientCapabilities:
    camera: bool
    file_upload: bool
    push_notifications: bool
    biometric_auth: bool
    passkeys: bool
    offline_storage: bool
    background_sync: bool
    local_notifications: bool
    secure_hardware: bool
    stylus: bool
    desktop_windows: bool


@dataclass(frozen=True)
class ClientPlatformProfile:
    platform: DevicePlatform
    form_factor: FormFactor
    capabilities: ClientCapabilities
    min_supported_version: SemanticVersion


@dataclass(frozen=True)
class DeviceRiskSignal:
    code: str
    severity: RiskSeverity
    message: str


@dataclass(frozen=True)
class RegisteredDevice:
    device_id: str

    tenant_id: str
    user_id: str

    platform: DevicePlatform
    form_factor: FormFactor

    app_version: SemanticVersion
    os_version: str

    managed: bool
    attested: bool

    jailbroken_or_rooted: bool
    emulator_or_virtualized: bool

    biometric_available: bool
    passkey_available: bool

    public_network: bool
    anonymizer_detected: bool
    impossible_travel_signal: bool

    registered_at: datetime
    last_seen_at: datetime

    revoked: bool = False
    revoked_at: datetime | None = None
    revoke_reason: str | None = None

    key_epoch: int = 1


@dataclass(frozen=True)
class DeviceTrustAssessment:
    device_id: str

    trust: DeviceTrust

    score: int

    findings: tuple[
        DeviceRiskSignal,
        ...
    ]

    step_up_recommended: bool


class DeviceTrustEngine:
    def assess(
        self,
        device: RegisteredDevice,
    ) -> DeviceTrustAssessment:
        score = 100

        findings = []

        if device.revoked:
            findings.append(
                DeviceRiskSignal(
                    code="DEVICE_REVOKED",
                    severity=(
                        RiskSeverity.BLOCKER
                    ),
                    message=(
                        "Device registration has "
                        "been revoked."
                    ),
                )
            )

            return (
                DeviceTrustAssessment(
                    device_id=(
                        device.device_id
                    ),
                    trust=(
                        DeviceTrust.BLOCKED
                    ),
                    score=0,
                    findings=tuple(
                        findings
                    ),
                    step_up_recommended=True,
                )
            )

        if device.jailbroken_or_rooted:
            findings.append(
                DeviceRiskSignal(
                    code="PLATFORM_INTEGRITY_FAILED",
                    severity=(
                        RiskSeverity.BLOCKER
                    ),
                    message=(
                        "Root or jailbreak signal "
                        "prevents trusted access."
                    ),
                )
            )

            return (
                DeviceTrustAssessment(
                    device_id=(
                        device.device_id
                    ),
                    trust=(
                        DeviceTrust.BLOCKED
                    ),
                    score=0,
                    findings=tuple(
                        findings
                    ),
                    step_up_recommended=True,
                )
            )

        if not device.attested:
            score -= 25

            findings.append(
                DeviceRiskSignal(
                    code="DEVICE_NOT_ATTESTED",
                    severity=(
                        RiskSeverity.REVIEW
                    ),
                    message=(
                        "Device integrity attestation "
                        "is unavailable."
                    ),
                )
            )

        if not device.managed:
            score -= 10

            findings.append(
                DeviceRiskSignal(
                    code="DEVICE_UNMANAGED",
                    severity=(
                        RiskSeverity.INFO
                    ),
                    message=(
                        "Device is not managed by "
                        "company device policy."
                    ),
                )
            )

        if device.emulator_or_virtualized:
            score -= 15

            findings.append(
                DeviceRiskSignal(
                    code="VIRTUALIZED_CLIENT",
                    severity=(
                        RiskSeverity.REVIEW
                    ),
                    message=(
                        "Virtualized/emulated client "
                        "requires additional scrutiny."
                    ),
                )
            )

        if device.public_network:
            score -= 10

            findings.append(
                DeviceRiskSignal(
                    code="PUBLIC_NETWORK",
                    severity=(
                        RiskSeverity.INFO
                    ),
                    message=(
                        "Client is using a public "
                        "or untrusted network."
                    ),
                )
            )

        if device.anonymizer_detected:
            score -= 15

            findings.append(
                DeviceRiskSignal(
                    code="NETWORK_ANONYMIZER",
                    severity=(
                        RiskSeverity.REVIEW
                    ),
                    message=(
                        "Network anonymization signal "
                        "increases session risk."
                    ),
                )
            )

        if device.impossible_travel_signal:
            score -= 30

            findings.append(
                DeviceRiskSignal(
                    code="IMPOSSIBLE_TRAVEL_SIGNAL",
                    severity=(
                        RiskSeverity.REVIEW
                    ),
                    message=(
                        "Session telemetry indicates "
                        "an impossible-travel anomaly."
                    ),
                )
            )

        score = max(
            0,
            min(
                100,
                score,
            ),
        )

        if score < 40:
            trust = (
                DeviceTrust.BLOCKED
            )

        elif score < 75:
            trust = (
                DeviceTrust.DEGRADED
            )

        else:
            trust = (
                DeviceTrust.TRUSTED
            )

        return DeviceTrustAssessment(
            device_id=(
                device.device_id
            ),
            trust=trust,
            score=score,
            findings=tuple(
                findings
            ),
            step_up_recommended=(
                score < 90
            ),
        )


# ============================================================
# DEVICE REGISTRY
# ============================================================


class DeviceRegistry:
    def __init__(
        self,
    ) -> None:
        self._devices: dict[
            str,
            RegisteredDevice,
        ] = {}

    def register(
        self,
        *,
        tenant_id: str,
        user_id: str,
        platform: DevicePlatform,
        form_factor: FormFactor,
        app_version: str,
        os_version: str,
        managed: bool,
        attested: bool,
        jailbroken_or_rooted: bool = False,
        emulator_or_virtualized: bool = False,
        biometric_available: bool = False,
        passkey_available: bool = False,
        public_network: bool = False,
        anonymizer_detected: bool = False,
        impossible_travel_signal: bool = False,
        device_id: str | None = None,
    ) -> RegisteredDevice:
        now = _now()

        device = RegisteredDevice(
            device_id=(
                device_id
                or _id(
                    "dev"
                )
            ),
            tenant_id=(
                _required(
                    tenant_id,
                    "tenant_id",
                )
            ),
            user_id=(
                _required(
                    user_id,
                    "user_id",
                )
            ),
            platform=platform,
            form_factor=(
                form_factor
            ),
            app_version=(
                SemanticVersion
                .parse(
                    app_version
                )
            ),
            os_version=(
                _required(
                    os_version,
                    "os_version",
                )
            ),
            managed=managed,
            attested=attested,
            jailbroken_or_rooted=(
                jailbroken_or_rooted
            ),
            emulator_or_virtualized=(
                emulator_or_virtualized
            ),
            biometric_available=(
                biometric_available
            ),
            passkey_available=(
                passkey_available
            ),
            public_network=(
                public_network
            ),
            anonymizer_detected=(
                anonymizer_detected
            ),
            impossible_travel_signal=(
                impossible_travel_signal
            ),
            registered_at=now,
            last_seen_at=now,
        )

        self._devices[
            device.device_id
        ] = device

        return device

    def get(
        self,
        device_id: str,
    ) -> RegisteredDevice:
        device = (
            self._devices.get(
                device_id
            )
        )

        if device is None:
            raise DeviceNotFound(
                device_id
            )

        return device

    def touch(
        self,
        device_id: str,
        *,
        at: datetime | None = None,
    ) -> RegisteredDevice:
        device = self.get(
            device_id
        )

        updated = replace(
            device,
            last_seen_at=(
                _aware(
                    at,
                    "at",
                )
                if at
                is not None
                else _now()
            ),
        )

        self._devices[
            device_id
        ] = updated

        return updated

    def revoke(
        self,
        device_id: str,
        *,
        reason: str,
    ) -> RegisteredDevice:
        device = self.get(
            device_id
        )

        if device.revoked:
            return device

        updated = replace(
            device,
            revoked=True,
            revoked_at=_now(),
            revoke_reason=(
                _required(
                    reason,
                    "reason",
                )
            ),
        )

        self._devices[
            device_id
        ] = updated

        return updated

    def rotate_key_epoch(
        self,
        device_id: str,
    ) -> RegisteredDevice:
        device = self.get(
            device_id
        )

        if device.revoked:
            raise DeviceRevoked(
                device_id
            )

        updated = replace(
            device,
            key_epoch=(
                device.key_epoch
                + 1
            ),
        )

        self._devices[
            device_id
        ] = updated

        return updated


# ============================================================
# CLIENT PLATFORM MATRIX
# ============================================================


def default_platform_profiles(
) -> tuple[
    ClientPlatformProfile,
    ...
]:
    return (
        ClientPlatformProfile(
            platform=(
                DevicePlatform.IOS
            ),
            form_factor=(
                FormFactor.PHONE
            ),
            min_supported_version=(
                SemanticVersion.parse(
                    "1.0.0"
                )
            ),
            capabilities=(
                ClientCapabilities(
                    camera=True,
                    file_upload=True,
                    push_notifications=True,
                    biometric_auth=True,
                    passkeys=True,
                    offline_storage=True,
                    background_sync=True,
                    local_notifications=True,
                    secure_hardware=True,
                    stylus=False,
                    desktop_windows=False,
                )
            ),
        ),

        ClientPlatformProfile(
            platform=(
                DevicePlatform.IPADOS
            ),
            form_factor=(
                FormFactor.TABLET
            ),
            min_supported_version=(
                SemanticVersion.parse(
                    "1.0.0"
                )
            ),
            capabilities=(
                ClientCapabilities(
                    camera=True,
                    file_upload=True,
                    push_notifications=True,
                    biometric_auth=True,
                    passkeys=True,
                    offline_storage=True,
                    background_sync=True,
                    local_notifications=True,
                    secure_hardware=True,
                    stylus=True,
                    desktop_windows=False,
                )
            ),
        ),

        ClientPlatformProfile(
            platform=(
                DevicePlatform.ANDROID
            ),
            form_factor=(
                FormFactor.PHONE
            ),
            min_supported_version=(
                SemanticVersion.parse(
                    "1.0.0"
                )
            ),
            capabilities=(
                ClientCapabilities(
                    camera=True,
                    file_upload=True,
                    push_notifications=True,
                    biometric_auth=True,
                    passkeys=True,
                    offline_storage=True,
                    background_sync=True,
                    local_notifications=True,
                    secure_hardware=True,
                    stylus=False,
                    desktop_windows=False,
                )
            ),
        ),

        ClientPlatformProfile(
            platform=(
                DevicePlatform.ANDROID
            ),
            form_factor=(
                FormFactor.TABLET
            ),
            min_supported_version=(
                SemanticVersion.parse(
                    "1.0.0"
                )
            ),
            capabilities=(
                ClientCapabilities(
                    camera=True,
                    file_upload=True,
                    push_notifications=True,
                    biometric_auth=True,
                    passkeys=True,
                    offline_storage=True,
                    background_sync=True,
                    local_notifications=True,
                    secure_hardware=True,
                    stylus=True,
                    desktop_windows=False,
                )
            ),
        ),

        ClientPlatformProfile(
            platform=(
                DevicePlatform.MACOS
            ),
            form_factor=(
                FormFactor.DESKTOP
            ),
            min_supported_version=(
                SemanticVersion.parse(
                    "1.0.0"
                )
            ),
            capabilities=(
                ClientCapabilities(
                    camera=True,
                    file_upload=True,
                    push_notifications=True,
                    biometric_auth=True,
                    passkeys=True,
                    offline_storage=True,
                    background_sync=True,
                    local_notifications=True,
                    secure_hardware=True,
                    stylus=False,
                    desktop_windows=True,
                )
            ),
        ),

        ClientPlatformProfile(
            platform=(
                DevicePlatform.WINDOWS
            ),
            form_factor=(
                FormFactor.DESKTOP
            ),
            min_supported_version=(
                SemanticVersion.parse(
                    "1.0.0"
                )
            ),
            capabilities=(
                ClientCapabilities(
                    camera=True,
                    file_upload=True,
                    push_notifications=True,
                    biometric_auth=True,
                    passkeys=True,
                    offline_storage=True,
                    background_sync=True,
                    local_notifications=True,
                    secure_hardware=True,
                    stylus=False,
                    desktop_windows=True,
                )
            ),
        ),

        ClientPlatformProfile(
            platform=(
                DevicePlatform.WEB
            ),
            form_factor=(
                FormFactor.BROWSER
            ),
            min_supported_version=(
                SemanticVersion.parse(
                    "1.0.0"
                )
            ),
            capabilities=(
                ClientCapabilities(
                    camera=True,
                    file_upload=True,
                    push_notifications=True,
                    biometric_auth=True,
                    passkeys=True,
                    offline_storage=True,
                    background_sync=True,
                    local_notifications=True,
                    secure_hardware=False,
                    stylus=False,
                    desktop_windows=False,
                )
            ),
        ),
    )


class ClientPlatformRegistry:
    def __init__(
        self,
        profiles: tuple[
            ClientPlatformProfile,
            ...
        ] | None = None,
    ) -> None:
        values = (
            profiles
            or default_platform_profiles()
        )

        self._profiles = {
            (
                profile.platform,
                profile.form_factor,
            ):
                profile
            for profile
            in values
        }

    def profile(
        self,
        *,
        platform: DevicePlatform,
        form_factor: FormFactor,
    ) -> ClientPlatformProfile:
        result = (
            self._profiles.get(
                (
                    platform,
                    form_factor,
                )
            )
        )

        if result is None:
            raise UnsupportedClient(
                (
                    f"{platform.value}/"
                    f"{form_factor.value}"
                )
            )

        return result

    def verify_client(
        self,
        device: RegisteredDevice,
    ) -> ClientPlatformProfile:
        profile = self.profile(
            platform=(
                device.platform
            ),
            form_factor=(
                device.form_factor
            ),
        )

        if (
            device.app_version
            < profile
            .min_supported_version
        ):
            raise UnsupportedClient(
                "client application version "
                "is below minimum supported version"
            )

        return profile

    def all_profiles(
        self,
    ) -> tuple[
        ClientPlatformProfile,
        ...
    ]:
        return tuple(
            self._profiles.values()
        )


# ============================================================
# AUTHORIZATION CAPABILITY GATE
# ============================================================


@dataclass(frozen=True)
class CapabilityPolicy:
    capability: str

    allowed_roles: frozenset[
        str
    ]

    allowed_surfaces: frozenset[
        ClientSurface
    ]

    min_auth: AuthStrength

    max_classification: (
        DataClassification
    )

    allow_offline: bool

    require_managed_device: bool = False
    require_attested_device: bool = False
    require_trusted_device: bool = False


@dataclass(frozen=True)
class SessionPrincipal:
    user_id: str
    tenant_id: str
    role: str
    surface: ClientSurface
    auth_strength: AuthStrength
    device_id: str


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    capability: str

    device_trust: (
        DeviceTrust
        | None
    )

    step_up_required: bool

    reasons: tuple[
        str,
        ...
    ]


def default_capability_policies(
) -> tuple[
    CapabilityPolicy,
    ...
]:
    executives = frozenset(
        {
            "president",
            "vice_president",
        }
    )

    all_internal = frozenset(
        {
            "president",
            "vice_president",
            "sales",
            "marketing",
            "estimator",
            "senior_estimator",
            "project_manager",
            "field",
            "finance",
            "security_admin",
        }
    )

    return (
        CapabilityPolicy(
            capability="crm.view",
            allowed_roles=(
                all_internal
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.EXECUTIVE,
                        ClientSurface.SALES,
                        ClientSurface.MARKETING,
                        ClientSurface.ESTIMATING,
                        ClientSurface.PROJECT_MANAGEMENT,
                    }
                )
            ),
            min_auth=(
                AuthStrength.MFA
            ),
            max_classification=(
                DataClassification
                .CONFIDENTIAL
            ),
            allow_offline=True,
        ),

        CapabilityPolicy(
            capability="crm.mutate",
            allowed_roles=(
                frozenset(
                    {
                        "president",
                        "vice_president",
                        "sales",
                        "marketing",
                        "estimator",
                        "senior_estimator",
                        "project_manager",
                    }
                )
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.EXECUTIVE,
                        ClientSurface.SALES,
                        ClientSurface.MARKETING,
                        ClientSurface.ESTIMATING,
                        ClientSurface.PROJECT_MANAGEMENT,
                    }
                )
            ),
            min_auth=(
                AuthStrength.MFA
            ),
            max_classification=(
                DataClassification
                .CONFIDENTIAL
            ),
            allow_offline=True,
        ),

        CapabilityPolicy(
            capability="estimating.view",
            allowed_roles=(
                frozenset(
                    {
                        "president",
                        "vice_president",
                        "estimator",
                        "senior_estimator",
                        "project_manager",
                    }
                )
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.EXECUTIVE,
                        ClientSurface.ESTIMATING,
                        ClientSurface.PROJECT_MANAGEMENT,
                    }
                )
            ),
            min_auth=(
                AuthStrength.MFA
            ),
            max_classification=(
                DataClassification
                .CONFIDENTIAL
            ),
            allow_offline=True,
        ),

        CapabilityPolicy(
            capability="estimating.approve",
            allowed_roles=(
                frozenset(
                    {
                        "president",
                        "vice_president",
                        "senior_estimator",
                    }
                )
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.EXECUTIVE,
                        ClientSurface.ESTIMATING,
                    }
                )
            ),
            min_auth=(
                AuthStrength.STEP_UP
            ),
            max_classification=(
                DataClassification
                .RESTRICTED
            ),
            allow_offline=False,
            require_attested_device=True,
            require_trusted_device=True,
        ),

        CapabilityPolicy(
            capability="project.field",
            allowed_roles=(
                frozenset(
                    {
                        "president",
                        "vice_president",
                        "project_manager",
                        "field",
                    }
                )
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.EXECUTIVE,
                        ClientSurface.PROJECT_MANAGEMENT,
                        ClientSurface.FIELD,
                    }
                )
            ),
            min_auth=(
                AuthStrength.MFA
            ),
            max_classification=(
                DataClassification
                .CONFIDENTIAL
            ),
            allow_offline=True,
        ),

        CapabilityPolicy(
            capability="finance.view",
            allowed_roles=(
                executives
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.EXECUTIVE,
                        ClientSurface.FINANCE,
                    }
                )
            ),
            min_auth=(
                AuthStrength.PASSKEY
            ),
            max_classification=(
                DataClassification
                .FINANCIAL
            ),
            allow_offline=False,
            require_managed_device=True,
            require_attested_device=True,
            require_trusted_device=True,
        ),

        CapabilityPolicy(
            capability="finance.mutate",
            allowed_roles=(
                executives
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.EXECUTIVE,
                        ClientSurface.FINANCE,
                    }
                )
            ),
            min_auth=(
                AuthStrength.STEP_UP
            ),
            max_classification=(
                DataClassification
                .FINANCIAL
            ),
            allow_offline=False,
            require_managed_device=True,
            require_attested_device=True,
            require_trusted_device=True,
        ),

        CapabilityPolicy(
            capability="security.admin",
            allowed_roles=(
                frozenset(
                    {
                        "president",
                        "security_admin",
                    }
                )
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.SECURITY,
                        ClientSurface.EXECUTIVE,
                    }
                )
            ),
            min_auth=(
                AuthStrength.STEP_UP
            ),
            max_classification=(
                DataClassification
                .RESTRICTED
            ),
            allow_offline=False,
            require_managed_device=True,
            require_attested_device=True,
            require_trusted_device=True,
        ),

        CapabilityPolicy(
            capability="client.portal",
            allowed_roles=(
                frozenset(
                    {
                        "client",
                    }
                )
            ),
            allowed_surfaces=(
                frozenset(
                    {
                        ClientSurface.CLIENT_PORTAL,
                    }
                )
            ),
            min_auth=(
                AuthStrength.MFA
            ),
            max_classification=(
                DataClassification
                .CONFIDENTIAL
            ),
            allow_offline=False,
        ),
    )


class RuntimeCapabilityGate:
    def __init__(
        self,
        *,
        devices: DeviceRegistry,
        client_registry: (
            ClientPlatformRegistry
            | None
        ) = None,
        trust_engine: (
            DeviceTrustEngine
            | None
        ) = None,
        policies: tuple[
            CapabilityPolicy,
            ...
        ] | None = None,
    ) -> None:
        self.devices = devices

        self.client_registry = (
            client_registry
            or ClientPlatformRegistry()
        )

        self.trust_engine = (
            trust_engine
            or DeviceTrustEngine()
        )

        self._policies = {
            policy.capability:
                policy
            for policy
            in (
                policies
                or default_capability_policies()
            )
        }

    def policy(
        self,
        capability: str,
    ) -> CapabilityPolicy:
        policy = (
            self._policies.get(
                capability
            )
        )

        if policy is None:
            raise PlatformAccessDenied(
                (
                    "unknown capability: "
                    + capability
                )
            )

        return policy

    def authorize(
        self,
        *,
        principal: SessionPrincipal,
        capability: str,
        classification: (
            DataClassification
        ),
        online: bool,
    ) -> CapabilityDecision:
        policy = self.policy(
            capability
        )

        reasons = []

        device = self.devices.get(
            principal.device_id
        )

        try:
            self.client_registry.verify_client(
                device
            )

        except UnsupportedClient as exc:
            return CapabilityDecision(
                allowed=False,
                capability=capability,
                device_trust=None,
                step_up_required=False,
                reasons=(
                    str(exc),
                ),
            )

        if (
            device.tenant_id
            != principal.tenant_id
        ):
            reasons.append(
                "device tenant mismatch"
            )

        if (
            device.user_id
            != principal.user_id
        ):
            reasons.append(
                "device principal mismatch"
            )

        trust = (
            self.trust_engine
            .assess(
                device
            )
        )

        if (
            trust.trust
            == DeviceTrust.BLOCKED
        ):
            reasons.append(
                "device trust is blocked"
            )

        role = (
            principal.role
            .strip()
            .lower()
        )

        if (
            role
            not in policy
            .allowed_roles
        ):
            reasons.append(
                "role is not authorized"
            )

        if (
            principal.surface
            not in policy
            .allowed_surfaces
        ):
            reasons.append(
                "client surface is not authorized"
            )

        if (
            classification
            > policy
            .max_classification
        ):
            reasons.append(
                "data classification exceeds capability policy"
            )

        if (
            not online
            and not policy
            .allow_offline
        ):
            reasons.append(
                "capability requires online connection"
            )

        if (
            policy
            .require_managed_device
            and not device.managed
        ):
            reasons.append(
                "managed device required"
            )

        if (
            policy
            .require_attested_device
            and not device.attested
        ):
            reasons.append(
                "attested device required"
            )

        if (
            policy
            .require_trusted_device
            and trust.trust
            != DeviceTrust.TRUSTED
        ):
            reasons.append(
                "trusted device required"
            )

        step_up_required = (
            principal.auth_strength
            < policy.min_auth
        )

        if step_up_required:
            reasons.append(
                "stronger authentication required"
            )

        allowed = (
            not reasons
        )

        return CapabilityDecision(
            allowed=allowed,
            capability=capability,
            device_trust=(
                trust.trust
            ),
            step_up_required=(
                step_up_required
            ),
            reasons=tuple(
                reasons
            ),
        )

    def require(
        self,
        *,
        principal: SessionPrincipal,
        capability: str,
        classification: (
            DataClassification
        ),
        online: bool,
    ) -> CapabilityDecision:
        decision = self.authorize(
            principal=principal,
            capability=capability,
            classification=classification,
            online=online,
        )

        if not decision.allowed:
            raise PlatformAccessDenied(
                "; ".join(
                    decision.reasons
                )
            )

        return decision


# ============================================================
# CACHE SECURITY
# ============================================================


@dataclass(frozen=True)
class CachePolicy:
    classification: DataClassification

    disposition: CacheDisposition

    encryption_required: bool

    max_ttl_seconds: int

    wipe_on_logout: bool

    redact_system_backup: bool


def default_cache_policies(
) -> tuple[
    CachePolicy,
    ...
]:
    return (
        CachePolicy(
            classification=(
                DataClassification.PUBLIC
            ),
            disposition=(
                CacheDisposition.ALLOW
            ),
            encryption_required=False,
            max_ttl_seconds=(
                7 * 24 * 3600
            ),
            wipe_on_logout=False,
            redact_system_backup=False,
        ),

        CachePolicy(
            classification=(
                DataClassification.INTERNAL
            ),
            disposition=(
                CacheDisposition.ALLOW
            ),
            encryption_required=True,
            max_ttl_seconds=(
                72 * 3600
            ),
            wipe_on_logout=True,
            redact_system_backup=True,
        ),

        CachePolicy(
            classification=(
                DataClassification.CONFIDENTIAL
            ),
            disposition=(
                CacheDisposition.ALLOW
            ),
            encryption_required=True,
            max_ttl_seconds=(
                24 * 3600
            ),
            wipe_on_logout=True,
            redact_system_backup=True,
        ),

        CachePolicy(
            classification=(
                DataClassification.RESTRICTED
            ),
            disposition=(
                CacheDisposition.MEMORY_ONLY
            ),
            encryption_required=True,
            max_ttl_seconds=(
                15 * 60
            ),
            wipe_on_logout=True,
            redact_system_backup=True,
        ),

        CachePolicy(
            classification=(
                DataClassification.FINANCIAL
            ),
            disposition=(
                CacheDisposition.DENY
            ),
            encryption_required=True,
            max_ttl_seconds=0,
            wipe_on_logout=True,
            redact_system_backup=True,
        ),
    )


class SecureCachePolicyEngine:
    def __init__(
        self,
        policies: tuple[
            CachePolicy,
            ...
        ] | None = None,
    ) -> None:
        self._policies = {
            policy.classification:
                policy
            for policy
            in (
                policies
                or default_cache_policies()
            )
        }

    def policy(
        self,
        classification: (
            DataClassification
        ),
    ) -> CachePolicy:
        return self._policies[
            classification
        ]

    def can_persist_offline(
        self,
        classification: (
            DataClassification
        ),
    ) -> bool:
        return (
            self.policy(
                classification
            )
            .disposition
            == CacheDisposition.ALLOW
        )


# ============================================================
# OFFLINE MUTATION QUEUE
# ============================================================


@dataclass(frozen=True)
class SyncMutation:
    mutation_id: str

    tenant_id: str
    user_id: str
    device_id: str

    aggregate_type: str
    aggregate_id: str

    command: str

    base_version: int

    classification: DataClassification

    idempotency_key: str

    payload_json: str
    payload_digest: str

    state: SyncMutationState

    retry_count: int

    created_at: datetime
    updated_at: datetime

    server_version: int | None = None

    rejection_reason: str | None = None


class OfflineMutationQueue:
    def __init__(
        self,
        *,
        max_retries: int = 5,
        max_payload_bytes: int = (
            256 * 1024
        ),
    ) -> None:
        if max_retries < 0:
            raise ValueError(
                "max_retries cannot be negative"
            )

        if max_payload_bytes <= 0:
            raise ValueError(
                "max_payload_bytes must be positive"
            )

        self.max_retries = (
            max_retries
        )

        self.max_payload_bytes = (
            max_payload_bytes
        )

        self._mutations: dict[
            str,
            SyncMutation,
        ] = {}

        self._by_idempotency: dict[
            tuple[
                str,
                str,
            ],
            str,
        ] = {}

    def enqueue(
        self,
        *,
        tenant_id: str,
        user_id: str,
        device_id: str,
        aggregate_type: str,
        aggregate_id: str,
        command: str,
        base_version: int,
        classification: (
            DataClassification
        ),
        idempotency_key: str,
        payload: dict[
            str,
            Any,
        ],
    ) -> SyncMutation:
        if (
            classification
            >= DataClassification
            .RESTRICTED
        ):
            raise SyncQueueError(
                "restricted/financial mutations "
                "cannot be queued for offline persistence"
            )

        if base_version < 0:
            raise ValueError(
                "base_version cannot be negative"
            )

        payload_json = (
            _canonical_json(
                payload
            )
        )

        payload_size = len(
            payload_json.encode(
                "utf-8"
            )
        )

        if (
            payload_size
            > self.max_payload_bytes
        ):
            raise SyncQueueError(
                "offline mutation payload exceeds limit"
            )

        idempotency_key = (
            _required(
                idempotency_key,
                "idempotency_key",
            )
        )

        identity = (
            device_id,
            idempotency_key,
        )

        existing_id = (
            self._by_idempotency.get(
                identity
            )
        )

        if existing_id:
            existing = (
                self._mutations[
                    existing_id
                ]
            )

            expected_digest = (
                _hash(
                    {
                        "command":
                            command,
                        "aggregate_id":
                            aggregate_id,
                        "payload":
                            payload,
                        "base_version":
                            base_version,
                    }
                )
            )

            actual_digest = (
                _hash(
                    {
                        "command":
                            existing.command,
                        "aggregate_id":
                            existing.aggregate_id,
                        "payload":
                            json.loads(
                                existing
                                .payload_json
                            ),
                        "base_version":
                            existing.base_version,
                    }
                )
            )

            if not hmac.compare_digest(
                expected_digest,
                actual_digest,
            ):
                raise SyncQueueError(
                    "idempotency key reused "
                    "with different mutation"
                )

            return existing

        now = _now()

        mutation = SyncMutation(
            mutation_id=(
                _id(
                    "sync"
                )
            ),
            tenant_id=(
                _required(
                    tenant_id,
                    "tenant_id",
                )
            ),
            user_id=(
                _required(
                    user_id,
                    "user_id",
                )
            ),
            device_id=(
                _required(
                    device_id,
                    "device_id",
                )
            ),
            aggregate_type=(
                _required(
                    aggregate_type,
                    "aggregate_type",
                )
            ),
            aggregate_id=(
                _required(
                    aggregate_id,
                    "aggregate_id",
                )
            ),
            command=(
                _required(
                    command,
                    "command",
                )
            ),
            base_version=(
                base_version
            ),
            classification=(
                classification
            ),
            idempotency_key=(
                idempotency_key
            ),
            payload_json=(
                payload_json
            ),
            payload_digest=(
                _hash(
                    payload
                )
            ),
            state=(
                SyncMutationState
                .PENDING
            ),
            retry_count=0,
            created_at=now,
            updated_at=now,
        )

        self._mutations[
            mutation.mutation_id
        ] = mutation

        self._by_idempotency[
            identity
        ] = (
            mutation.mutation_id
        )

        return mutation

    def get(
        self,
        mutation_id: str,
    ) -> SyncMutation:
        result = (
            self._mutations.get(
                mutation_id
            )
        )

        if result is None:
            raise KeyError(
                mutation_id
            )

        return result

    def next_batch(
        self,
        *,
        tenant_id: str,
        device_id: str,
        limit: int = 50,
    ) -> tuple[
        SyncMutation,
        ...
    ]:
        if limit <= 0:
            raise ValueError(
                "limit must be positive"
            )

        eligible = [
            mutation
            for mutation
            in self._mutations
            .values()
            if (
                mutation.tenant_id
                == tenant_id
                and mutation.device_id
                == device_id
                and mutation.state
                in {
                    SyncMutationState.PENDING,
                    SyncMutationState.RETRY,
                }
            )
        ]

        eligible.sort(
            key=lambda item:
                (
                    item.created_at,
                    item.mutation_id,
                )
        )

        return tuple(
            eligible[
                :limit
            ]
        )

    def acknowledge(
        self,
        mutation_id: str,
        *,
        server_version: int,
    ) -> SyncMutation:
        mutation = self.get(
            mutation_id
        )

        if server_version < 0:
            raise ValueError(
                "server_version cannot be negative"
            )

        updated = replace(
            mutation,
            state=(
                SyncMutationState
                .ACKNOWLEDGED
            ),
            server_version=(
                server_version
            ),
            updated_at=_now(),
        )

        self._mutations[
            mutation_id
        ] = updated

        return updated

    def conflict(
        self,
        mutation_id: str,
        *,
        server_version: int,
        reason: str,
    ) -> SyncMutation:
        mutation = self.get(
            mutation_id
        )

        updated = replace(
            mutation,
            state=(
                SyncMutationState
                .CONFLICT
            ),
            server_version=(
                server_version
            ),
            rejection_reason=(
                _required(
                    reason,
                    "reason",
                )
            ),
            updated_at=_now(),
        )

        self._mutations[
            mutation_id
        ] = updated

        return updated

    def reject(
        self,
        mutation_id: str,
        *,
        reason: str,
    ) -> SyncMutation:
        mutation = self.get(
            mutation_id
        )

        updated = replace(
            mutation,
            state=(
                SyncMutationState
                .REJECTED
            ),
            rejection_reason=(
                _required(
                    reason,
                    "reason",
                )
            ),
            updated_at=_now(),
        )

        self._mutations[
            mutation_id
        ] = updated

        return updated

    def retry(
        self,
        mutation_id: str,
    ) -> SyncMutation:
        mutation = self.get(
            mutation_id
        )

        retry_count = (
            mutation.retry_count
            + 1
        )

        if (
            retry_count
            > self.max_retries
        ):
            return self.reject(
                mutation_id,
                reason=(
                    "maximum retry count exceeded"
                ),
            )

        updated = replace(
            mutation,
            state=(
                SyncMutationState.RETRY
            ),
            retry_count=(
                retry_count
            ),
            updated_at=_now(),
        )

        self._mutations[
            mutation_id
        ] = updated

        return updated


# ============================================================
# CONFLICT RESOLUTION
# ============================================================


@dataclass(frozen=True)
class ConflictResolution:
    disposition: ConflictDisposition

    policy: ConflictPolicy

    merged_document: (
        dict[
            str,
            Any,
        ]
        | None
    )

    overlapping_fields: tuple[
        str,
        ...
    ]

    reason: str


class DeterministicConflictResolver:
    def resolve(
        self,
        *,
        base_document: dict[
            str,
            Any,
        ],
        client_changes: dict[
            str,
            Any,
        ],
        server_changes: dict[
            str,
            Any,
        ],
        policy: ConflictPolicy,
        classification: (
            DataClassification
        ),
    ) -> ConflictResolution:
        client_fields = set(
            client_changes
        )

        server_fields = set(
            server_changes
        )

        overlap = tuple(
            sorted(
                client_fields
                & server_fields
            )
        )

        if (
            policy
            == ConflictPolicy
            .SERVER_WINS
        ):
            merged = dict(
                base_document
            )

            merged.update(
                client_changes
            )

            merged.update(
                server_changes
            )

            return ConflictResolution(
                disposition=(
                    ConflictDisposition
                    .RESOLVED
                ),
                policy=policy,
                merged_document=(
                    merged
                ),
                overlapping_fields=(
                    overlap
                ),
                reason=(
                    "server values win overlapping fields"
                ),
            )

        if (
            policy
            == ConflictPolicy
            .CLIENT_WINS
        ):
            if (
                classification
                >= DataClassification
                .RESTRICTED
            ):
                return ConflictResolution(
                    disposition=(
                        ConflictDisposition
                        .MANUAL_REVIEW
                    ),
                    policy=policy,
                    merged_document=None,
                    overlapping_fields=(
                        overlap
                    ),
                    reason=(
                        "client-wins is prohibited "
                        "for restricted data"
                    ),
                )

            merged = dict(
                base_document
            )

            merged.update(
                server_changes
            )

            merged.update(
                client_changes
            )

            return ConflictResolution(
                disposition=(
                    ConflictDisposition
                    .RESOLVED
                ),
                policy=policy,
                merged_document=(
                    merged
                ),
                overlapping_fields=(
                    overlap
                ),
                reason=(
                    "client values win overlapping fields"
                ),
            )

        if (
            policy
            == ConflictPolicy
            .MERGE_DISJOINT
        ):
            if overlap:
                return ConflictResolution(
                    disposition=(
                        ConflictDisposition
                        .MANUAL_REVIEW
                    ),
                    policy=policy,
                    merged_document=None,
                    overlapping_fields=(
                        overlap
                    ),
                    reason=(
                        "same fields changed on "
                        "client and server"
                    ),
                )

            merged = dict(
                base_document
            )

            merged.update(
                server_changes
            )

            merged.update(
                client_changes
            )

            return ConflictResolution(
                disposition=(
                    ConflictDisposition
                    .RESOLVED
                ),
                policy=policy,
                merged_document=(
                    merged
                ),
                overlapping_fields=(),
                reason=(
                    "non-overlapping field updates merged"
                ),
            )

        return ConflictResolution(
            disposition=(
                ConflictDisposition
                .MANUAL_REVIEW
            ),
            policy=policy,
            merged_document=None,
            overlapping_fields=(
                overlap
            ),
            reason=(
                "manual conflict review required"
            ),
        )


# ============================================================
# API VERSION NEGOTIATION
# ============================================================


class ApiVersionRegistry:
    def __init__(
        self,
        supported: tuple[
            str,
            ...
        ],
    ) -> None:
        if not supported:
            raise ValueError(
                "at least one API version required"
            )

        normalized = tuple(
            sorted(
                {
                    _required(
                        version,
                        "api_version",
                    )
                    for version
                    in supported
                }
            )
        )

        self.supported = (
            normalized
        )

    def negotiate(
        self,
        client_versions: tuple[
            str,
            ...
        ],
    ) -> str:
        common = sorted(
            set(
                client_versions
            )
            & set(
                self.supported
            ),
            reverse=True,
        )

        if not common:
            raise ApiVersionError(
                "client and server have "
                "no compatible API version"
            )

        return common[0]


# ============================================================
# REPLAY PROTECTION
# ============================================================


class ReplayProtector:
    def __init__(
        self,
        *,
        ttl_seconds: int = 300,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be positive"
            )

        self.ttl = timedelta(
            seconds=(
                ttl_seconds
            )
        )

        self._seen: dict[
            str,
            datetime,
        ] = {}

    def new_nonce(
        self,
    ) -> str:
        return secrets.token_urlsafe(
            32
        )

    def _purge(
        self,
        *,
        as_of: datetime,
    ) -> None:
        expired = [
            nonce
            for nonce, seen_at
            in self._seen.items()
            if (
                as_of
                - seen_at
                > self.ttl
            )
        ]

        for nonce in expired:
            self._seen.pop(
                nonce,
                None,
            )

    def accept(
        self,
        *,
        nonce: str,
        timestamp: datetime,
        as_of: datetime,
        max_clock_skew_seconds: int = 300,
    ) -> None:
        nonce = _required(
            nonce,
            "nonce",
        )

        timestamp = _aware(
            timestamp,
            "timestamp",
        )

        as_of = _aware(
            as_of,
            "as_of",
        )

        if (
            abs(
                (
                    as_of
                    - timestamp
                )
                .total_seconds()
            )
            > max_clock_skew_seconds
        ):
            raise ReplayDetected(
                "request timestamp outside "
                "accepted clock-skew window"
            )

        self._purge(
            as_of=as_of
        )

        if nonce in self._seen:
            raise ReplayDetected(
                "request nonce already used"
            )

        self._seen[
            nonce
        ] = as_of


# ============================================================
# API ENVELOPE
# ============================================================


@dataclass(frozen=True)
class ApiRequestEnvelope:
    request_id: str

    api_version: str

    tenant_id: str
    user_id: str
    device_id: str

    idempotency_key: str | None

    nonce: str

    timestamp: datetime

    payload_digest: str


@dataclass(frozen=True)
class ApiValidationResult:
    accepted: bool

    negotiated_version: str | None

    reasons: tuple[
        str,
        ...
    ]


class ApiBoundary:
    def __init__(
        self,
        *,
        versions: ApiVersionRegistry,
        replay: ReplayProtector,
        devices: DeviceRegistry,
    ) -> None:
        self.versions = versions
        self.replay = replay
        self.devices = devices

    def build_envelope(
        self,
        *,
        api_version: str,
        tenant_id: str,
        user_id: str,
        device_id: str,
        payload: Any,
        idempotency_key: str | None = None,
        timestamp: datetime | None = None,
        nonce: str | None = None,
    ) -> ApiRequestEnvelope:
        return ApiRequestEnvelope(
            request_id=(
                _id(
                    "req"
                )
            ),
            api_version=(
                api_version
            ),
            tenant_id=(
                tenant_id
            ),
            user_id=(
                user_id
            ),
            device_id=(
                device_id
            ),
            idempotency_key=(
                idempotency_key
            ),
            nonce=(
                nonce
                or self.replay
                .new_nonce()
            ),
            timestamp=(
                timestamp
                or _now()
            ),
            payload_digest=(
                _hash(
                    payload
                )
            ),
        )

    def validate(
        self,
        *,
        envelope: ApiRequestEnvelope,
        payload: Any,
        as_of: datetime,
    ) -> ApiValidationResult:
        reasons = []

        try:
            negotiated = (
                self.versions
                .negotiate(
                    (
                        envelope
                        .api_version,
                    )
                )
            )

        except ApiVersionError as exc:
            return ApiValidationResult(
                accepted=False,
                negotiated_version=None,
                reasons=(
                    str(exc),
                ),
            )

        try:
            device = self.devices.get(
                envelope.device_id
            )

        except DeviceNotFound:
            return ApiValidationResult(
                accepted=False,
                negotiated_version=(
                    negotiated
                ),
                reasons=(
                    "device not registered",
                ),
            )

        if device.revoked:
            reasons.append(
                "device revoked"
            )

        if (
            device.tenant_id
            != envelope.tenant_id
        ):
            reasons.append(
                "device tenant mismatch"
            )

        if (
            device.user_id
            != envelope.user_id
        ):
            reasons.append(
                "device user mismatch"
            )

        if not hmac.compare_digest(
            envelope.payload_digest,
            _hash(
                payload
            ),
        ):
            reasons.append(
                "payload integrity mismatch"
            )

        if not reasons:
            try:
                self.replay.accept(
                    nonce=(
                        envelope.nonce
                    ),
                    timestamp=(
                        envelope
                        .timestamp
                    ),
                    as_of=as_of,
                )

            except ReplayDetected as exc:
                reasons.append(
                    str(exc)
                )

        return ApiValidationResult(
            accepted=(
                not reasons
            ),
            negotiated_version=(
                negotiated
            ),
            reasons=tuple(
                reasons
            ),
        )


# ============================================================
# PUSH PRIVACY
# ============================================================


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str

    classification: (
        DataClassification
    )

    entity_type: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True)
class PushPresentation:
    visibility: (
        NotificationVisibility
    )

    title: str
    body: str

    include_entity_reference: bool


class PushPrivacyPolicy:
    def present(
        self,
        message: PushMessage,
        *,
        device_locked: bool,
    ) -> PushPresentation:
        if (
            message.classification
            >= DataClassification
            .RESTRICTED
        ):
            return PushPresentation(
                visibility=(
                    NotificationVisibility
                    .HIDDEN
                ),
                title="GOAT",
                body=(
                    "Open GOAT to view "
                    "a secure notification."
                ),
                include_entity_reference=False,
            )

        if (
            device_locked
            and message
            .classification
            >= DataClassification
            .CONFIDENTIAL
        ):
            return PushPresentation(
                visibility=(
                    NotificationVisibility
                    .GENERIC
                ),
                title="GOAT",
                body=(
                    "You have a new "
                    "company notification."
                ),
                include_entity_reference=False,
            )

        return PushPresentation(
            visibility=(
                NotificationVisibility
                .FULL
            ),
            title=(
                message.title
            ),
            body=(
                message.body
            ),
            include_entity_reference=True,
        )


# ============================================================
# TAMPER-EVIDENT PLATFORM AUDIT
# ============================================================


@dataclass(frozen=True)
class RuntimeAuditRecord:
    event_id: str

    sequence: int

    tenant_id: str
    actor_id: str
    device_id: str | None

    action: str

    occurred_at: datetime

    payload_digest: str

    previous_hash: str

    event_hash: str


class RuntimeAuditLog:
    def __init__(
        self,
    ) -> None:
        self._records: list[
            RuntimeAuditRecord
        ] = []

    def append(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action: str,
        payload: Any,
        device_id: str | None = None,
    ) -> RuntimeAuditRecord:
        sequence = (
            len(
                self._records
            )
            + 1
        )

        previous_hash = (
            self._records[-1]
            .event_hash
            if self._records
            else "GENESIS"
        )

        occurred_at = _now()

        payload_digest = (
            _hash(
                payload
            )
        )

        material = {
            "sequence":
                sequence,
            "tenant_id":
                tenant_id,
            "actor_id":
                actor_id,
            "device_id":
                device_id,
            "action":
                action,
            "occurred_at":
                occurred_at
                .isoformat(),
            "payload_digest":
                payload_digest,
            "previous_hash":
                previous_hash,
        }

        record = RuntimeAuditRecord(
            event_id=(
                _id(
                    "raudit"
                )
            ),
            sequence=sequence,
            tenant_id=(
                tenant_id
            ),
            actor_id=(
                actor_id
            ),
            device_id=(
                device_id
            ),
            action=action,
            occurred_at=(
                occurred_at
            ),
            payload_digest=(
                payload_digest
            ),
            previous_hash=(
                previous_hash
            ),
            event_hash=(
                _hash(
                    material
                )
            ),
        )

        self._records.append(
            record
        )

        return record

    def records(
        self,
    ) -> tuple[
        RuntimeAuditRecord,
        ...
    ]:
        return tuple(
            self._records
        )

    def verify(
        self,
    ) -> bool:
        previous = "GENESIS"

        for expected_sequence, record in enumerate(
            self._records,
            1,
        ):
            if (
                record.sequence
                != expected_sequence
            ):
                raise AuditIntegrityError(
                    "audit sequence mismatch"
                )

            if (
                record.previous_hash
                != previous
            ):
                raise AuditIntegrityError(
                    "audit chain mismatch"
                )

            material = {
                "sequence":
                    record.sequence,
                "tenant_id":
                    record.tenant_id,
                "actor_id":
                    record.actor_id,
                "device_id":
                    record.device_id,
                "action":
                    record.action,
                "occurred_at":
                    record
                    .occurred_at
                    .isoformat(),
                "payload_digest":
                    record
                    .payload_digest,
                "previous_hash":
                    record
                    .previous_hash,
            }

            expected_hash = (
                _hash(
                    material
                )
            )

            if not hmac.compare_digest(
                expected_hash,
                record.event_hash,
            ):
                raise AuditIntegrityError(
                    "audit event hash mismatch"
                )

            previous = (
                record.event_hash
            )

        return True


# ============================================================
# UNIVERSAL RUNTIME MANIFEST
# ============================================================


@dataclass(frozen=True)
class UniversalRuntimeManifest:
    product_name: str

    supported_platforms: tuple[
        DevicePlatform,
        ...
    ]

    supports_offline_sync: bool

    supports_passkeys: bool

    supports_device_attestation: bool

    supports_push_privacy: bool

    supports_tenant_isolation: bool

    supports_replay_protection: bool

    supports_conflict_resolution: bool

    supports_revocation: bool

    finance_offline_allowed: bool

    restricted_offline_mutations_allowed: bool


def universal_runtime_manifest(
) -> UniversalRuntimeManifest:
    return UniversalRuntimeManifest(
        product_name="GOAT OS",
        supported_platforms=(
            DevicePlatform.IOS,
            DevicePlatform.IPADOS,
            DevicePlatform.ANDROID,
            DevicePlatform.MACOS,
            DevicePlatform.WINDOWS,
            DevicePlatform.WEB,
        ),
        supports_offline_sync=True,
        supports_passkeys=True,
        supports_device_attestation=True,
        supports_push_privacy=True,
        supports_tenant_isolation=True,
        supports_replay_protection=True,
        supports_conflict_resolution=True,
        supports_revocation=True,
        finance_offline_allowed=False,
        restricted_offline_mutations_allowed=False,
    )
