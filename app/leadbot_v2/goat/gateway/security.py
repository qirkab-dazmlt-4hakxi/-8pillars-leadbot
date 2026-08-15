from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import time
import uuid

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum
from typing import Any, Callable


class GatewaySecurityError(RuntimeError):
    pass


class InvalidSession(GatewaySecurityError):
    pass


class SessionExpired(InvalidSession):
    pass


class SessionRevoked(InvalidSession):
    pass


class ReplayDetected(GatewaySecurityError):
    pass


class RateLimitExceeded(GatewaySecurityError):
    pass


class DeviceBlocked(GatewaySecurityError):
    pass


class StepUpRequired(GatewaySecurityError):
    pass


def utcnow() -> datetime:
    return datetime.now(
        timezone.utc
    )


def new_id(prefix: str) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def canonical_json(
    value: Any,
) -> str:
    def norm(item: Any) -> Any:
        if isinstance(item, Enum):
            return item.value

        if isinstance(item, datetime):
            return item.isoformat()

        if isinstance(item, dict):
            return {
                str(k): norm(v)
                for k, v
                in sorted(item.items())
            }

        if isinstance(
            item,
            (
                tuple,
                list,
                set,
                frozenset,
            ),
        ):
            return [
                norm(v)
                for v
                in item
            ]

        return item

    return json.dumps(
        norm(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def sha256_hex(
    value: Any,
) -> str:
    return hashlib.sha256(
        canonical_json(
            value
        ).encode("utf-8")
    ).hexdigest()


def _b64encode(
    raw: bytes,
) -> str:
    return (
        base64
        .urlsafe_b64encode(raw)
        .rstrip(b"=")
        .decode("ascii")
    )


def _b64decode(
    value: str,
) -> bytes:
    """
    Decode canonical unpadded Base64URL.

    Python's Base64 decoder accepts alternate encodings whose unused
    padding bits differ while decoding to identical bytes. For signed
    security tokens that malleability is undesirable: token text must
    have exactly one canonical representation.
    """

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            "base64url value must be text"
        )

    if not value:
        raise ValueError(
            "empty base64url value"
        )

    if "=" in value:
        raise ValueError(
            "padding is not permitted"
        )

    allowed = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789-_"
    )

    if any(
        char not in allowed
        for char
        in value
    ):
        raise ValueError(
            "invalid base64url character"
        )

    padding = (
        "="
        * (
            (4 - len(value) % 4)
            % 4
        )
    )

    raw = base64.urlsafe_b64decode(
        value + padding
    )

    canonical = _b64encode(
        raw
    )

    if not hmac.compare_digest(
        canonical,
        value,
    ):
        raise ValueError(
            "non-canonical base64url encoding"
        )

    return raw


class AuthStrength(IntEnum):
    PASSWORD = 10
    MFA = 20
    PASSKEY = 30
    HARDWARE_BOUND = 40


class DeviceTrustLevel(str, Enum):
    TRUSTED = "trusted"
    REVIEW = "review"
    STEP_UP = "step_up"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DeviceSignals:
    device_id: str
    platform: str

    known_device: bool = False
    attested: bool = False

    rooted_or_jailbroken: bool = False

    vpn_or_proxy: bool = False
    tor: bool = False
    public_network: bool = False

    impossible_travel: bool = False
    attestation_anomaly: bool = False

    clock_skew_seconds: int = 0

    app_version: str | None = None


@dataclass(frozen=True)
class DeviceTrustAssessment:
    score: int

    level: DeviceTrustLevel

    require_step_up: bool

    blocked: bool

    reasons: tuple[str, ...]


class DeviceTrustEngine:
    @staticmethod
    def assess(
        signals: DeviceSignals,
    ) -> DeviceTrustAssessment:
        score = 100

        reasons = []

        def subtract(
            points: int,
            reason: str,
        ) -> None:
            nonlocal score

            score -= points

            reasons.append(
                reason
            )

        if not signals.known_device:
            subtract(
                15,
                "unknown_device",
            )

        if not signals.attested:
            subtract(
                15,
                "device_not_attested",
            )

        if signals.rooted_or_jailbroken:
            subtract(
                35,
                "root_or_jailbreak_detected",
            )

        if signals.attestation_anomaly:
            subtract(
                35,
                "attestation_anomaly",
            )

        if signals.impossible_travel:
            subtract(
                30,
                "impossible_travel",
            )

        if signals.tor:
            subtract(
                25,
                "tor_network",
            )

        elif signals.vpn_or_proxy:
            subtract(
                8,
                "vpn_or_proxy",
            )

        if signals.public_network:
            subtract(
                5,
                "public_network",
            )

        if abs(
            int(
                signals.clock_skew_seconds
            )
        ) > 300:
            subtract(
                10,
                "excessive_clock_skew",
            )

        score = max(
            0,
            min(
                100,
                score,
            ),
        )

        if score < 40:
            level = (
                DeviceTrustLevel.BLOCKED
            )

        elif score < 65:
            level = (
                DeviceTrustLevel.STEP_UP
            )

        elif score < 85:
            level = (
                DeviceTrustLevel.REVIEW
            )

        else:
            level = (
                DeviceTrustLevel.TRUSTED
            )

        return DeviceTrustAssessment(
            score=score,
            level=level,
            require_step_up=(
                score < 85
            ),
            blocked=(
                score < 40
            ),
            reasons=tuple(
                reasons
            ),
        )


@dataclass(frozen=True)
class SessionClaims:
    session_id: str
    user_id: str
    tenant_id: str

    role: str

    device_id: str

    auth_strength: AuthStrength

    issued_at: datetime
    expires_at: datetime

    audience: str

    nonce: str


class SessionTokenService:
    """
    Signed GOAT server session envelope.

    This is NOT a replacement for WebAuthn/passkey verification.
    Passkey assertions should be verified by the authentication layer first;
    this service issues the resulting server-side GOAT session.
    """

    VERSION = "GOAT1"

    def __init__(
        self,
        *,
        secret: bytes,
        audience: str = "goat-api",
        max_lifetime: timedelta = timedelta(
            hours=12
        ),
    ) -> None:
        if len(secret) < 32:
            raise ValueError(
                "session secret must be >=32 bytes"
            )

        self.secret = secret

        self.audience = audience

        self.max_lifetime = (
            max_lifetime
        )

        self._revoked = set()

    def issue(
        self,
        *,
        user_id: str,
        tenant_id: str,
        role: str,
        device_id: str,
        auth_strength: AuthStrength,
        lifetime: timedelta = timedelta(
            hours=8
        ),
        now: datetime | None = None,
    ) -> tuple[
        str,
        SessionClaims,
    ]:
        now = (
            now
            or utcnow()
        )

        if (
            lifetime.total_seconds()
            <= 0
            or lifetime
            > self.max_lifetime
        ):
            raise ValueError(
                "invalid session lifetime"
            )

        claims = SessionClaims(
            session_id=new_id(
                "sess"
            ),
            user_id=str(
                user_id
            ),
            tenant_id=str(
                tenant_id
            ),
            role=str(
                role
            ).lower(),
            device_id=str(
                device_id
            ),
            auth_strength=(
                auth_strength
            ),
            issued_at=now,
            expires_at=(
                now
                + lifetime
            ),
            audience=(
                self.audience
            ),
            nonce=new_id(
                "nonce"
            ),
        )

        payload = {
            "sid":
                claims.session_id,
            "uid":
                claims.user_id,
            "tid":
                claims.tenant_id,
            "role":
                claims.role,
            "did":
                claims.device_id,
            "auth":
                int(
                    claims.auth_strength
                ),
            "iat":
                int(
                    claims.issued_at
                    .timestamp()
                ),
            "exp":
                int(
                    claims.expires_at
                    .timestamp()
                ),
            "aud":
                claims.audience,
            "nonce":
                claims.nonce,
        }

        encoded = _b64encode(
            canonical_json(
                payload
            ).encode("utf-8")
        )

        signing_input = (
            self.VERSION
            + "."
            + encoded
        ).encode("ascii")

        signature = hmac.new(
            self.secret,
            signing_input,
            hashlib.sha256,
        ).digest()

        token = (
            self.VERSION
            + "."
            + encoded
            + "."
            + _b64encode(
                signature
            )
        )

        return (
            token,
            claims,
        )

    def verify(
        self,
        token: str,
        *,
        now: datetime | None = None,
    ) -> SessionClaims:
        now = (
            now
            or utcnow()
        )

        try:
            version, encoded, sig = (
                token.split(
                    ".",
                    2,
                )
            )

        except ValueError as exc:
            raise InvalidSession(
                "invalid token format"
            ) from exc

        if version != self.VERSION:
            raise InvalidSession(
                "unsupported token version"
            )

        signing_input = (
            version
            + "."
            + encoded
        ).encode("ascii")

        expected = hmac.new(
            self.secret,
            signing_input,
            hashlib.sha256,
        ).digest()

        try:
            received = _b64decode(
                sig
            )

        except Exception as exc:
            raise InvalidSession(
                "invalid signature encoding"
            ) from exc

        if not hmac.compare_digest(
            expected,
            received,
        ):
            raise InvalidSession(
                "invalid token signature"
            )

        try:
            payload = json.loads(
                _b64decode(
                    encoded
                ).decode("utf-8")
            )

        except Exception as exc:
            raise InvalidSession(
                "invalid token payload"
            ) from exc

        if payload.get(
            "aud"
        ) != self.audience:
            raise InvalidSession(
                "invalid audience"
            )

        session_id = str(
            payload.get(
                "sid"
            )
            or ""
        )

        if session_id in self._revoked:
            raise SessionRevoked(
                session_id
            )

        expires = datetime.fromtimestamp(
            int(
                payload["exp"]
            ),
            tz=timezone.utc,
        )

        if now >= expires:
            raise SessionExpired(
                session_id
            )

        issued = datetime.fromtimestamp(
            int(
                payload["iat"]
            ),
            tz=timezone.utc,
        )

        if issued > (
            now
            + timedelta(
                minutes=5
            )
        ):
            raise InvalidSession(
                "token issued in future"
            )

        return SessionClaims(
            session_id=session_id,
            user_id=str(
                payload["uid"]
            ),
            tenant_id=str(
                payload["tid"]
            ),
            role=str(
                payload["role"]
            ).lower(),
            device_id=str(
                payload["did"]
            ),
            auth_strength=(
                AuthStrength(
                    int(
                        payload["auth"]
                    )
                )
            ),
            issued_at=issued,
            expires_at=expires,
            audience=str(
                payload["aud"]
            ),
            nonce=str(
                payload["nonce"]
            ),
        )

    def revoke(
        self,
        session_id: str,
    ) -> None:
        self._revoked.add(
            str(
                session_id
            )
        )


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

        self.ttl_seconds = (
            ttl_seconds
        )

        self._seen = {}

    def _prune(
        self,
        now: float,
    ) -> None:
        expired = [
            key
            for key, expires
            in self._seen.items()
            if expires <= now
        ]

        for key in expired:
            self._seen.pop(
                key,
                None,
            )

    def require_fresh(
        self,
        *,
        tenant_id: str,
        user_id: str,
        nonce: str,
        now_monotonic: float | None = None,
    ) -> None:
        now_value = (
            time.monotonic()
            if now_monotonic is None
            else float(
                now_monotonic
            )
        )

        self._prune(
            now_value
        )

        key = (
            str(
                tenant_id
            ),
            str(
                user_id
            ),
            str(
                nonce
            ),
        )

        if key in self._seen:
            raise ReplayDetected(
                nonce
            )

        self._seen[
            key
        ] = (
            now_value
            + self.ttl_seconds
        )


@dataclass
class _Bucket:
    tokens: float
    last_time: float


class TokenBucketRateLimiter:
    def __init__(
        self,
        *,
        capacity: int,
        refill_per_second: float,
        clock: Callable[
            [],
            float,
        ] = time.monotonic,
    ) -> None:
        if capacity <= 0:
            raise ValueError(
                "capacity must be positive"
            )

        if refill_per_second <= 0:
            raise ValueError(
                "refill rate must be positive"
            )

        self.capacity = float(
            capacity
        )

        self.refill_per_second = float(
            refill_per_second
        )

        self.clock = clock

        self._buckets = {}

    def require(
        self,
        key: str,
        *,
        cost: float = 1.0,
    ) -> None:
        if cost <= 0:
            raise ValueError(
                "cost must be positive"
            )

        now = float(
            self.clock()
        )

        bucket = self._buckets.get(
            key
        )

        if bucket is None:
            bucket = _Bucket(
                tokens=(
                    self.capacity
                ),
                last_time=now,
            )

            self._buckets[
                key
            ] = bucket

        elapsed = max(
            0.0,
            now
            - bucket.last_time,
        )

        bucket.tokens = min(
            self.capacity,
            (
                bucket.tokens
                + elapsed
                * self.refill_per_second
            ),
        )

        bucket.last_time = now

        if bucket.tokens < cost:
            raise RateLimitExceeded(
                key
            )

        bucket.tokens -= cost
