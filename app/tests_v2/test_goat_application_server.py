import json
import struct
import unittest

from dataclasses import replace
from datetime import datetime, timezone

from leadbot_v2.goat.app_server import (
    AudioEncoding,
    ClientFrameType,
    GOATASGIApp,
    GOATApplicationServer,
    HttpRequest,
    MetricsRegistry,
    RealtimeHandshake,
    RealtimeProtocolError,
    RealtimeVoiceEngine,
    ServerEventType,
    VoiceClientFrame,
    VoiceSessionState,
)

from leadbot_v2.goat.gateway import (
    AuthStrength,
    CrossPlatformSyncFeed,
    DeviceSignals,
    SecureApplicationGateway,
    SessionTokenService,
    SyncOperation,
)


UTC = timezone.utc


class BaseServerTest(
    unittest.TestCase
):
    def setUp(self):
        self.sessions = (
            SessionTokenService(
                secret=b"s" * 64
            )
        )

        self.gateway = (
            SecureApplicationGateway(
                sessions=(
                    self.sessions
                )
            )
        )

        self.sync = (
            CrossPlatformSyncFeed()
        )

        self.metrics = (
            MetricsRegistry()
        )

        self.runtime = (
            GOATApplicationServer(
                gateway=self.gateway,
                sync_feed=self.sync,
                metrics=self.metrics,
            )
        )

        self.voice = (
            RealtimeVoiceEngine(
                sessions=self.sessions,
                metrics=self.metrics,
            )
        )

        (
            self.token,
            self.claims,
        ) = self.sessions.issue(
            user_id="user-1",
            tenant_id="tenant-1",
            role="president",
            device_id="device-1",
            auth_strength=(
                AuthStrength.PASSKEY
            ),
        )

    def trusted_device(self):
        return DeviceSignals(
            device_id="device-1",
            platform="ipados",
            known_device=True,
            attested=True,
        )

    def auth_headers(
        self,
        *,
        nonce: str,
    ):
        return {
            "authorization":
                "Bearer "
                + self.token,
            "x-goat-tenant-id":
                "tenant-1",
            "x-goat-device-id":
                "device-1",
            "x-goat-platform":
                "ipados",
            "x-goat-known-device":
                "1",
            "x-goat-attested":
                "1",
            "x-goat-request-nonce":
                nonce,
        }


class RuntimeTests(
    BaseServerTest
):
    def test_health(self):
        response = (
            self.runtime.handle(
                HttpRequest(
                    method="GET",
                    path="/healthz",
                    headers={},
                    query={},
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        payload = json.loads(
            response.body
        )

        self.assertEqual(
            payload["status"],
            "ok",
        )

    def test_ready(self):
        response = (
            self.runtime.handle(
                HttpRequest(
                    method="GET",
                    path="/readyz",
                    headers={},
                    query={},
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

    def test_session_me(self):
        response = (
            self.runtime.handle(
                HttpRequest(
                    method="GET",
                    path="/v1/session/me",
                    headers=(
                        self.auth_headers(
                            nonce="me-1"
                        )
                    ),
                    query={},
                )
            )
        )

        payload = json.loads(
            response.body
        )

        self.assertEqual(
            payload["user_id"],
            "user-1",
        )

        self.assertEqual(
            payload["tenant_id"],
            "tenant-1",
        )

    def test_sync_feed(self):
        self.sync.append(
            tenant_id="tenant-1",
            project_id="project-1",
            entity_type="rfi",
            entity_id="rfi-1",
            operation=(
                SyncOperation.CREATE
            ),
            payload={
                "subject":
                    "Structural clarification"
            },
        )

        self.sync.append(
            tenant_id="tenant-1",
            project_id="project-2",
            entity_type="rfi",
            entity_id="rfi-secret",
            operation=(
                SyncOperation.CREATE
            ),
            payload={
                "subject":
                    "Other project"
            },
        )

        response = (
            self.runtime.handle(
                HttpRequest(
                    method="GET",
                    path="/v1/sync",
                    headers=(
                        self.auth_headers(
                            nonce="sync-1"
                        )
                    ),
                    query={
                        "cursor":
                            "0",
                        "projects":
                            "project-1",
                    },
                )
            )
        )

        payload = json.loads(
            response.body
        )

        self.assertEqual(
            len(
                payload["changes"]
            ),
            1,
        )

        self.assertEqual(
            payload[
                "changes"
            ][0]["entity_id"],
            "rfi-1",
        )

    def test_metrics(self):
        self.runtime.handle(
            HttpRequest(
                method="GET",
                path="/healthz",
                headers={},
                query={},
            )
        )

        snapshot = (
            self.metrics.snapshot()
        )

        self.assertGreaterEqual(
            snapshot.counters[
                "http.requests"
            ],
            1,
        )


class VoiceTests(
    BaseServerTest
):
    def open_voice(self):
        return self.voice.open(
            RealtimeHandshake(
                tenant_id="tenant-1",
                bearer_token=self.token,
                device=self.trusted_device(),
                audio_encoding=(
                    AudioEncoding
                    .PCM16_24000_MONO
                ),
            )
        )

    def test_voice_open(self):
        session, event = (
            self.open_voice()
        )

        self.assertEqual(
            session.state,
            VoiceSessionState.READY,
        )

        self.assertEqual(
            event.event_type,
            ServerEventType
            .SESSION_READY,
        )

    def test_voice_tenant_isolation(self):
        with self.assertRaises(
            RealtimeProtocolError
        ):
            self.voice.open(
                RealtimeHandshake(
                    tenant_id="wrong",
                    bearer_token=(
                        self.token
                    ),
                    device=(
                        self
                        .trusted_device()
                    ),
                )
            )

    def test_voice_audio_sequence(self):
        session, _ = (
            self.open_voice()
        )

        events = self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=1,
                frame_type=(
                    ClientFrameType
                    .INPUT_AUDIO
                ),
                audio=b"\x00\x00" * 100,
            ),
        )

        self.assertEqual(
            events[-1].event_type,
            ServerEventType
            .AUDIO_ACK,
        )

        self.assertEqual(
            session.state,
            VoiceSessionState
            .LISTENING,
        )

    def test_sequence_gap_rejected(self):
        session, _ = (
            self.open_voice()
        )

        with self.assertRaises(
            RealtimeProtocolError
        ):
            self.voice.receive(
                session.session_id,
                VoiceClientFrame(
                    sequence=2,
                    frame_type=(
                        ClientFrameType
                        .HEARTBEAT
                    ),
                ),
            )

    def test_audio_oversize_rejected(self):
        session, _ = (
            self.open_voice()
        )

        with self.assertRaises(
            RealtimeProtocolError
        ):
            self.voice.receive(
                session.session_id,
                VoiceClientFrame(
                    sequence=1,
                    frame_type=(
                        ClientFrameType
                        .INPUT_AUDIO
                    ),
                    audio=(
                        b"x"
                        * (
                            64
                            * 1024
                            + 1
                        )
                    ),
                ),
            )

    def test_commit_audio_turn(self):
        session, _ = (
            self.open_voice()
        )

        self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=1,
                frame_type=(
                    ClientFrameType
                    .INPUT_AUDIO
                ),
                audio=b"\x00\x00" * 100,
            ),
        )

        events = self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=2,
                frame_type=(
                    ClientFrameType
                    .COMMIT_TURN
                ),
            ),
        )

        self.assertEqual(
            events[0].event_type,
            ServerEventType
            .TURN_STARTED,
        )

        self.assertEqual(
            session.state,
            VoiceSessionState
            .THINKING,
        )

    def test_text_turn(self):
        session, _ = (
            self.open_voice()
        )

        events = self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=1,
                frame_type=(
                    ClientFrameType
                    .INPUT_TEXT
                ),
                text=(
                    "What projects need attention?"
                ),
            ),
        )

        self.assertEqual(
            events[-1].event_type,
            ServerEventType
            .TURN_STARTED,
        )

    def test_assistant_response(self):
        session, _ = (
            self.open_voice()
        )

        self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=1,
                frame_type=(
                    ClientFrameType
                    .INPUT_TEXT
                ),
                text="Status",
            ),
        )

        event = (
            self.voice
            .assistant_text(
                session.session_id,
                text="All systems nominal.",
            )
        )

        self.assertEqual(
            event.event_type,
            ServerEventType
            .ASSISTANT_TEXT,
        )

        self.assertEqual(
            session.state,
            VoiceSessionState
            .SPEAKING,
        )

    def test_barge_in(self):
        session, _ = (
            self.open_voice()
        )

        self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=1,
                frame_type=(
                    ClientFrameType
                    .INPUT_TEXT
                ),
                text="Give status",
            ),
        )

        self.voice.assistant_text(
            session.session_id,
            text="Beginning report",
        )

        events = self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=2,
                frame_type=(
                    ClientFrameType
                    .INPUT_AUDIO
                ),
                audio=b"\x00\x00" * 50,
            ),
        )

        types = {
            item.event_type
            for item
            in events
        }

        self.assertIn(
            ServerEventType
            .INTERRUPTED,
            types,
        )

        self.assertIn(
            ServerEventType
            .AUDIO_ACK,
            types,
        )

    def test_finish_turn(self):
        session, _ = (
            self.open_voice()
        )

        self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=1,
                frame_type=(
                    ClientFrameType
                    .INPUT_TEXT
                ),
                text="Status",
            ),
        )

        self.voice.assistant_text(
            session.session_id,
            text="Ready",
        )

        event = (
            self.voice.finish_turn(
                session.session_id
            )
        )

        self.assertEqual(
            event.event_type,
            ServerEventType
            .TURN_FINISHED,
        )

        self.assertEqual(
            session.state,
            VoiceSessionState.READY,
        )

    def test_heartbeat(self):
        session, _ = (
            self.open_voice()
        )

        events = self.voice.receive(
            session.session_id,
            VoiceClientFrame(
                sequence=1,
                frame_type=(
                    ClientFrameType
                    .HEARTBEAT
                ),
            ),
        )

        self.assertEqual(
            events[0].event_type,
            ServerEventType
            .HEARTBEAT_ACK,
        )


class ASGIHTTPTests(
    BaseServerTest,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_asgi_health(self):
        app = GOATASGIApp(
            runtime=self.runtime,
            realtime=self.voice,
        )

        received = [
            {
                "type":
                    "http.request",
                "body":
                    b"",
                "more_body":
                    False,
            }
        ]

        sent = []

        async def receive():
            return received.pop(0)

        async def send(message):
            sent.append(message)

        await app(
            {
                "type":
                    "http",
                "method":
                    "GET",
                "path":
                    "/healthz",
                "query_string":
                    b"",
                "headers":
                    [],
                "client":
                    (
                        "127.0.0.1",
                        1234,
                    ),
            },
            receive,
            send,
        )

        self.assertEqual(
            sent[0]["status"],
            200,
        )


class ASGIWebSocketTests(
    BaseServerTest,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_websocket_handshake_and_heartbeat(
        self,
    ):
        app = GOATASGIApp(
            runtime=self.runtime,
            realtime=self.voice,
        )

        incoming = [
            {
                "type":
                    "websocket.connect",
            },
            {
                "type":
                    "websocket.receive",
                "text":
                    json.dumps(
                        {
                            "type":
                                "heartbeat",
                            "sequence":
                                1,
                        }
                    ),
            },
            {
                "type":
                    "websocket.disconnect",
                "code":
                    1000,
            },
        ]

        outgoing = []

        async def receive():
            return incoming.pop(0)

        async def send(message):
            outgoing.append(
                message
            )

        headers = [
            (
                b"authorization",
                (
                    "Bearer "
                    + self.token
                ).encode(),
            ),
            (
                b"x-goat-tenant-id",
                b"tenant-1",
            ),
            (
                b"x-goat-device-id",
                b"device-1",
            ),
            (
                b"x-goat-platform",
                b"ipados",
            ),
            (
                b"x-goat-known-device",
                b"1",
            ),
            (
                b"x-goat-attested",
                b"1",
            ),
        ]

        await app(
            {
                "type":
                    "websocket",
                "path":
                    "/v1/realtime/voice",
                "headers":
                    headers,
            },
            receive,
            send,
        )

        types = [
            message["type"]
            for message
            in outgoing
        ]

        self.assertIn(
            "websocket.accept",
            types,
        )

        text_messages = [
            json.loads(
                message["text"]
            )
            for message
            in outgoing
            if (
                message["type"]
                == "websocket.send"
                and "text"
                in message
            )
        ]

        event_types = {
            item["type"]
            for item
            in text_messages
        }

        self.assertIn(
            "session_ready",
            event_types,
        )

        self.assertIn(
            "heartbeat_ack",
            event_types,
        )


class BinaryAudioProtocolTests(
    BaseServerTest
):
    def test_binary_header_encoding(self):
        sequence = 123456789

        payload = (
            struct.pack(
                ">Q",
                sequence,
            )
            + b"audio"
        )

        decoded = struct.unpack(
            ">Q",
            payload[:8],
        )[0]

        self.assertEqual(
            decoded,
            sequence,
        )

        self.assertEqual(
            payload[8:],
            b"audio",
        )


if __name__ == "__main__":
    unittest.main()
