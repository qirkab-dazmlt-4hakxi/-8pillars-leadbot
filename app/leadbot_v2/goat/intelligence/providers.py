from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

from dataclasses import dataclass
from typing import Any, Callable

from .core import (
    ConversationMessage,
    ModelCapability,
    ModelDescriptor,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
    ProviderKind,
    ProviderUnavailable,
)


class ProviderTransportError(
    ProviderUnavailable
):
    pass


class HttpTransport:
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def post_json_bytes(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> bytes:
        raise NotImplementedError

    def post_multipart(
        self,
        *,
        url: str,
        headers: dict[str, str],
        fields: tuple[
            tuple[
                str,
                str,
                str,
            ],
            ...
        ],
        files: tuple[
            tuple[
                str,
                str,
                str,
                bytes,
            ],
            ...
        ],
        timeout: float,
        expect_json: bool,
    ) -> dict[str, Any] | str:
        raise NotImplementedError


class UrllibTransport(
    HttpTransport
):
    @staticmethod
    def _request(
        *,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> bytes:
        request = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers=headers,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:
                return response.read()

        except urllib.error.HTTPError as exc:
            detail = (
                exc.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

            raise ProviderTransportError(
                (
                    f"HTTP {exc.code}: "
                    f"{detail[:1000]}"
                )
            ) from exc

        except urllib.error.URLError as exc:
            raise ProviderTransportError(
                str(
                    exc.reason
                )
            ) from exc

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        final_headers = {
            **headers,
            "Content-Type":
                "application/json",
        }

        raw = self._request(
            url=url,
            headers=final_headers,
            body=json.dumps(
                payload
            ).encode(
                "utf-8"
            ),
            timeout=timeout,
        )

        result = json.loads(
            raw.decode(
                "utf-8"
            )
        )

        if not isinstance(
            result,
            dict,
        ):
            raise ProviderTransportError(
                "expected JSON object response"
            )

        return result

    def post_json_bytes(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> bytes:
        final_headers = {
            **headers,
            "Content-Type":
                "application/json",
        }

        return self._request(
            url=url,
            headers=final_headers,
            body=json.dumps(
                payload
            ).encode(
                "utf-8"
            ),
            timeout=timeout,
        )

    def post_multipart(
        self,
        *,
        url: str,
        headers: dict[str, str],
        fields: tuple[
            tuple[
                str,
                str,
                str,
            ],
            ...
        ],
        files: tuple[
            tuple[
                str,
                str,
                str,
                bytes,
            ],
            ...
        ],
        timeout: float,
        expect_json: bool,
    ) -> dict[str, Any] | str:
        boundary = (
            "----GOAT"
            + uuid.uuid4().hex
        )

        chunks = []

        for (
            name,
            value,
            content_type,
        ) in fields:
            chunks.extend(
                [
                    (
                        "--"
                        + boundary
                        + "\r\n"
                    ).encode(),
                    (
                        "Content-Disposition: "
                        f'form-data; name="{name}"'
                        "\r\n"
                    ).encode(),
                    (
                        "Content-Type: "
                        + content_type
                        + "\r\n\r\n"
                    ).encode(),
                    value.encode(
                        "utf-8"
                    ),
                    b"\r\n",
                ]
            )

        for (
            name,
            filename,
            content_type,
            data,
        ) in files:
            chunks.extend(
                [
                    (
                        "--"
                        + boundary
                        + "\r\n"
                    ).encode(),
                    (
                        "Content-Disposition: "
                        f'form-data; name="{name}"; '
                        f'filename="{filename}"'
                        "\r\n"
                    ).encode(),
                    (
                        "Content-Type: "
                        + content_type
                        + "\r\n\r\n"
                    ).encode(),
                    data,
                    b"\r\n",
                ]
            )

        chunks.append(
            (
                "--"
                + boundary
                + "--\r\n"
            ).encode()
        )

        body = b"".join(
            chunks
        )

        final_headers = {
            **headers,
            "Content-Type": (
                "multipart/form-data; "
                "boundary="
                + boundary
            ),
        }

        raw = self._request(
            url=url,
            headers=final_headers,
            body=body,
            timeout=timeout,
        )

        text = raw.decode(
            "utf-8",
            errors="replace",
        )

        if expect_json:
            result = json.loads(
                text
            )

            if not isinstance(
                result,
                dict,
            ):
                raise ProviderTransportError(
                    (
                        "expected JSON "
                        "multipart response"
                    )
                )

            return result

        return text


def _response_text(
    payload: dict[str, Any],
) -> str:
    direct = payload.get(
        "output_text"
    )

    if isinstance(
        direct,
        str,
    ):
        return direct

    fragments = []

    for item in (
        payload.get(
            "output"
        )
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            item.get("type")
            == "message"
        ):
            for content in (
                item.get(
                    "content"
                )
                or []
            ):
                if (
                    isinstance(
                        content,
                        dict,
                    )
                    and content.get(
                        "type"
                    )
                    in {
                        "output_text",
                        "text",
                    }
                ):
                    text = content.get(
                        "text"
                    )

                    if isinstance(
                        text,
                        str,
                    ):
                        fragments.append(
                            text
                        )

    return "\n".join(
        fragments
    )


def _tool_calls(
    payload: dict[str, Any],
) -> tuple[
    ModelToolCall,
    ...
]:
    result = []

    for item in (
        payload.get(
            "output"
        )
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            item.get("type")
            != "function_call"
        ):
            continue

        raw_arguments = (
            item.get(
                "arguments"
            )
            or "{}"
        )

        if isinstance(
            raw_arguments,
            str,
        ):
            try:
                arguments = json.loads(
                    raw_arguments
                )

            except json.JSONDecodeError:
                arguments = {
                    "_raw":
                        raw_arguments
                }

        elif isinstance(
            raw_arguments,
            dict,
        ):
            arguments = (
                raw_arguments
            )

        else:
            arguments = {}

        result.append(
            ModelToolCall(
                call_id=str(
                    item.get(
                        "call_id"
                    )
                    or item.get(
                        "id"
                    )
                    or uuid.uuid4()
                ),
                name=str(
                    item.get(
                        "name"
                    )
                    or ""
                ),
                arguments=(
                    arguments
                ),
            )
        )

    return tuple(
        result
    )


class OpenAIResponsesProvider(
    ModelProvider
):
    """
    Optional OpenAI Responses API engine.

    GOAT owns routing, memory, tools, authorization and company state.
    This adapter only performs model inference.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        provider_name: str = "openai",
        base_url: str = (
            "https://api.openai.com/v1"
        ),
        transport: HttpTransport | None = None,
        timeout: float = 90.0,
        quality_score: float = 0.95,
        expected_latency_ms: float = 1500.0,
        allow_restricted_data: bool = False,
    ) -> None:
        self.model = (
            str(model).strip()
        )

        if not self.model:
            raise ValueError(
                "model is required"
            )

        self.api_key = (
            api_key
            or os.environ.get(
                "OPENAI_API_KEY"
            )
        )

        self.provider_name = (
            provider_name
        )

        self.base_url = (
            base_url.rstrip(
                "/"
            )
        )

        self.transport = (
            transport
            or UrllibTransport()
        )

        self.timeout = timeout

        self._descriptor = (
            ModelDescriptor(
                provider_name=(
                    provider_name
                ),
                model_name=(
                    self.model
                ),
                provider_kind=(
                    ProviderKind.CLOUD
                ),
                capabilities=(
                    frozenset(
                        {
                            ModelCapability.TEXT,
                            ModelCapability.TOOLS,
                            ModelCapability.VISION,
                        }
                    )
                ),
                quality_score=(
                    quality_score
                ),
                expected_latency_ms=(
                    expected_latency_ms
                ),
                enabled=True,
                allow_restricted_data=(
                    allow_restricted_data
                ),
            )
        )

    @property
    def descriptor(
        self,
    ) -> ModelDescriptor:
        return self._descriptor

    def _headers(
        self,
    ) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailable(
                (
                    "OpenAI API key is not "
                    "configured server-side"
                )
            )

        return {
            "Authorization":
                (
                    "Bearer "
                    + self.api_key
                ),
            "X-Client-Request-Id":
                str(
                    uuid.uuid4()
                ),
        }

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        input_items = []

        for message in (
            request.messages
        ):
            if (
                message.role
                == "system"
            ):
                continue

            if (
                message.role
                == "tool"
            ):
                input_items.append(
                    {
                        "role":
                            "user",
                        "content":
                            (
                                "[TOOL RESULT "
                                + str(
                                    message.name
                                    or ""
                                )
                                + "] "
                                + message.content
                            ),
                    }
                )

            else:
                input_items.append(
                    {
                        "role":
                            message.role,
                        "content":
                            message.content,
                    }
                )

        system_parts = [
            item.content
            for item
            in request.messages
            if item.role
            == "system"
        ]

        if request.instructions:
            system_parts.insert(
                0,
                request.instructions,
            )

        payload = {
            "model":
                self.model,
            "input":
                input_items,
            "max_output_tokens":
                request.max_output_tokens,
            "store":
                False,
        }

        if system_parts:
            payload[
                "instructions"
            ] = "\n\n".join(
                system_parts
            )

        if request.tools:
            payload[
                "tools"
            ] = [
                {
                    "type":
                        "function",
                    "name":
                        tool.name,
                    "description":
                        tool.description,
                    "parameters":
                        tool.parameters,
                }
                for tool
                in request.tools
            ]

        started = (
            time.perf_counter()
        )

        response = (
            self.transport
            .post_json(
                url=(
                    self.base_url
                    + "/responses"
                ),
                headers=(
                    self._headers()
                ),
                payload=payload,
                timeout=(
                    self.timeout
                ),
            )
        )

        latency_ms = (
            (
                time.perf_counter()
                - started
            )
            * 1000.0
        )

        return ModelResponse(
            text=_response_text(
                response
            ),
            tool_calls=_tool_calls(
                response
            ),
            provider_name=(
                self.provider_name
            ),
            model_name=(
                self.model
            ),
            finish_reason=str(
                response.get(
                    "status"
                )
                or ""
            ),
            latency_ms=(
                latency_ms
            ),
        )


class LocalFunctionModelProvider(
    ModelProvider
):
    """
    Adapter for a GOAT-controlled local model runtime.

    The supplied callable can later wrap llama.cpp, vLLM, a private model
    server or another internally operated inference service.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        model_name: str,
        function: Callable[
            [ModelRequest],
            ModelResponse | str,
        ],
        capabilities: frozenset[
            ModelCapability
        ] = frozenset(
            {
                ModelCapability.TEXT,
                ModelCapability.TOOLS,
            }
        ),
        quality_score: float = 0.80,
        expected_latency_ms: float = 900.0,
    ) -> None:
        self.function = function

        self._descriptor = (
            ModelDescriptor(
                provider_name=(
                    provider_name
                ),
                model_name=(
                    model_name
                ),
                provider_kind=(
                    ProviderKind.LOCAL
                ),
                capabilities=(
                    capabilities
                ),
                quality_score=(
                    quality_score
                ),
                expected_latency_ms=(
                    expected_latency_ms
                ),
                enabled=True,
                allow_restricted_data=True,
            )
        )

    @property
    def descriptor(
        self,
    ) -> ModelDescriptor:
        return self._descriptor

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        started = (
            time.perf_counter()
        )

        value = self.function(
            request
        )

        elapsed = (
            (
                time.perf_counter()
                - started
            )
            * 1000.0
        )

        if isinstance(
            value,
            ModelResponse,
        ):
            return ModelResponse(
                text=value.text,
                tool_calls=(
                    value.tool_calls
                ),
                provider_name=(
                    self.descriptor
                    .provider_name
                ),
                model_name=(
                    self.descriptor
                    .model_name
                ),
                finish_reason=(
                    value.finish_reason
                ),
                latency_ms=(
                    elapsed
                ),
            )

        return ModelResponse(
            text=str(
                value
            ),
            provider_name=(
                self.descriptor
                .provider_name
            ),
            model_name=(
                self.descriptor
                .model_name
            ),
            latency_ms=elapsed,
        )


@dataclass(frozen=True)
class RealtimeCallResult:
    sdp_answer: str


class OpenAIRealtimeCallAdapter:
    """
    Server-side WebRTC bootstrap adapter.

    API credentials remain on the GOAT server. Mobile/web clients exchange
    SDP with GOAT rather than receiving the permanent provider key.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = (
            "https://api.openai.com/v1"
        ),
        transport: HttpTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get(
                "OPENAI_API_KEY"
            )
        )

        self.base_url = (
            base_url.rstrip(
                "/"
            )
        )

        self.transport = (
            transport
            or UrllibTransport()
        )

        self.timeout = timeout

    def _headers(
        self,
    ) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailable(
                "OpenAI API key not configured"
            )

        return {
            "Authorization":
                (
                    "Bearer "
                    + self.api_key
                ),
            "X-Client-Request-Id":
                str(
                    uuid.uuid4()
                ),
        }

    def create_webrtc_call(
        self,
        *,
        sdp_offer: str,
        model: str,
        instructions: str,
        voice: str | None = None,
        turn_detection: str = (
            "server_vad"
        ),
        interrupt_response: bool = True,
    ) -> RealtimeCallResult:
        session = {
            "type":
                "realtime",
            "model":
                model,
            "instructions":
                instructions,
            "output_modalities":
                [
                    "audio"
                ],
            "audio": {
                "input": {
                    "turn_detection": {
                        "type":
                            turn_detection,
                        "interrupt_response":
                            interrupt_response,
                    },
                },
                "output": {},
            },
        }

        if voice:
            session[
                "audio"
            ][
                "output"
            ][
                "voice"
            ] = voice

        response = (
            self.transport
            .post_multipart(
                url=(
                    self.base_url
                    + "/realtime/calls"
                ),
                headers=(
                    self._headers()
                ),
                fields=(
                    (
                        "sdp",
                        sdp_offer,
                        "application/sdp",
                    ),
                    (
                        "session",
                        json.dumps(
                            session
                        ),
                        "application/json",
                    ),
                ),
                files=(),
                timeout=(
                    self.timeout
                ),
                expect_json=False,
            )
        )

        if not isinstance(
            response,
            str,
        ):
            raise ProviderTransportError(
                "expected SDP text response"
            )

        return RealtimeCallResult(
            sdp_answer=response
        )


class OpenAIAudioAdapter:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = (
            "https://api.openai.com/v1"
        ),
        transport: HttpTransport | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get(
                "OPENAI_API_KEY"
            )
        )

        self.base_url = (
            base_url.rstrip(
                "/"
            )
        )

        self.transport = (
            transport
            or UrllibTransport()
        )

        self.timeout = timeout

    def _headers(
        self,
    ) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailable(
                "OpenAI API key not configured"
            )

        return {
            "Authorization":
                (
                    "Bearer "
                    + self.api_key
                ),
        }

    def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        model: str,
        mime_type: str = "audio/wav",
        language: str | None = None,
    ) -> str:
        fields = [
            (
                "model",
                model,
                "text/plain",
            )
        ]

        if language:
            fields.append(
                (
                    "language",
                    language,
                    "text/plain",
                )
            )

        response = (
            self.transport
            .post_multipart(
                url=(
                    self.base_url
                    + "/audio/transcriptions"
                ),
                headers=(
                    self._headers()
                ),
                fields=tuple(
                    fields
                ),
                files=(
                    (
                        "file",
                        filename,
                        mime_type,
                        audio,
                    ),
                ),
                timeout=(
                    self.timeout
                ),
                expect_json=True,
            )
        )

        if not isinstance(
            response,
            dict,
        ):
            raise ProviderTransportError(
                "invalid transcription response"
            )

        return str(
            response.get(
                "text"
            )
            or ""
        )

    def synthesize(
        self,
        *,
        text: str,
        model: str,
        voice: str,
        instructions: str | None = None,
    ) -> bytes:
        payload = {
            "model":
                model,
            "voice":
                voice,
            "input":
                text,
        }

        if instructions:
            payload[
                "instructions"
            ] = instructions

        return (
            self.transport
            .post_json_bytes(
                url=(
                    self.base_url
                    + "/audio/speech"
                ),
                headers=(
                    self._headers()
                ),
                payload=payload,
                timeout=(
                    self.timeout
                ),
            )
        )
