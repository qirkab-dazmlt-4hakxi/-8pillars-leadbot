from __future__ import annotations

from .models import (
    IngestionCursor,
    IngestionResult,
    utcnow,
)

from leadbot_v2.goat.growth_intelligence import (
    stable_hash,
)


class GrowthIngestionState:
    def __init__(self) -> None:
        self._cursors = {}
        self._fingerprints = set()

    def cursor(
        self,
        *,
        adapter_name,
        stream_name,
    ):
        return self._cursors.get(
            (
                adapter_name,
                stream_name,
            )
        )

    def set_cursor(
        self,
        cursor,
    ) -> None:
        self._cursors[
            (
                cursor.adapter_name,
                cursor.stream_name,
            )
        ] = cursor

    def accept_fingerprint(
        self,
        fingerprint,
    ) -> bool:
        if fingerprint in self._fingerprints:
            return False

        self._fingerprints.add(
            fingerprint
        )

        return True


class GrowthStreamIngestor:
    def __init__(
        self,
        *,
        registry,
        state=None,
        rate_limiter=None,
    ) -> None:
        self.registry = registry
        self.state = (
            state
            or GrowthIngestionState()
        )
        self.rate_limiter = rate_limiter

    @staticmethod
    def fingerprint(item):
        return stable_hash(item)

    def ingest(
        self,
        *,
        adapter_name,
        stream_name,
        capability,
        item_handler,
    ):
        previous = self.state.cursor(
            adapter_name=adapter_name,
            stream_name=stream_name,
        )

        cursor = (
            previous.cursor
            if previous
            else None
        )

        seen = 0
        accepted = 0
        duplicates = 0
        guard = 0

        while True:
            guard += 1

            if guard > 1000:
                raise RuntimeError(
                    "pagination safety limit exceeded"
                )

            if self.rate_limiter is not None:
                if not self.rate_limiter.allow(
                    adapter_name
                ):
                    raise RuntimeError(
                        "adapter rate limit exhausted"
                    )

            page = self.registry.read_stream(
                adapter_name=adapter_name,
                stream_name=stream_name,
                capability=capability,
                cursor=cursor,
            )

            for item in page.items:
                seen += 1

                fingerprint = (
                    self.fingerprint(item)
                )

                if not self.state.accept_fingerprint(
                    fingerprint
                ):
                    duplicates += 1
                    continue

                item_handler(item)
                accepted += 1

            cursor = page.next_cursor

            if not page.has_more:
                break

        state = IngestionCursor(
            adapter_name=adapter_name,
            stream_name=stream_name,
            cursor=cursor,
            updated_at=utcnow(),
        )

        self.state.set_cursor(
            state
        )

        return IngestionResult(
            adapter_name=adapter_name,
            stream_name=stream_name,
            items_seen=seen,
            accepted=accepted,
            duplicates=duplicates,
            next_cursor=cursor,
        )
