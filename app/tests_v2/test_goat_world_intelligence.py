from __future__ import annotations

import unittest

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from leadbot_v2.goat.world_intelligence import (
    EvidenceChain,
    EvidenceEnvelope,
    EvidenceIntegrityError,
    EvidenceStatus,
    RefreshCadence,
    SignalDomain,
    SourceAuthority,
    SourceDefinition,
    SourceHealthTracker,
    WorldIntelligenceService,
    WorldRepository,
    seal_evidence,
    verify_evidence,
)


NOW = datetime(
    2026,
    8,
    17,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeStore:
    def __init__(
        self,
    ):
        self.entities = {}

    def get_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        include_deleted=False,
    ):
        return deepcopy(
            self.entities.get(
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                )
            )
        )

    def put_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        payload,
        actor_id,
        expected_version=None,
    ):
        key = (
            tenant_id,
            entity_type,
            entity_id,
        )

        current = (
            self.entities.get(
                key
            )
        )

        if current is None:
            if expected_version is not None:
                raise RuntimeError(
                    "version conflict"
                )

            version = 1

        else:
            if (
                current.version
                != expected_version
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = (
                current.version
                + 1
            )

        record = SimpleNamespace(
            version=version,
            payload=deepcopy(
                payload
            ),
        )

        self.entities[
            key
        ] = record

        return deepcopy(
            record
        )


def official_source(
    *,
    source_id="official",
    domain=SignalDomain.BUILDING_CODE,
):
    return SourceDefinition(
        source_id=source_id,
        name="Official Source",
        authority=(
            SourceAuthority.OFFICIAL
        ),
        domains=frozenset(
            {
                domain
            }
        ),
        public_information_only=True,
        base_confidence=1.0,
    )


def evidence(
    *,
    evidence_id,
    source_id="official",
    domain=SignalDomain.BUILDING_CODE,
    subject="Fort Worth",
    predicate="adopted_code",
    value="Code A",
    jurisdiction="Fort Worth, Texas",
    confidence=1.0,
    acquired_at=NOW,
):
    return EvidenceEnvelope(
        evidence_id=(
            evidence_id
        ),
        source_id=source_id,
        domain=domain,
        subject=subject,
        predicate=predicate,
        value=value,
        jurisdiction=jurisdiction,
        source_url=(
            "https://example.gov/source"
        ),
        published_at=(
            NOW
            - timedelta(
                days=1
            )
        ),
        acquired_at=(
            acquired_at
        ),
        confidence=(
            confidence
        ),
    )


class ProvenanceTests(
    unittest.TestCase
):
    def test_evidence_hash_verifies(
        self,
    ):
        sealed = seal_evidence(
            evidence(
                evidence_id="e1"
            )
        )

        self.assertTrue(
            verify_evidence(
                sealed
            )
        )

    def test_tampering_detected(
        self,
    ):
        sealed = seal_evidence(
            evidence(
                evidence_id="e1"
            )
        )

        tampered = (
            EvidenceEnvelope(
                **{
                    **sealed.__dict__,
                    "value":
                        "Tampered Value",
                }
            )
        )

        with self.assertRaises(
            EvidenceIntegrityError
        ):
            verify_evidence(
                tampered
            )

    def test_chain_verification(
        self,
    ):
        chain = EvidenceChain()

        chain.append(
            evidence(
                evidence_id="a"
            )
        )

        chain.append(
            evidence(
                evidence_id="b",
                value="Code B",
            )
        )

        self.assertTrue(
            chain.verify()
        )


class SourceTests(
    unittest.TestCase
):
    def test_health_quarantines_repeated_failure(
        self,
    ):
        tracker = SourceHealthTracker(
            failure_quarantine_threshold=3
        )

        for _ in range(
            3
        ):
            tracker.failure(
                "source",
                when=NOW,
            )

        self.assertEqual(
            tracker.health(
                "source"
            ).state.value,
            "quarantined",
        )


class IngestionTests(
    unittest.TestCase
):
    def test_duplicate_suppression(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        service.register_source(
            official_source()
        )

        item = evidence(
            evidence_id="e1"
        )

        first = service.ingest_evidence(
            item
        )

        second = (
            service.ingest_evidence(
                item
            )
        )

        self.assertIsNotNone(
            first
        )

        self.assertIsNone(
            second
        )


class KnowledgeTests(
    unittest.TestCase
):
    def test_official_fact_resolves(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        service.register_source(
            official_source()
        )

        service.ingest_evidence(
            evidence(
                evidence_id="e1"
            )
        )

        decision = service.resolve_fact(
            domain=(
                SignalDomain
                .BUILDING_CODE
            ),
            subject="Fort Worth",
            predicate="adopted_code",
            jurisdiction=(
                "Fort Worth, Texas"
            ),
            now=NOW,
            high_impact=True,
        )

        self.assertTrue(
            decision.usable
        )

        self.assertEqual(
            decision.fact.value,
            "Code A",
        )

    def test_conflicting_official_facts_block_authoritative_use(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        service.register_source(
            official_source(
                source_id="official-a"
            )
        )

        service.register_source(
            official_source(
                source_id="official-b"
            )
        )

        service.ingest_evidence(
            evidence(
                evidence_id="a",
                source_id="official-a",
                value="Code A",
            )
        )

        service.ingest_evidence(
            evidence(
                evidence_id="b",
                source_id="official-b",
                value="Code B",
            )
        )

        decision = service.resolve_fact(
            domain=(
                SignalDomain
                .BUILDING_CODE
            ),
            subject="Fort Worth",
            predicate="adopted_code",
            jurisdiction=(
                "Fort Worth, Texas"
            ),
            now=NOW,
            high_impact=True,
        )

        self.assertFalse(
            decision.usable
        )

        self.assertTrue(
            decision.contradictions
        )


class FreshnessTests(
    unittest.TestCase
):
    def test_stale_fact_eventually_expires(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        service.register_source(
            SourceDefinition(
                source_id="weather",
                name="Weather Source",
                authority=(
                    SourceAuthority.OFFICIAL
                ),
                domains=frozenset(
                    {
                        SignalDomain.WEATHER
                    }
                ),
                base_confidence=1.0,
            )
        )

        service.ingest_evidence(
            evidence(
                evidence_id="weather-1",
                source_id="weather",
                domain=(
                    SignalDomain.WEATHER
                ),
                subject="Site",
                predicate="temperature",
                value=100,
                jurisdiction="Texas",
                acquired_at=(
                    NOW
                    - timedelta(
                        hours=10
                    )
                ),
            )
        )

        decision = service.resolve_fact(
            domain=(
                SignalDomain.WEATHER
            ),
            subject="Site",
            predicate="temperature",
            jurisdiction="Texas",
            now=NOW,
            high_impact=False,
        )

        self.assertFalse(
            decision.usable
        )


class MarketPolicyTests(
    unittest.TestCase
):
    def test_public_market_signal_allowed(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        signal = service.ingest_market_signal(
            domain=(
                SignalDomain.SECURITIES
            ),
            name="price",
            timestamp=NOW,
            value=100.0,
            unit="USD",
            geography="USA",
            source_id="public-market",
            confidence=0.9,
            metadata={
                "information_tags":
                    (
                        "public",
                    )
            },
        )

        self.assertEqual(
            signal.value,
            100.0,
        )

    def test_nonpublic_market_signal_rejected(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        with self.assertRaises(
            ValueError
        ):
            service.ingest_market_signal(
                domain=(
                    SignalDomain.SECURITIES
                ),
                name="event",
                timestamp=NOW,
                value=1,
                unit=None,
                geography="USA",
                source_id="unknown",
                confidence=1.0,
                metadata={
                    "information_tags":
                        (
                            "material_nonpublic",
                        )
                },
            )


class RefreshTests(
    unittest.TestCase
):
    def test_quarterly_deep_refresh(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        task = (
            service.refresh
            .quarterly_audit_task(
                domain=(
                    SignalDomain
                    .ENGINEERING
                ),
                now=NOW,
            )
        )

        self.assertTrue(
            task.full_audit
        )

        self.assertEqual(
            task.priority,
            85,
        )

    def test_weather_incremental_refresh_is_hourly(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        task = (
            service.refresh
            .incremental_task(
                domain=(
                    SignalDomain.WEATHER
                ),
                now=NOW,
            )
        )

        self.assertEqual(
            (
                task.due_at
                - NOW
            ).total_seconds(),
            3600,
        )

    def test_event_driven_refresh_is_immediate(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        task = (
            service.refresh
            .event_driven_task(
                domain=(
                    SignalDomain
                    .BUILDING_CODE
                ),
                now=NOW,
                reason=(
                    "official adoption changed"
                ),
            )
        )

        self.assertEqual(
            task.due_at,
            NOW,
        )

        self.assertEqual(
            task.priority,
            100,
        )


class PersistenceTests(
    unittest.TestCase
):
    def test_evidence_and_fact_persist(
        self,
    ):
        store = FakeStore()

        repository = WorldRepository(
            store,
            tenant_id="tenant",
        )

        service = (
            WorldIntelligenceService(
                repository=(
                    repository
                )
            )
        )

        service.register_source(
            official_source()
        )

        service.ingest_evidence(
            evidence(
                evidence_id="persist"
            )
        )

        entity_types = {
            key[
                1
            ]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.world.evidence",
            entity_types,
        )

        self.assertIn(
            "goat.world.fact",
            entity_types,
        )


class StressTests(
    unittest.TestCase
):
    def test_20000_signal_normalizations(
        self,
    ):
        service = (
            WorldIntelligenceService()
        )

        for index in range(
            20000
        ):
            signal = (
                service.signals
                .normalize(
                    domain=(
                        SignalDomain
                        .MATERIALS
                    ),
                    name="rebar-index",
                    timestamp=NOW,
                    value=float(
                        index
                    ),
                    unit="index",
                    geography="Texas",
                    source_id="source",
                    confidence=0.9,
                    metadata={
                        "index":
                            index
                    },
                )
            )

            self.assertEqual(
                signal.domain,
                SignalDomain.MATERIALS,
            )


if __name__ == "__main__":
    unittest.main()
