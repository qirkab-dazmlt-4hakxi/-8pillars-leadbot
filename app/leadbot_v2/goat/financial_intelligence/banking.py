from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from .canonical import (
    money,
    stable_hash,
)

from .models import (
    BankDirection,
    BankTransaction,
)


@dataclass(frozen=True)
class BankAccountSnapshot:
    entity_id: str

    provider: str
    account_id: str

    name: str
    account_type: str

    current_balance: Decimal

    available_balance: Decimal | None = None


@dataclass(frozen=True)
class RawBankTransaction:
    entity_id: str

    provider: str

    transaction_id: str
    account_id: str

    posted_date: date

    signed_amount: Decimal

    description: str

    merchant_name: str | None = None

    pending: bool = False

    metadata: dict | None = None


@dataclass(frozen=True)
class ProviderHealth:
    provider: str

    healthy: bool

    message: str = ""


class BankProvider(
    Protocol
):
    provider_name: str

    def accounts(
        self,
    ) -> tuple[
        BankAccountSnapshot,
        ...,
    ]:
        ...

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[
        RawBankTransaction,
        ...,
    ]:
        ...

    def health(
        self,
    ) -> ProviderHealth:
        ...


class BankFeedNormalizer:
    def normalize(
        self,
        raw: RawBankTransaction,
    ) -> BankTransaction:
        signed = money(
            raw.signed_amount
        )

        direction = (
            BankDirection.INFLOW
            if signed >= Decimal(
                "0.00"
            )
            else BankDirection.OUTFLOW
        )

        amount = money(
            abs(
                signed
            )
        )

        external_hash = stable_hash(
            {
                "entity_id":
                    raw.entity_id,
                "provider":
                    raw.provider,
                "transaction_id":
                    raw.transaction_id,
                "account_id":
                    raw.account_id,
                "posted_date":
                    raw.posted_date,
                "signed_amount":
                    signed,
                "description":
                    raw.description,
                "merchant_name":
                    raw.merchant_name,
            }
        )

        return BankTransaction(
            transaction_id=(
                raw.transaction_id
            ),
            entity_id=(
                raw.entity_id
            ),
            provider=(
                raw.provider
            ),
            account_id=(
                raw.account_id
            ),
            posted_date=(
                raw.posted_date
            ),
            amount=amount,
            direction=direction,
            description=(
                raw.description
            ),
            merchant_name=(
                raw.merchant_name
            ),
            pending=bool(
                raw.pending
            ),
            external_hash=(
                external_hash
            ),
            metadata=dict(
                raw.metadata or {}
            ),
        )


class BankFeedIngestor:
    def __init__(
        self,
    ) -> None:
        self.normalizer = (
            BankFeedNormalizer()
        )

        self._seen_ids = set()
        self._seen_hashes = set()

    def ingest(
        self,
        rows,
    ):
        accepted = []
        duplicates = []

        for raw in rows:
            transaction = (
                self.normalizer
                .normalize(
                    raw
                )
            )

            key = (
                transaction.entity_id,
                transaction.provider,
                transaction.account_id,
                transaction.transaction_id,
            )

            if (
                key in self._seen_ids
                or transaction.external_hash
                in self._seen_hashes
            ):
                duplicates.append(
                    transaction
                )
                continue

            self._seen_ids.add(
                key
            )
            self._seen_hashes.add(
                transaction.external_hash
            )

            accepted.append(
                transaction
            )

        return (
            tuple(
                accepted
            ),
            tuple(
                duplicates
            ),
        )


class SimulatedBankProvider:
    provider_name = (
        "goat-simulated-bank"
    )

    def __init__(
        self,
        *,
        accounts=(),
        transactions=(),
        healthy=True,
    ) -> None:
        self._accounts = tuple(
            accounts
        )
        self._transactions = tuple(
            transactions
        )
        self._healthy = bool(
            healthy
        )

    def accounts(
        self,
    ):
        return self._accounts

    def transactions(
        self,
        *,
        start_date,
        end_date,
    ):
        return tuple(
            row
            for row
            in self._transactions
            if (
                start_date
                <= row.posted_date
                <= end_date
            )
        )

    def health(
        self,
    ) -> ProviderHealth:
        return ProviderHealth(
            provider=(
                self.provider_name
            ),
            healthy=(
                self._healthy
            ),
            message=(
                "simulated provider"
            ),
        )
