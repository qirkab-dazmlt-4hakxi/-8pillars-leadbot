from __future__ import annotations

from .models import (
    AdapterCapability,
    AdapterHealth,
    AdapterHealthState,
    AdapterPage,
    AdapterPolicyError,
    ExternalPublicationState,
    PublicationReceipt,
    utcnow,
)


READ_CAPABILITIES = {
    AdapterCapability.SEARCH_READ,
    AdapterCapability.ANALYTICS_READ,
    AdapterCapability.LOCAL_LISTINGS_READ,
    AdapterCapability.REVIEWS_READ,
}


class GrowthPlatformAdapter:
    adapter_name: str

    def health(self, *, secret_resolver):
        raise NotImplementedError

    def read_stream(
        self,
        *,
        stream_name,
        cursor,
        secret_resolver,
    ):
        raise NotImplementedError

    def publish(
        self,
        *,
        request,
        secret_resolver,
    ):
        raise NotImplementedError


class GrowthAdapterRegistry:
    def __init__(
        self,
        *,
        secret_resolver,
    ) -> None:
        self.secret_resolver = secret_resolver
        self._registrations = {}
        self._adapters = {}

    def register(
        self,
        *,
        registration,
        adapter,
    ) -> None:
        if (
            registration.adapter_name
            != adapter.adapter_name
        ):
            raise AdapterPolicyError(
                "adapter registration name mismatch"
            )

        if (
            registration.adapter_name
            in self._adapters
        ):
            raise AdapterPolicyError(
                "duplicate adapter"
            )

        self._registrations[
            registration.adapter_name
        ] = registration

        self._adapters[
            registration.adapter_name
        ] = adapter

    def registration(
        self,
        adapter_name,
    ):
        try:
            return self._registrations[
                adapter_name
            ]
        except KeyError as exc:
            raise AdapterPolicyError(
                f"unknown adapter: {adapter_name}"
            ) from exc

    def adapter(
        self,
        adapter_name,
    ):
        self.registration(adapter_name)

        return self._adapters[
            adapter_name
        ]

    def require(
        self,
        adapter_name,
        capability,
    ) -> None:
        registration = self.registration(
            adapter_name
        )

        if not registration.enabled:
            raise AdapterPolicyError(
                "adapter disabled"
            )

        if (
            capability
            not in registration.capabilities
        ):
            raise AdapterPolicyError(
                f"adapter lacks capability "
                f"{capability.value}"
            )

    def health(
        self,
        adapter_name,
    ):
        return self.adapter(
            adapter_name
        ).health(
            secret_resolver=(
                self.secret_resolver
            )
        )

    def read_stream(
        self,
        *,
        adapter_name,
        stream_name,
        capability,
        cursor=None,
    ):
        if capability not in READ_CAPABILITIES:
            raise AdapterPolicyError(
                "stream read requires read capability"
            )

        self.require(
            adapter_name,
            capability,
        )

        return self.adapter(
            adapter_name
        ).read_stream(
            stream_name=stream_name,
            cursor=cursor,
            secret_resolver=(
                self.secret_resolver
            ),
        )

    def publish(
        self,
        *,
        request,
        capability,
    ):
        if capability not in {
            AdapterCapability.CONTENT_PUBLISH,
            AdapterCapability.SOCIAL_PUBLISH,
        }:
            raise AdapterPolicyError(
                "invalid publication capability"
            )

        self.require(
            request.adapter_name,
            capability,
        )

        return self.adapter(
            request.adapter_name
        ).publish(
            request=request,
            secret_resolver=(
                self.secret_resolver
            ),
        )


class SimulatedGrowthAdapter(
    GrowthPlatformAdapter
):
    adapter_name = "goat-simulated-growth"

    def __init__(
        self,
        *,
        pages=None,
        healthy=True,
    ) -> None:
        self.pages = dict(
            pages or {}
        )

        self.healthy = bool(
            healthy
        )

        self.publications = []

    def health(
        self,
        *,
        secret_resolver,
    ):
        return AdapterHealth(
            adapter_name=self.adapter_name,
            state=(
                AdapterHealthState.HEALTHY
                if self.healthy
                else AdapterHealthState.UNAVAILABLE
            ),
            message="simulated growth adapter",
        )

    def read_stream(
        self,
        *,
        stream_name,
        cursor,
        secret_resolver,
    ):
        return self.pages.get(
            (
                stream_name,
                cursor,
            ),
            AdapterPage(
                items=(),
                next_cursor=None,
                has_more=False,
            ),
        )

    def publish(
        self,
        *,
        request,
        secret_resolver,
    ):
        self.publications.append(
            request
        )

        return PublicationReceipt(
            request_id=request.request_id,
            adapter_name=self.adapter_name,
            external_id=(
                f"sim-{len(self.publications)}"
            ),
            state=(
                ExternalPublicationState.EXECUTED
            ),
            executed_at=utcnow(),
            message=(
                "simulated publication executed"
            ),
        )
