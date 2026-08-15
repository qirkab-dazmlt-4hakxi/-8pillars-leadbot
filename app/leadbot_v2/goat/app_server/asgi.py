from __future__ import annotations

import asyncio
import json
import struct
import traceback

from typing import Any

from leadbot_v2.goat.gateway import (
    AuthStrength,
    CrossPlatformSyncFeed,
    DeviceBlocked,
    DeviceSignals,
    GatewaySecurityError,
    SecureApplicationGateway,
    SessionTokenService,
)

from .contracts import (
    ApplicationServerError,
    BadRequest,
    HttpRequest,
    HttpResponse,
    PayloadTooLarge,
    RealtimeProtocolError,
    RouteNotFound,
    bearer_token,
    normalize_headers,
    parse_query_string,
)

from .observability import (
    MetricsRegistry,
)

from .realtime import (
    AudioEncoding,
    ClientFrameType,
    RealtimeHandshake,
    RealtimeVoiceEngine,
    ServerEventType,
    VoiceClientFrame,
    VoiceServerEvent,
)

from .runtime import (
    GOATApplicationServer,
)


class GOATASGIApp:
    """
    Dependency-free ASGI 3 application.

    It can run under any standards-compliant ASGI server.
    """

    def __init__(
        self,
        *,
        runtime: GOATApplicationServer,
        realtime: RealtimeVoiceEngine,
        maximum_http_body_bytes: int = (
            2
            * 1024
            * 1024
        ),
    ) -> None:
        self.runtime = runtime
        self.realtime = realtime

        self.maximum_http_body_bytes = (
            int(
                maximum_http_body_bytes
            )
        )

    async def __call__(
        self,
        scope,
        receive,
        send,
    ):
        scope_type = scope.get(
            "type"
        )

        if scope_type == "http":
            await self._http(
                scope,
                receive,
                send,
            )

            return

        if scope_type == "websocket":
            await self._websocket(
                scope,
                receive,
                send,
            )

            return

        raise RuntimeError(
            (
                "unsupported ASGI scope: "
                + str(
                    scope_type
                )
            )
        )

    async def _read_http_body(
        self,
        receive,
    ) -> bytes:
        chunks = []

        total = 0

        while True:
            message = await receive()

            if (
                message.get(
                    "type"
                )
                != "http.request"
            ):
                raise BadRequest(
                    "invalid ASGI HTTP event"
                )

            body = message.get(
                "body",
                b"",
            )

            total += len(
                body
            )

            if (
                total
                > self
                .maximum_http_body_bytes
            ):
                raise PayloadTooLarge(
                    "HTTP body exceeds limit"
                )

            chunks.append(
                body
            )

            if not message.get(
                "more_body",
                False,
            ):
                break

        return b"".join(
            chunks
        )

    @staticmethod
    def _error_response(
        exc: Exception,
    ) -> HttpResponse:
        from leadbot_v2.goat.gateway import (
            AuthorizationDenied,
            IdempotencyConflict,
            IdempotencyRequired,
            InvalidSession,
            RateLimitExceeded,
            ReplayDetected,
            StepUpRequired,
            TenantBoundaryViolation,
        )

        if isinstance(
            exc,
            RouteNotFound,
        ):
            status = 404
            code = "route_not_found"

        elif isinstance(
            exc,
            (
                InvalidSession,
                TenantBoundaryViolation,
            ),
        ):
            status = 401
            code = "unauthorized"

        elif isinstance(
            exc,
            (
                AuthorizationDenied,
                DeviceBlocked,
            ),
        ):
            status = 403
            code = "forbidden"

        elif isinstance(
            exc,
            StepUpRequired,
        ):
            status = 428
            code = "step_up_required"

        elif isinstance(
            exc,
            ReplayDetected,
        ):
            status = 409
            code = "replay_detected"

        elif isinstance(
            exc,
            IdempotencyConflict,
        ):
            status = 409
            code = "idempotency_conflict"

        elif isinstance(
            exc,
            IdempotencyRequired,
        ):
            status = 428
            code = "idempotency_required"

        elif isinstance(
            exc,
            RateLimitExceeded,
        ):
            status = 429
            code = "rate_limited"

        elif isinstance(
            exc,
            PayloadTooLarge,
        ):
            status = 413
            code = "payload_too_large"

        elif isinstance(
            exc,
            BadRequest,
        ):
            status = 400
            code = "bad_request"

        else:
            status = 500
            code = "internal_error"

        message = (
            str(exc)
            if status < 500
            else "internal server error"
        )

        return HttpResponse.json(
            status,
            {
                "error":
                    code,
                "message":
                    message,
            },
        )

    async def _http(
        self,
        scope,
        receive,
        send,
    ) -> None:
        try:
            body = await self._read_http_body(
                receive
            )

            headers = normalize_headers(
                scope.get(
                    "headers",
                    [],
                )
            )

            client = scope.get(
                "client"
            )

            remote = (
                str(
                    client[0]
                )
                if client
                else None
            )

            request = HttpRequest(
                method=str(
                    scope.get(
                        "method",
                        "GET",
                    )
                ),
                path=str(
                    scope.get(
                        "path",
                        "/",
                    )
                ),
                headers=headers,
                query=parse_query_string(
                    scope.get(
                        "query_string",
                        b"",
                    )
                ),
                body=body,
                request_id=(
                    headers.get(
                        "x-goat-request-id"
                    )
                ),
                remote_address=remote,
            )

            response = (
                self.runtime.handle(
                    request
                )
            )

        except Exception as exc:
            response = (
                self._error_response(
                    exc
                )
            )

        await send(
            {
                "type":
                    "http.response.start",
                "status":
                    response.status,
                "headers": [
                    (
                        key.encode(
                            "latin-1"
                        ),
                        value.encode(
                            "latin-1"
                        ),
                    )
                    for key, value
                    in response.headers
                ],
            }
        )

        await send(
            {
                "type":
                    "http.response.body",
                "body":
                    response.body,
            }
        )

    @staticmethod
    async def _send_voice_event(
        send,
        event: VoiceServerEvent,
    ) -> None:
        payload = {
            "sequence":
                event.sequence,
            "type":
                event.event_type.value,
            "session_id":
                event.session_id,
            "turn_id":
                event.turn_id,
            "payload":
                event.payload,
            "occurred_at":
                event
                .occurred_at
                .isoformat(),
        }

        await send(
            {
                "type":
                    "websocket.send",
                "text":
                    json.dumps(
                        payload,
                        separators=(
                            ",",
                            ":",
                        ),
                        sort_keys=True,
                    ),
            }
        )

    async def _websocket(
        self,
        scope,
        receive,
        send,
    ) -> None:
        if (
            scope.get(
                "path"
            )
            != "/v1/realtime/voice"
        ):
            await send(
                {
                    "type":
                        "websocket.close",
                    "code":
                        4404,
                    "reason":
                        "route not found",
                }
            )

            return

        session = None

        try:
            initial = await receive()

            if (
                initial.get(
                    "type"
                )
                != "websocket.connect"
            ):
                raise RealtimeProtocolError(
                    "expected websocket.connect"
                )

            headers = normalize_headers(
                scope.get(
                    "headers",
                    [],
                )
            )

            tenant_id = (
                headers.get(
                    "x-goat-tenant-id",
                    "",
                ).strip()
            )

            device_id = (
                headers.get(
                    "x-goat-device-id",
                    "",
                ).strip()
            )

            if not tenant_id:
                raise RealtimeProtocolError(
                    "missing tenant"
                )

            if not device_id:
                raise RealtimeProtocolError(
                    "missing device ID"
                )

            encoding_value = (
                headers.get(
                    "x-goat-audio-encoding",
                    AudioEncoding
                    .PCM16_24000_MONO
                    .value,
                )
            )

            try:
                encoding = AudioEncoding(
                    encoding_value
                )

            except ValueError as exc:
                raise (
                    RealtimeProtocolError(
                        "unsupported audio encoding"
                    )
                ) from exc

            handshake = (
                RealtimeHandshake(
                    tenant_id=tenant_id,
                    bearer_token=(
                        bearer_token(
                            headers
                        )
                    ),
                    device=(
                        DeviceSignals(
                            device_id=(
                                device_id
                            ),
                            platform=(
                                headers.get(
                                    "x-goat-platform",
                                    "unknown",
                                )
                            ),
                            known_device=(
                                headers.get(
                                    "x-goat-known-device",
                                    "0",
                                )
                                == "1"
                            ),
                            attested=(
                                headers.get(
                                    "x-goat-attested",
                                    "0",
                                )
                                == "1"
                            ),
                            rooted_or_jailbroken=(
                                headers.get(
                                    "x-goat-rooted",
                                    "0",
                                )
                                == "1"
                            ),
                            vpn_or_proxy=(
                                headers.get(
                                    "x-goat-vpn",
                                    "0",
                                )
                                == "1"
                            ),
                            tor=(
                                headers.get(
                                    "x-goat-tor",
                                    "0",
                                )
                                == "1"
                            ),
                            public_network=(
                                headers.get(
                                    "x-goat-public-network",
                                    "0",
                                )
                                == "1"
                            ),
                            impossible_travel=(
                                headers.get(
                                    "x-goat-impossible-travel",
                                    "0",
                                )
                                == "1"
                            ),
                            attestation_anomaly=(
                                headers.get(
                                    "x-goat-attestation-anomaly",
                                    "0",
                                )
                                == "1"
                            ),
                        )
                    ),
                    audio_encoding=(
                        encoding
                    ),
                )
            )

            session, ready = (
                self.realtime.open(
                    handshake
                )
            )

            await send(
                {
                    "type":
                        "websocket.accept",
                    "subprotocol":
                        "goat.voice.v1",
                    "headers": [],
                }
            )

            await self._send_voice_event(
                send,
                ready,
            )

            while True:
                message = await receive()

                message_type = (
                    message.get(
                        "type"
                    )
                )

                if (
                    message_type
                    == "websocket.disconnect"
                ):
                    if (
                        session.state.value
                        != "closed"
                    ):
                        self.realtime.close(
                            session.session_id,
                            reason=(
                                "transport_disconnect"
                            ),
                        )

                    break

                if (
                    message_type
                    != "websocket.receive"
                ):
                    raise RealtimeProtocolError(
                        "invalid websocket event"
                    )

                raw_bytes = message.get(
                    "bytes"
                )

                raw_text = message.get(
                    "text"
                )

                if raw_bytes is not None:
                    if len(raw_bytes) < 9:
                        raise RealtimeProtocolError(
                            "binary audio frame missing sequence header"
                        )

                    sequence = struct.unpack(
                        ">Q",
                        raw_bytes[:8],
                    )[0]

                    audio = raw_bytes[
                        8:
                    ]

                    frame = VoiceClientFrame(
                        sequence=int(
                            sequence
                        ),
                        frame_type=(
                            ClientFrameType
                            .INPUT_AUDIO
                        ),
                        audio=audio,
                    )

                else:
                    try:
                        payload = json.loads(
                            raw_text
                            or "{}"
                        )

                    except json.JSONDecodeError as exc:
                        raise (
                            RealtimeProtocolError(
                                "invalid websocket JSON"
                            )
                        ) from exc

                    if not isinstance(
                        payload,
                        dict,
                    ):
                        raise RealtimeProtocolError(
                            "websocket payload must be object"
                        )

                    try:
                        frame_type = (
                            ClientFrameType(
                                str(
                                    payload[
                                        "type"
                                    ]
                                )
                            )
                        )

                        sequence = int(
                            payload[
                                "sequence"
                            ]
                        )

                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                    ) as exc:
                        raise (
                            RealtimeProtocolError(
                                "invalid realtime frame envelope"
                            )
                        ) from exc

                    frame = VoiceClientFrame(
                        sequence=sequence,
                        frame_type=(
                            frame_type
                        ),
                        text=(
                            payload.get(
                                "text"
                            )
                        ),
                        client_timestamp_ms=(
                            payload.get(
                                "client_timestamp_ms"
                            )
                        ),
                    )

                events = (
                    self.realtime.receive(
                        session.session_id,
                        frame,
                    )
                )

                for event in events:
                    await (
                        self._send_voice_event(
                            send,
                            event,
                        )
                    )

                if (
                    session.state.value
                    == "closed"
                ):
                    await send(
                        {
                            "type":
                                "websocket.close",
                            "code":
                                1000,
                        }
                    )

                    break

        except Exception as exc:
            if (
                session is not None
                and session.state.value
                != "closed"
            ):
                try:
                    self.realtime.close(
                        session.session_id,
                        reason="server_error",
                    )

                except Exception:
                    pass

            reason = str(
                exc
            )[:120]

            await send(
                {
                    "type":
                        "websocket.close",
                    "code":
                        4400,
                    "reason":
                        reason,
                }
            )


def build_application(
    *,
    session_secret: bytes,
) -> GOATASGIApp:
    sessions = SessionTokenService(
        secret=session_secret
    )

    gateway = (
        SecureApplicationGateway(
            sessions=sessions
        )
    )

    sync_feed = (
        CrossPlatformSyncFeed()
    )

    metrics = (
        MetricsRegistry()
    )

    runtime = (
        GOATApplicationServer(
            gateway=gateway,
            sync_feed=sync_feed,
            metrics=metrics,
        )
    )

    realtime = (
        RealtimeVoiceEngine(
            sessions=sessions,
            metrics=metrics,
        )
    )

    return GOATASGIApp(
        runtime=runtime,
        realtime=realtime,
    )
