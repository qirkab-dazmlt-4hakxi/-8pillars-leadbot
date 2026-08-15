from __future__ import annotations

import math
import time
import uuid

from collections import deque
from dataclasses import dataclass
from enum import Enum


class VoiceError(RuntimeError):
    pass


class InvalidVoiceTransition(
    VoiceError
):
    pass


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    CLOSED = "closed"


@dataclass(frozen=True)
class VoiceTurn:
    turn_id: str
    sequence: int
    state: VoiceState
    interrupted_response_id: (
        str
        | None
    ) = None


class VoiceTurnController:
    """
    Provider-independent conversational turn controller.

    Explicit barge-in prevents the UI from waiting for an AI response to
    finish before the user can speak again.
    """

    def __init__(
        self,
    ) -> None:
        self._sequence = 0

        self._state = (
            VoiceState.IDLE
        )

        self._turn_id = None

        self._active_response_id = None

        self._interrupted_response_id = None

    @property
    def state(
        self,
    ) -> VoiceState:
        return self._state

    def _snapshot(
        self,
    ) -> VoiceTurn:
        return VoiceTurn(
            turn_id=(
                self._turn_id
                or ""
            ),
            sequence=(
                self._sequence
            ),
            state=(
                self._state
            ),
            interrupted_response_id=(
                self
                ._interrupted_response_id
            ),
        )

    def begin_listening(
        self,
    ) -> VoiceTurn:
        if (
            self._state
            not in {
                VoiceState.IDLE,
                VoiceState.INTERRUPTED,
            }
        ):
            raise InvalidVoiceTransition(
                (
                    "cannot begin listening from "
                    + self._state.value
                )
            )

        self._sequence += 1

        self._turn_id = (
            "turn_"
            + uuid.uuid4().hex
        )

        self._active_response_id = None
        self._interrupted_response_id = None

        self._state = (
            VoiceState.LISTENING
        )

        return self._snapshot()

    def end_user_turn(
        self,
    ) -> VoiceTurn:
        if (
            self._state
            != VoiceState.LISTENING
        ):
            raise InvalidVoiceTransition(
                "user turn not currently listening"
            )

        self._state = (
            VoiceState.THINKING
        )

        return self._snapshot()

    def begin_response(
        self,
        *,
        response_id: str,
    ) -> VoiceTurn:
        if (
            self._state
            != VoiceState.THINKING
        ):
            raise InvalidVoiceTransition(
                (
                    "response cannot begin from "
                    + self._state.value
                )
            )

        self._active_response_id = (
            response_id
        )

        self._state = (
            VoiceState.SPEAKING
        )

        return self._snapshot()

    def barge_in(
        self,
    ) -> VoiceTurn:
        if (
            self._state
            not in {
                VoiceState.SPEAKING,
                VoiceState.THINKING,
            }
        ):
            raise InvalidVoiceTransition(
                (
                    "barge-in unavailable from "
                    + self._state.value
                )
            )

        self._interrupted_response_id = (
            self._active_response_id
        )

        self._state = (
            VoiceState.INTERRUPTED
        )

        return self._snapshot()

    def complete_response(
        self,
    ) -> VoiceTurn:
        if (
            self._state
            != VoiceState.SPEAKING
        ):
            raise InvalidVoiceTransition(
                (
                    "response not currently speaking"
                )
            )

        self._state = (
            VoiceState.IDLE
        )

        self._active_response_id = None

        return self._snapshot()

    def close(
        self,
    ) -> VoiceTurn:
        self._state = (
            VoiceState.CLOSED
        )

        self._active_response_id = None

        return self._snapshot()


class AudioRingBuffer:
    def __init__(
        self,
        *,
        max_bytes: int = (
            2 * 1024 * 1024
        ),
    ) -> None:
        if max_bytes <= 0:
            raise ValueError(
                "max_bytes must be positive"
            )

        self.max_bytes = (
            max_bytes
        )

        self._chunks = deque()

        self._size = 0

    @property
    def size_bytes(
        self,
    ) -> int:
        return self._size

    def append(
        self,
        data: bytes,
    ) -> None:
        if not isinstance(
            data,
            bytes,
        ):
            raise TypeError(
                "audio data must be bytes"
            )

        if len(data) > self.max_bytes:
            data = data[
                -self.max_bytes:
            ]

        self._chunks.append(
            data
        )

        self._size += len(
            data
        )

        while (
            self._size
            > self.max_bytes
            and self._chunks
        ):
            removed = (
                self._chunks
                .popleft()
            )

            self._size -= len(
                removed
            )

    def bytes(
        self,
    ) -> bytes:
        return b"".join(
            self._chunks
        )

    def clear(
        self,
    ) -> None:
        self._chunks.clear()
        self._size = 0


@dataclass(frozen=True)
class VoiceLatency:
    speech_end_to_first_token_ms: (
        float
        | None
    )

    speech_end_to_first_audio_ms: (
        float
        | None
    )

    total_turn_ms: (
        float
        | None
    )


class VoiceLatencyTracker:
    def __init__(
        self,
    ) -> None:
        self.reset()

    def reset(
        self,
    ) -> None:
        self.started = None
        self.speech_end = None
        self.first_token = None
        self.first_audio = None
        self.completed = None

    def mark_start(
        self,
    ) -> None:
        self.started = (
            time.perf_counter()
        )

    def mark_speech_end(
        self,
    ) -> None:
        self.speech_end = (
            time.perf_counter()
        )

    def mark_first_token(
        self,
    ) -> None:
        if self.first_token is None:
            self.first_token = (
                time.perf_counter()
            )

    def mark_first_audio(
        self,
    ) -> None:
        if self.first_audio is None:
            self.first_audio = (
                time.perf_counter()
            )

    def mark_complete(
        self,
    ) -> None:
        self.completed = (
            time.perf_counter()
        )

    @staticmethod
    def _ms(
        start: float | None,
        end: float | None,
    ) -> float | None:
        if (
            start is None
            or end is None
        ):
            return None

        return (
            end - start
        ) * 1000.0

    def snapshot(
        self,
    ) -> VoiceLatency:
        return VoiceLatency(
            speech_end_to_first_token_ms=(
                self._ms(
                    self.speech_end,
                    self.first_token,
                )
            ),
            speech_end_to_first_audio_ms=(
                self._ms(
                    self.speech_end,
                    self.first_audio,
                )
            ),
            total_turn_ms=(
                self._ms(
                    self.started,
                    self.completed,
                )
            ),
        )


@dataclass(frozen=True)
class RealtimeVoicePolicy:
    model: str
    voice: str

    instructions: str

    turn_detection: str = (
        "server_vad"
    )

    interrupt_response: bool = True

    language: str | None = "en"

    speed: float = 1.0

    near_field: bool = True

    max_output_tokens: int = 2048

    def __post_init__(
        self,
    ) -> None:
        if not (
            0.25
            <= self.speed
            <= 1.5
        ):
            raise ValueError(
                "voice speed must be 0.25..1.5"
            )

        if (
            self.max_output_tokens
            <= 0
        ):
            raise ValueError(
                "max_output_tokens must be positive"
            )

        if (
            self.turn_detection
            not in {
                "server_vad",
                "semantic_vad",
            }
        ):
            raise ValueError(
                "unsupported turn detection"
            )

    def session_config(
        self,
    ) -> dict:
        audio_input = {
            "noise_reduction": {
                "type": (
                    "near_field"
                    if self.near_field
                    else "far_field"
                )
            },
            "turn_detection": {
                "type":
                    self.turn_detection,
                "interrupt_response":
                    self.interrupt_response,
            },
        }

        if self.language:
            audio_input[
                "transcription"
            ] = {
                "language":
                    self.language
            }

        return {
            "type":
                "realtime",
            "model":
                self.model,
            "instructions":
                self.instructions,
            "max_output_tokens":
                self.max_output_tokens,
            "output_modalities":
                [
                    "audio"
                ],
            "audio": {
                "input":
                    audio_input,
                "output": {
                    "voice":
                        self.voice,
                    "speed":
                        self.speed,
                },
            },
        }
