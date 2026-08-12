from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import os
import tempfile

from leadbot_v2.core.source_health import (
    CircuitState,
    SourceCircuitBreaker,
    SourceHealth,
)


class HealthStore:
    def __init__(
        self,
        path: str | Path = "data/v2_source_health.json",
    ) -> None:
        self.path = Path(path)

    def load_into(
        self,
        breaker: SourceCircuitBreaker,
    ) -> None:
        if not self.path.exists():
            return

        try:
            raw = json.loads(
                self.path.read_text(encoding="utf-8")
            )
        except Exception:
            # Corrupt persistence must never crash acquisition.
            return

        for name, item in raw.get("sources", {}).items():
            try:
                health = SourceHealth(
                    name=name,
                    state=CircuitState(
                        item.get(
                            "state",
                            CircuitState.CLOSED.value,
                        )
                    ),
                    total_requests=int(
                        item.get("total_requests", 0)
                    ),
                    successes=int(
                        item.get("successes", 0)
                    ),
                    failures=int(
                        item.get("failures", 0)
                    ),
                    consecutive_failures=int(
                        item.get(
                            "consecutive_failures",
                            0,
                        )
                    ),
                    latency_ms_ema=float(
                        item.get("latency_ms_ema", 0.0)
                    ),
                    last_error=item.get("last_error"),
                    metadata=item.get("metadata", {}),
                )

                # Never restore an OPEN circuit forever after restart.
                # Let current runtime health re-evaluate the source.
                if health.state == CircuitState.OPEN:
                    health.state = CircuitState.HALF_OPEN

                breaker.sources[name] = health

            except Exception:
                continue

    def save(
        self,
        breaker: SourceCircuitBreaker,
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "version": 1,
            "sources": {},
        }

        for name, health in breaker.sources.items():
            item = asdict(health)

            item["state"] = health.state.value

            # monotonic timestamps are process-local and not
            # meaningful after restart.
            item["opened_at"] = None
            item["last_success_at"] = None
            item["last_failure_at"] = None

            payload["sources"][name] = item

        data = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )

        fd, temp_path = tempfile.mkstemp(
            prefix="source-health-",
            suffix=".json",
            dir=str(self.path.parent),
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

            os.replace(
                temp_path,
                self.path,
            )

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
