from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IncidentRecord:
    component: str
    action: str
    reason: str
    severity: str
    count: int = 1
    first_seen: str = ""
    last_seen: str = ""

    def touch(self) -> None:
        now = utc_now_iso()

        if not self.first_seen:
            self.first_seen = now

        self.last_seen = now
        self.count += 1


class IncidentStore:
    def __init__(
        self,
        path: str | Path = "data/v2_incidents.json",
    ) -> None:
        self.path = Path(path)
        self.records: dict[str, IncidentRecord] = {}
        self.load()

    def _key(
        self,
        component: str,
        action: str,
    ) -> str:
        return f"{component}::{action}"

    def record(
        self,
        *,
        component: str,
        action: str,
        reason: str,
        severity: str,
    ) -> IncidentRecord:
        key = self._key(component, action)

        if key not in self.records:
            now = utc_now_iso()

            self.records[key] = IncidentRecord(
                component=component,
                action=action,
                reason=reason,
                severity=severity,
                count=1,
                first_seen=now,
                last_seen=now,
            )

        else:
            item = self.records[key]
            item.reason = reason
            item.severity = severity
            item.touch()

        self.save()
        return self.records[key]

    def load(self) -> None:
        if not self.path.exists():
            return

        try:
            raw = json.loads(
                self.path.read_text(
                    encoding="utf-8",
                )
            )
        except Exception:
            return

        for key, item in raw.get(
            "incidents",
            {},
        ).items():
            try:
                self.records[key] = IncidentRecord(
                    **item
                )
            except Exception:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "version": 1,
            "incidents": {
                key: asdict(value)
                for key, value in self.records.items()
            },
        }

        data = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )

        fd, temp_path = tempfile.mkstemp(
            prefix="incidents-",
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
