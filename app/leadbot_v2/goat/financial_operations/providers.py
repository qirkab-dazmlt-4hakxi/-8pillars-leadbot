from __future__ import annotations

from typing import Protocol

from .models import (
    ExternalAccount,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthState,
    ProviderPolicyError,
    ProviderRegistration,
    ProviderTransactionPage,
)


class ReadOnlyFinancialProvider(
    Protocol
):
    provider_name: str

    def health(
        self,
        *,
        secret_resolver,
    ) -> ProviderHealth:
        ...

    def accounts(
        self,
        *,
        entity_id: str,
        secret_resolver,
    ) -> tuple[
        ExternalAccount,
        ...,
    ]:
        ...

    def transactions(
        self,
        *,
        entity_id: str,
        external_account_id: str,
        start_date,
        end_date,
        cursor: str | None,
        secret_resolver,
    ) -> ProviderTransactionPage:
        ...


class ProviderControlPlane:
    def __init__(
        self,
        *,
        secret_resolver,
    ) -> None:
        self.secret_resolver = (
            secret_resolver
        )

        self._registrations = {}
        self._providers = {}

    def register(
        self,
        *,
        registration: ProviderRegistration,
        provider,
    ) -> None:
        name = (
            registration
            .provider_name
        )

        if (
            name
            != provider.provider_name
        ):
            raise ProviderPolicyError(
                "provider registration name mismatch"
            )

        if (
            name
            in self._providers
        ):
            raise ProviderPolicyError(
                f"duplicate provider: {name}"
            )

        forbidden = {
            capability
            for capability
            in registration.capabilities
            if capability
            not in {
                ProviderCapability.ACCOUNTS_READ,
                ProviderCapability.TRANSACTIONS_READ,
            }
        }

        if forbidden:
            raise ProviderPolicyError(
                "financial operations edge is read-only"
            )

        self._registrations[
            name
        ] = registration

        self._providers[
            name
        ] = provider

    def require_capability(
        self,
        provider_name: str,
        capability: ProviderCapability,
    ) -> None:
        registration = (
            self._registrations[
                provider_name
            ]
        )

        if not registration.enabled:
            raise ProviderPolicyError(
                f"provider disabled: "
                f"{provider_name}"
            )

        if (
            capability
            not in registration.capabilities
        ):
            raise ProviderPolicyError(
                f"provider lacks capability "
                f"{capability.value}"
            )

    def provider(
        self,
        provider_name: str,
    ):
        try:
            return self._providers[
                provider_name
            ]
        except KeyError as exc:
            raise ProviderPolicyError(
                f"unknown provider: "
                f"{provider_name}"
            ) from exc

    def health(
        self,
        provider_name: str,
    ) -> ProviderHealth:
        provider = self.provider(
            provider_name
        )

        return provider.health(
            secret_resolver=(
                self.secret_resolver
            )
        )

    def accounts(
        self,
        *,
        provider_name: str,
        entity_id: str,
    ):
        self.require_capability(
            provider_name,
            ProviderCapability
            .ACCOUNTS_READ,
        )

        provider = self.provider(
            provider_name
        )

        return provider.accounts(
            entity_id=entity_id,
            secret_resolver=(
                self.secret_resolver
            ),
        )

    def transactions(
        self,
        *,
        provider_name: str,
        entity_id: str,
        external_account_id: str,
        start_date,
        end_date,
        cursor=None,
    ):
        self.require_capability(
            provider_name,
            ProviderCapability
            .TRANSACTIONS_READ,
        )

        provider = self.provider(
            provider_name
        )

        return provider.transactions(
            entity_id=entity_id,
            external_account_id=(
                external_account_id
            ),
            start_date=start_date,
            end_date=end_date,
            cursor=cursor,
            secret_resolver=(
                self.secret_resolver
            ),
        )


class SimulatedReadOnlyProvider:
    provider_name = (
        "goat-simulated-finance"
    )

    def __init__(
        self,
        *,
        accounts=(),
        pages=None,
        healthy=True,
    ) -> None:
        self._accounts = tuple(
            accounts
        )

        self._pages = dict(
            pages or {}
        )

        self._healthy = bool(
            healthy
        )

    def health(
        self,
        *,
        secret_resolver,
    ):
        return ProviderHealth(
            provider_name=(
                self.provider_name
            ),
            state=(
                ProviderHealthState.HEALTHY
                if self._healthy
                else ProviderHealthState.UNAVAILABLE
            ),
            message=(
                "simulated finance provider"
            ),
        )

    def accounts(
        self,
        *,
        entity_id,
        secret_resolver,
    ):
        return tuple(
            account
            for account
            in self._accounts
            if account.entity_id
            == entity_id
        )

    def transactions(
        self,
        *,
        entity_id,
        external_account_id,
        start_date,
        end_date,
        cursor,
        secret_resolver,
    ):
        key = (
            entity_id,
            external_account_id,
            cursor,
        )

        page = self._pages.get(
            key
        )

        if page is None:
            return ProviderTransactionPage(
                transactions=(),
                next_cursor=None,
                has_more=False,
            )

        filtered = tuple(
            transaction
            for transaction
            in page.transactions
            if (
                start_date
                <= transaction.posted_date
                <= end_date
            )
        )

        return ProviderTransactionPage(
            transactions=filtered,
            next_cursor=(
                page.next_cursor
            ),
            has_more=(
                page.has_more
            ),
        )
