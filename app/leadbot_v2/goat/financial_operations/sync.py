from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from leadbot_v2.goat.financial_intelligence import (
    RawBankTransaction,
)

from leadbot_v2.goat.financial_intelligence.canonical import (
    money,
    stable_hash,
)

from .models import (
    AccountRoute,
    ProviderCapability,
    SyncCorrection,
    SyncCursor,
    SyncResult,
)


class SyncStateStore:
    def __init__(
        self,
    ) -> None:
        self._cursors = {}

        self._pending = {}

        self._forwarded = {}

    @staticmethod
    def account_key(
        *,
        provider_name,
        entity_id,
        external_account_id,
    ):
        return (
            provider_name,
            entity_id,
            external_account_id,
        )

    @staticmethod
    def transaction_key(
        transaction,
    ):
        return (
            transaction.provider_name,
            transaction.entity_id,
            transaction.external_account_id,
            transaction.external_transaction_id,
        )

    def cursor(
        self,
        *,
        provider_name,
        entity_id,
        external_account_id,
    ):
        return self._cursors.get(
            self.account_key(
                provider_name=(
                    provider_name
                ),
                entity_id=(
                    entity_id
                ),
                external_account_id=(
                    external_account_id
                ),
            )
        )

    def set_cursor(
        self,
        cursor: SyncCursor,
    ) -> None:
        self._cursors[
            self.account_key(
                provider_name=(
                    cursor.provider_name
                ),
                entity_id=(
                    cursor.entity_id
                ),
                external_account_id=(
                    cursor.external_account_id
                ),
            )
        ] = cursor

    def stage_pending(
        self,
        transaction,
        fingerprint: str,
    ) -> None:
        self._pending[
            self.transaction_key(
                transaction
            )
        ] = fingerprint

    def clear_pending(
        self,
        transaction,
    ) -> None:
        self._pending.pop(
            self.transaction_key(
                transaction
            ),
            None,
        )

    def forwarded_fingerprint(
        self,
        transaction,
    ):
        return self._forwarded.get(
            self.transaction_key(
                transaction
            )
        )

    def mark_forwarded(
        self,
        transaction,
        fingerprint: str,
    ) -> None:
        self._forwarded[
            self.transaction_key(
                transaction
            )
        ] = fingerprint

        self.clear_pending(
            transaction
        )


class BankSynchronizationEngine:
    def __init__(
        self,
        *,
        control_plane,
        state_store=None,
    ) -> None:
        self.control_plane = (
            control_plane
        )

        self.state = (
            state_store
            or SyncStateStore()
        )

    @staticmethod
    def fingerprint(
        transaction,
    ) -> str:
        return stable_hash(
            {
                "provider_name":
                    transaction
                    .provider_name,
                "entity_id":
                    transaction
                    .entity_id,
                "external_account_id":
                    transaction
                    .external_account_id,
                "external_transaction_id":
                    transaction
                    .external_transaction_id,
                "posted_date":
                    transaction
                    .posted_date,
                "signed_amount":
                    money(
                        transaction
                        .signed_amount
                    ),
                "description":
                    transaction
                    .description,
                "merchant_name":
                    transaction
                    .merchant_name,
                "pending":
                    transaction
                    .pending,
                "revision_token":
                    transaction
                    .revision_token,
            }
        )

    def sync(
        self,
        *,
        provider_name: str,
        entity_id: str,
        start_date,
        end_date,
        financial_system,
    ) -> SyncResult:
        if (
            financial_system.entity_id
            != entity_id
        ):
            raise ValueError(
                "financial system entity mismatch"
            )

        accounts = (
            self.control_plane
            .accounts(
                provider_name=(
                    provider_name
                ),
                entity_id=(
                    entity_id
                ),
            )
        )

        seen = 0
        accepted_count = 0
        pending_count = 0
        duplicate_count = 0

        corrections = []
        cursors = []

        for account in accounts:
            existing_cursor = (
                self.state.cursor(
                    provider_name=(
                        provider_name
                    ),
                    entity_id=(
                        entity_id
                    ),
                    external_account_id=(
                        account
                        .external_account_id
                    ),
                )
            )

            cursor = (
                existing_cursor.cursor
                if existing_cursor
                else None
            )

            page_guard = 0

            while True:
                page_guard += 1

                if page_guard > 1000:
                    raise RuntimeError(
                        "provider pagination exceeded safety limit"
                    )

                page = (
                    self.control_plane
                    .transactions(
                        provider_name=(
                            provider_name
                        ),
                        entity_id=(
                            entity_id
                        ),
                        external_account_id=(
                            account
                            .external_account_id
                        ),
                        start_date=(
                            start_date
                        ),
                        end_date=(
                            end_date
                        ),
                        cursor=cursor,
                    )
                )

                for external in (
                    page.transactions
                ):
                    seen += 1

                    fingerprint = (
                        self.fingerprint(
                            external
                        )
                    )

                    if external.pending:
                        self.state.stage_pending(
                            external,
                            fingerprint,
                        )

                        pending_count += 1
                        continue

                    previous = (
                        self.state
                        .forwarded_fingerprint(
                            external
                        )
                    )

                    if previous is not None:
                        if (
                            previous
                            == fingerprint
                        ):
                            duplicate_count += 1

                        else:
                            corrections.append(
                                SyncCorrection(
                                    provider_name=(
                                        external
                                        .provider_name
                                    ),
                                    entity_id=(
                                        external
                                        .entity_id
                                    ),
                                    external_account_id=(
                                        external
                                        .external_account_id
                                    ),
                                    external_transaction_id=(
                                        external
                                        .external_transaction_id
                                    ),
                                    previous_fingerprint=(
                                        previous
                                    ),
                                    new_fingerprint=(
                                        fingerprint
                                    ),
                                    reason=(
                                        "provider changed a previously "
                                        "forwarded posted transaction; "
                                        "manual correction workflow required"
                                    ),
                                )
                            )

                        continue

                    raw = RawBankTransaction(
                        entity_id=(
                            external.entity_id
                        ),
                        provider=(
                            external.provider_name
                        ),
                        transaction_id=(
                            external
                            .external_transaction_id
                        ),
                        account_id=(
                            external
                            .external_account_id
                        ),
                        posted_date=(
                            external.posted_date
                        ),
                        signed_amount=money(
                            external.signed_amount
                        ),
                        description=(
                            external.description
                        ),
                        merchant_name=(
                            external.merchant_name
                        ),
                        pending=False,
                        metadata=dict(
                            external.metadata
                        ),
                    )

                    accepted, duplicates = (
                        financial_system
                        .ingest_raw_transactions(
                            (
                                raw,
                            )
                        )
                    )

                    if accepted:
                        accepted_count += 1

                        self.state.mark_forwarded(
                            external,
                            fingerprint,
                        )

                    else:
                        duplicate_count += (
                            len(
                                duplicates
                            )
                        )

                cursor = (
                    page.next_cursor
                )

                if not page.has_more:
                    break

            snapshot = SyncCursor(
                provider_name=(
                    provider_name
                ),
                entity_id=(
                    entity_id
                ),
                external_account_id=(
                    account
                    .external_account_id
                ),
                cursor=cursor,
                updated_at=datetime.now(
                    timezone.utc
                ),
            )

            self.state.set_cursor(
                snapshot
            )

            cursors.append(
                snapshot
            )

        return SyncResult(
            provider_name=(
                provider_name
            ),
            entity_id=entity_id,
            accounts_seen=len(
                accounts
            ),
            transactions_seen=seen,
            accepted_posted=(
                accepted_count
            ),
            staged_pending=(
                pending_count
            ),
            duplicates=(
                duplicate_count
            ),
            corrections=tuple(
                corrections
            ),
            next_cursors=tuple(
                cursors
            ),
        )
