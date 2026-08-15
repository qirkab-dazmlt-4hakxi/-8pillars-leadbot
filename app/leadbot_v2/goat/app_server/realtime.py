from __future__ import annotations

import math
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from leadbot_v2.goat.gateway import (
    AuthStrength,
    DeviceBlocked,
    DeviceSignals,
    DeviceTrustEngine,
    SessionClaims,
    SessionTokenService,
    StepUpRequired,
)

from .contracts import (
    RealtimeProtocolError,
)

from .observability import (
    MetricsRegistry,
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


class VoiceSessionState(
    str,
    Enum,
):
    CONNECTING = "connecting"
    READY = "ready"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    CLOSED = "closed"


class ClientFrameType(
    str,
    Enum,
):
    HEARTBEAT = "heartbeat"
    INPUT_AUDIO = "input_audio"
    INPUT_TEXT = "input_text"
    COMMIT_TURN = "commit_turn"
    INTERRUPT = "interrupt"
    CLOSE = "close"


class ServerEventType(
    str,
    Enum,
):
    SESSION_READY = "session_ready"
    HEARTBEAT_ACK = "heartbeat_ack"
    AUDIO_ACK = "audio_ack"
    TURN_STARTED = "turn_started"
    TRANSCRIPT = "transcript"
    ASSISTANT_TEXT = "assistant_text"
    ASSISTANT_AUDIO = "assistant_audio"
    INTERRUPTED = "interrupted"
    TURN_FINISHED = "turn_finished"
    ERROR = "error"
    CLOSED = "closed"


class AudioEncoding(
    str,
    Enum,
):
    PCM16_16000_MONO = (
        "pcm16_16000_mono"
    )

    PCM16_24000_MONO = (
        "pcm16_24000_mono"
    )

    OPUS = "opus"


@dataclass(frozen=True)
class RealtimeHandshake:
    tenant_id: str

    bearer_token: str

    device: DeviceSignals

    audio_encoding: AudioEncoding = (
        AudioEncoding
        .PCM16_24000_MONO
    )


@dataclass(frozen=True)
class VoiceClientFrame:
    sequence: int

    frame_type: ClientFrameType

    audio: bytes | None = None

    text: str | None = None

    client_timestamp_ms: int | None = None


@dataclass(frozen=True)
class VoiceServerEvent:
    sequence: int

    event_type: ServerEventType

    session_id: str

    turn_id: str | None

    payload: dict[
        str,
        Any,
    ]

    occurred_at: datetime


@dataclass
class RealtimeVoiceSession:
    session_id: str

    claims: SessionClaims

    device: DeviceSignals

    audio_encoding: AudioEncoding

    state: VoiceSessionState

    expected_client_sequence: int = 1

    next_server_sequence: int = 1

    current_turn_id: str | None = None

    audio_bytes_received: int = 0

    audio_frames_received: int = 0

    text_turns_received: int = 0

    created_at: datetime = field(
        default_factory=_now
    )

    last_activity_at: datetime = field(
        default_factory=_now
    )

    closed_at: datetime | None = None


class RealtimeVoiceEngine:
    """
    GOAT-owned realtime session and voice transport state machine.

    Intelligence providers remain replaceable behind the GOAT
    Intelligence Fabric. This component controls transport integrity,
    sequencing, interruption, device/session trust and turn state.
    """

    def __init__(
        self,
        *,
        sessions: SessionTokenService,
        metrics: MetricsRegistry | None = None,
        maximum_audio_frame_bytes: int = 64 * 1024,
        minimum_auth_strength: AuthStrength = (
            AuthStrength.MFA
        ),
    ) -> None:
        self.sessions = (
            sessions
        )

        self.metrics = (
            metrics
            or MetricsRegistry()
        )

        self.maximum_audio_frame_bytes = (
            int(
                maximum_audio_frame_bytes
            )
        )

        if (
            self.maximum_audio_frame_bytes
            <= 0
        ):
            raise ValueError(
                "maximum audio frame must be positive"
            )

        self.minimum_auth_strength = (
            minimum_auth_strength
        )

        self._sessions = {}

    def session(
        self,
        session_id: str,
    ) -> RealtimeVoiceSession:
        try:
            return self._sessions[
                session_id
            ]

        except KeyError as exc:
            raise RealtimeProtocolError(
                "unknown realtime session"
            ) from exc

    def _event(
        self,
        session: RealtimeVoiceSession,
        event_type: ServerEventType,
        payload: dict[
            str,
            Any,
        ] | None = None,
    ) -> VoiceServerEvent:
        event = VoiceServerEvent(
            sequence=(
                session
                .next_server_sequence
            ),
            event_type=event_type,
            session_id=(
                session.session_id
            ),
            turn_id=(
                session
                .current_turn_id
            ),
            payload=dict(
                payload
                or {}
            ),
            occurred_at=_now(),
        )

        session.next_server_sequence += 1

        return event

    def open(
        self,
        handshake: RealtimeHandshake,
    ) -> tuple[
        RealtimeVoiceSession,
        VoiceServerEvent,
    ]:
        claims = (
            self.sessions.verify(
                handshake
                .bearer_token
            )
        )

        if (
            claims.tenant_id
            != handshake.tenant_id
        ):
            raise RealtimeProtocolError(
                "tenant boundary violation"
            )

        if (
            claims.device_id
            != handshake
            .device
            .device_id
        ):
            raise RealtimeProtocolError(
                "session device mismatch"
            )

        if (
            claims.auth_strength
            < self.minimum_auth_strength
        ):
            raise StepUpRequired(
                "realtime session requires stronger authentication"
            )

        trust = (
            DeviceTrustEngine.assess(
                handshake.device
            )
        )

        if trust.blocked:
            raise DeviceBlocked(
                ",".join(
                    trust.reasons
                )
            )

        session = (
            RealtimeVoiceSession(
                session_id=_id(
                    "voice"
                ),
                claims=claims,
                device=(
                    handshake.device
                ),
                audio_encoding=(
                    handshake
                    .audio_encoding
                ),
                state=(
                    VoiceSessionState
                    .READY
                ),
            )
        )

        self._sessions[
            session.session_id
        ] = session

        self.metrics.increment(
            "voice.sessions.opened"
        )

        self.metrics.gauge(
            "voice.sessions.active",
            float(
                sum(
                    1
                    for item
                    in self
                    ._sessions
                    .values()
                    if item.state
                    != VoiceSessionState
                    .CLOSED
                )
            ),
        )

        ready = self._event(
            session,
            ServerEventType
            .SESSION_READY,
            {
                "tenant_id":
                    claims.tenant_id,
                "user_id":
                    claims.user_id,
                "audio_encoding":
                    session
                    .audio_encoding
                    .value,
                "device_trust_score":
                    trust.score,
            },
        )

        return (
            session,
            ready,
        )

    def _require_sequence(
        self,
        session: RealtimeVoiceSession,
        sequence: int,
    ) -> None:
        if sequence <= 0:
            raise RealtimeProtocolError(
                "sequence must be positive"
            )

        if (
            sequence
            != session
            .expected_client_sequence
        ):
            raise RealtimeProtocolError(
                (
                    "client sequence mismatch: "
                    f"expected="
                    f"{session.expected_client_sequence}, "
                    f"received={sequence}"
                )
            )

        session.expected_client_sequence += 1

    def receive(
        self,
        session_id: str,
        frame: VoiceClientFrame,
    ) -> tuple[
        VoiceServerEvent,
        ...
    ]:
        session = self.session(
            session_id
        )

        if (
            session.state
            == VoiceSessionState.CLOSED
        ):
            raise RealtimeProtocolError(
                "session closed"
            )

        self._require_sequence(
            session,
            frame.sequence,
        )

        session.last_activity_at = (
            _now()
        )

        if (
            frame.frame_type
            == ClientFrameType
            .HEARTBEAT
        ):
            return (
                self._event(
                    session,
                    ServerEventType
                    .HEARTBEAT_ACK,
                    {
                        "client_sequence":
                            frame.sequence
                    },
                ),
            )

        if (
            frame.frame_type
            == ClientFrameType
            .INPUT_AUDIO
        ):
            audio = (
                frame.audio
                or b""
            )

            if not audio:
                raise RealtimeProtocolError(
                    "audio frame empty"
                )

            if (
                len(audio)
                > self
                .maximum_audio_frame_bytes
            ):
                raise RealtimeProtocolError(
                    "audio frame too large"
                )

            events = []

            if (
                session.state
                == VoiceSessionState
                .SPEAKING
            ):
                session.state = (
                    VoiceSessionState
                    .INTERRUPTED
                )

                events.append(
                    self._event(
                        session,
                        ServerEventType
                        .INTERRUPTED,
                        {
                            "reason":
                                "barge_in"
                        },
                    )
                )

            if (
                session.current_turn_id
                is None
            ):
                session.current_turn_id = (
                    _id(
                        "turn"
                    )
                )

            session.state = (
                VoiceSessionState
                .LISTENING
            )

            session.audio_frames_received += 1

            session.audio_bytes_received += (
                len(audio)
            )

            self.metrics.increment(
                "voice.audio.frames"
            )

            self.metrics.increment(
                "voice.audio.bytes",
                len(audio),
            )

            events.append(
                self._event(
                    session,
                    ServerEventType
                    .AUDIO_ACK,
                    {
                        "client_sequence":
                            frame.sequence,
                        "bytes":
                            len(audio),
                    },
                )
            )

            return tuple(
                events
            )

        if (
            frame.frame_type
            == ClientFrameType
            .INPUT_TEXT
        ):
            text = str(
                frame.text
                or ""
            ).strip()

            if not text:
                raise RealtimeProtocolError(
                    "text frame empty"
                )

            if (
                len(text)
                > 20_000
            ):
                raise RealtimeProtocolError(
                    "text frame too large"
                )

            if (
                session.state
                == VoiceSessionState
                .SPEAKING
            ):
                interrupted = self._event(
                    session,
                    ServerEventType
                    .INTERRUPTED,
                    {
                        "reason":
                            "text_barge_in"
                    },
                )

            else:
                interrupted = None

            session.current_turn_id = (
                _id(
                    "turn"
                )
            )

            session.state = (
                VoiceSessionState
                .THINKING
            )

            session.text_turns_received += 1

            self.metrics.increment(
                "voice.text.turns"
            )

            started = self._event(
                session,
                ServerEventType
                .TURN_STARTED,
                {
                    "input_type":
                        "text",
                    "text":
                        text,
                },
            )

            if interrupted:
                return (
                    interrupted,
                    started,
                )

            return (
                started,
            )

        if (
            frame.frame_type
            == ClientFrameType
            .COMMIT_TURN
        ):
            if (
                session.state
                not in {
                    VoiceSessionState
                    .LISTENING,
                    VoiceSessionState
                    .READY,
                }
            ):
                raise RealtimeProtocolError(
                    (
                        "cannot commit turn "
                        f"from {session.state.value}"
                    )
                )

            if (
                session.current_turn_id
                is None
            ):
                session.current_turn_id = (
                    _id(
                        "turn"
                    )
                )

            session.state = (
                VoiceSessionState
                .THINKING
            )

            return (
                self._event(
                    session,
                    ServerEventType
                    .TURN_STARTED,
                    {
                        "input_type":
                            "audio",
                        "audio_frames":
                            session
                            .audio_frames_received,
                        "audio_bytes":
                            session
                            .audio_bytes_received,
                    },
                ),
            )

        if (
            frame.frame_type
            == ClientFrameType
            .INTERRUPT
        ):
            if (
                session.state
                in {
                    VoiceSessionState
                    .THINKING,
                    VoiceSessionState
                    .SPEAKING,
                }
            ):
                session.state = (
                    VoiceSessionState
                    .INTERRUPTED
                )

                self.metrics.increment(
                    "voice.interruptions"
                )

                return (
                    self._event(
                        session,
                        ServerEventType
                        .INTERRUPTED,
                        {
                            "reason":
                                "client_interrupt"
                        },
                    ),
                )

            return ()

        if (
            frame.frame_type
            == ClientFrameType.CLOSE
        ):
            return (
                self.close(
                    session_id,
                    reason="client_close",
                ),
            )

        raise RealtimeProtocolError(
            "unsupported frame type"
        )

    def transcript(
        self,
        session_id: str,
        *,
        text: str,
        final: bool,
    ) -> VoiceServerEvent:
        session = self.session(
            session_id
        )

        return self._event(
            session,
            ServerEventType.TRANSCRIPT,
            {
                "text":
                    str(text),
                "final":
                    bool(final),
            },
        )

    def assistant_text(
        self,
        session_id: str,
        *,
        text: str,
        final: bool = False,
    ) -> VoiceServerEvent:
        session = self.session(
            session_id
        )

        if (
            session.current_turn_id
            is None
        ):
            raise RealtimeProtocolError(
                "no active turn"
            )

        session.state = (
            VoiceSessionState.SPEAKING
        )

        return self._event(
            session,
            ServerEventType
            .ASSISTANT_TEXT,
            {
                "text":
                    str(text),
                "final":
                    bool(final),
            },
        )

    def assistant_audio(
        self,
        session_id: str,
        *,
        audio_bytes: int,
        chunk_index: int,
        final: bool,
    ) -> VoiceServerEvent:
        session = self.session(
            session_id
        )

        if (
            session.current_turn_id
            is None
        ):
            raise RealtimeProtocolError(
                "no active turn"
            )

        if audio_bytes < 0:
            raise RealtimeProtocolError(
                "audio byte count invalid"
            )

        session.state = (
            VoiceSessionState.SPEAKING
        )

        return self._event(
            session,
            ServerEventType
            .ASSISTANT_AUDIO,
            {
                "bytes":
                    int(audio_bytes),
                "chunk_index":
                    int(chunk_index),
                "final":
                    bool(final),
            },
        )

    def finish_turn(
        self,
        session_id: str,
    ) -> VoiceServerEvent:
        session = self.session(
            session_id
        )

        completed_turn = (
            session.current_turn_id
        )

        event = self._event(
            session,
            ServerEventType
            .TURN_FINISHED,
            {
                "turn_id":
                    completed_turn
            },
        )

        session.current_turn_id = None

        session.state = (
            VoiceSessionState.READY
        )

        session.audio_frames_received = 0

        session.audio_bytes_received = 0

        self.metrics.increment(
            "voice.turns.completed"
        )

        return event

    def close(
        self,
        session_id: str,
        *,
        reason: str,
    ) -> VoiceServerEvent:
        session = self.session(
            session_id
        )

        if (
            session.state
            != VoiceSessionState.CLOSED
        ):
            session.state = (
                VoiceSessionState.CLOSED
            )

            session.closed_at = (
                _now()
            )

            self.metrics.increment(
                "voice.sessions.closed"
            )

            self.metrics.gauge(
                "voice.sessions.active",
                float(
                    sum(
                        1
                        for item
                        in self
                        ._sessions
                        .values()
                        if item.state
                        != VoiceSessionState
                        .CLOSED
                    )
                ),
            )

        return self._event(
            session,
            ServerEventType.CLOSED,
            {
                "reason":
                    str(reason)
            },
        )
