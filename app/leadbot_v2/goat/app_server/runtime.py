from __future__ import annotations

import uuid

from dataclasses import dataclass
from typing import Any, Callable

from leadbot_v2.goat.gateway import (
    ApiRisk,
    AuthStrength,
    CrossPlatformSyncFeed,
    DataClass,
    DeviceSignals,
    EndpointSpec,
    GatewayRequest,
    SecureApplicationGateway,
)

from .contracts import (
    BadRequest,
    HttpRequest,
    HttpResponse,
    RouteNotFound,
    bearer_token,
)

from .observability import (
    MetricsRegistry,
    Timer,
)


RouteHandler = Callable[
    [
        HttpRequest,
        Any,
    ],
    HttpResponse,
]


@dataclass(frozen=True)
class Route:
    method: str
    path: str

    endpoint_name: str | None

    protected: bool

    handler: RouteHandler


class RouteRegistry:
    def __init__(
        self,
    ) -> None:
        self._routes = {}

    def add(
        self,
        route: Route,
    ) -> None:
        key = (
            route.method.upper(),
            route.path,
        )

        if key in self._routes:
            raise ValueError(
                "duplicate application route"
            )

        self._routes[
            key
        ] = route

    def resolve(
        self,
        method: str,
        path: str,
    ) -> Route:
        try:
            return self._routes[
                (
                    method.upper(),
                    path,
                )
            ]

        except KeyError as exc:
            raise RouteNotFound(
                (
                    method.upper()
                    + " "
                    + path
                )
            ) from exc


class GOATApplicationServer:
    ALL_ROLES = frozenset(
        {
            "president",
            "vice_president",
            "sales",
            "marketing",
            "project_manager",
            "field",
            "client",
        }
    )

    def __init__(
        self,
        *,
        gateway: SecureApplicationGateway,
        sync_feed: CrossPlatformSyncFeed,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.gateway = (
            gateway
        )

        self.sync_feed = (
            sync_feed
        )

        self.metrics = (
            metrics
            or MetricsRegistry()
        )

        self.routes = (
            RouteRegistry()
        )

        self._install_routes()

    def _install_routes(
        self,
    ) -> None:
        self.routes.add(
            Route(
                method="GET",
                path="/healthz",
                endpoint_name=None,
                protected=False,
                handler=(
                    self._health
                ),
            )
        )

        self.routes.add(
            Route(
                method="GET",
                path="/readyz",
                endpoint_name=None,
                protected=False,
                handler=(
                    self._ready
                ),
            )
        )

        self.gateway.register_endpoint(
            EndpointSpec(
                name="session.me",
                method="GET",
                path="/v1/session/me",
                allowed_roles=(
                    self.ALL_ROLES
                ),
                data_class=(
                    DataClass.INTERNAL
                ),
                risk=ApiRisk.READ,
                minimum_auth=(
                    AuthStrength.MFA
                ),
                rate_capacity=120,
                rate_refill_per_second=2.0,
            )
        )

        self.routes.add(
            Route(
                method="GET",
                path="/v1/session/me",
                endpoint_name="session.me",
                protected=True,
                handler=(
                    self._session_me
                ),
            )
        )

        self.gateway.register_endpoint(
            EndpointSpec(
                name="sync.pull",
                method="GET",
                path="/v1/sync",
                allowed_roles=(
                    self.ALL_ROLES
                ),
                data_class=(
                    DataClass.CONFIDENTIAL
                ),
                risk=ApiRisk.READ,
                minimum_auth=(
                    AuthStrength.MFA
                ),
                rate_capacity=120,
                rate_refill_per_second=2.0,
            )
        )

        self.routes.add(
            Route(
                method="GET",
                path="/v1/sync",
                endpoint_name="sync.pull",
                protected=True,
                handler=(
                    self._sync_pull
                ),
            )
        )

    def handle(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        request_id = (
            request.request_id
            or (
                "req_"
                + uuid.uuid4().hex
            )
        )

        self.metrics.increment(
            "http.requests"
        )

        route = self.routes.resolve(
            request.method,
            request.path,
        )

        with Timer(
            self.metrics,
            "http.request.seconds",
        ):
            if not route.protected:
                response = route.handler(
                    request,
                    None,
                )

            else:
                tenant_id = (
                    request.headers.get(
                        "x-goat-tenant-id",
                        "",
                    ).strip()
                )

                if not tenant_id:
                    raise BadRequest(
                        "missing x-goat-tenant-id"
                    )

                device_id = (
                    request.headers.get(
                        "x-goat-device-id",
                        "",
                    ).strip()
                )

                if not device_id:
                    raise BadRequest(
                        "missing x-goat-device-id"
                    )

                nonce = (
                    request.headers.get(
                        "x-goat-request-nonce",
                        "",
                    ).strip()
                )

                if not nonce:
                    raise BadRequest(
                        "missing x-goat-request-nonce"
                    )

                platform = (
                    request.headers.get(
                        "x-goat-platform",
                        "unknown",
                    ).strip()
                )

                gateway_request = (
                    GatewayRequest(
                        method=(
                            request.method
                        ),
                        path=(
                            request.path
                        ),
                        tenant_id=(
                            tenant_id
                        ),
                        bearer_token=(
                            bearer_token(
                                request.headers
                            )
                        ),
                        device=(
                            DeviceSignals(
                                device_id=(
                                    device_id
                                ),
                                platform=(
                                    platform
                                ),
                                known_device=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-known-device",
                                        "0",
                                    )
                                    == "1"
                                ),
                                attested=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-attested",
                                        "0",
                                    )
                                    == "1"
                                ),
                                rooted_or_jailbroken=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-rooted",
                                        "0",
                                    )
                                    == "1"
                                ),
                                vpn_or_proxy=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-vpn",
                                        "0",
                                    )
                                    == "1"
                                ),
                                tor=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-tor",
                                        "0",
                                    )
                                    == "1"
                                ),
                                public_network=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-public-network",
                                        "0",
                                    )
                                    == "1"
                                ),
                                impossible_travel=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-impossible-travel",
                                        "0",
                                    )
                                    == "1"
                                ),
                                attestation_anomaly=(
                                    request
                                    .headers
                                    .get(
                                        "x-goat-attestation-anomaly",
                                        "0",
                                    )
                                    == "1"
                                ),
                            )
                        ),
                        request_nonce=(
                            nonce
                        ),
                        idempotency_key=(
                            request.headers.get(
                                "idempotency-key"
                            )
                        ),
                        body=(
                            request.json()
                            if request.body
                            else {}
                        ),
                    )
                )

                response = (
                    self.gateway.execute(
                        gateway_request,
                        handler=lambda decision:
                            route.handler(
                                request,
                                decision,
                            ),
                    )
                )

        response_headers = (
            response.headers
            + (
                (
                    "x-goat-request-id",
                    request_id,
                ),
            )
        )

        self.metrics.increment(
            (
                "http.status."
                + str(
                    response.status
                )
            )
        )

        return HttpResponse(
            status=response.status,
            body=response.body,
            headers=response_headers,
        )

    def _health(
        self,
        request: HttpRequest,
        decision: Any,
    ) -> HttpResponse:
        return HttpResponse.json(
            200,
            {
                "status":
                    "ok",
                "service":
                    "goat-os",
            },
        )

    def _ready(
        self,
        request: HttpRequest,
        decision: Any,
    ) -> HttpResponse:
        return HttpResponse.json(
            200,
            {
                "status":
                    "ready",
                "gateway":
                    True,
                "sync":
                    True,
                "realtime":
                    True,
            },
        )

    def _session_me(
        self,
        request: HttpRequest,
        decision: Any,
    ) -> HttpResponse:
        claims = (
            decision.claims
        )

        return HttpResponse.json(
            200,
            {
                "user_id":
                    claims.user_id,
                "tenant_id":
                    claims.tenant_id,
                "role":
                    claims.role,
                "device_id":
                    claims.device_id,
                "auth_strength":
                    int(
                        claims
                        .auth_strength
                    ),
                "device_score":
                    decision.device_score,
            },
        )

    def _sync_pull(
        self,
        request: HttpRequest,
        decision: Any,
    ) -> HttpResponse:
        try:
            cursor = int(
                request.query.get(
                    "cursor",
                    "0",
                )
            )

            limit = int(
                request.query.get(
                    "limit",
                    "100",
                )
            )

        except ValueError as exc:
            raise BadRequest(
                "invalid sync cursor/limit"
            ) from exc

        limit = max(
            1,
            min(
                500,
                limit,
            ),
        )

        project_string = (
            request.query.get(
                "projects",
                "",
            )
        )

        projects = {
            item.strip()
            for item
            in project_string.split(
                ","
            )
            if item.strip()
        }

        page = (
            self.sync_feed.page(
                tenant_id=(
                    decision
                    .claims
                    .tenant_id
                ),
                cursor=cursor,
                allowed_project_ids=(
                    projects
                ),
                limit=limit,
            )
        )

        return HttpResponse.json(
            200,
            {
                "next_cursor":
                    page.next_cursor,
                "has_more":
                    page.has_more,
                "changes": [
                    {
                        "sequence":
                            item.sequence,
                        "project_id":
                            item.project_id,
                        "entity_type":
                            item.entity_type,
                        "entity_id":
                            item.entity_id,
                        "operation":
                            item.operation.value,
                        "payload":
                            item.payload,
                        "payload_hash":
                            item.payload_hash,
                        "occurred_at":
                            item
                            .occurred_at
                            .isoformat(),
                    }
                    for item
                    in page.changes
                ],
            },
        )
