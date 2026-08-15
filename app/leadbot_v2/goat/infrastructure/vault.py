from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from leadbot_v2.goat.platform.runtime import (
    DataClassification,
)


class VaultError(RuntimeError):
    pass


class VaultObjectNotFound(VaultError):
    pass


class VaultIntegrityError(VaultError):
    pass


class VaultPolicyError(VaultError):
    pass


class VaultLegalHoldError(VaultError):
    pass


class VaultState(str, Enum):
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    DELETED = "deleted"


@dataclass(frozen=True)
class VaultObject:
    object_id: str
    tenant_id: str
    logical_name: str
    original_filename: str
    version: int
    content_hash: str
    size_bytes: int
    mime_type: str
    classification: DataClassification
    state: VaultState
    legal_hold: bool
    previous_object_id: str | None
    created_at: datetime
    created_by: str


@dataclass(frozen=True)
class VaultVerification:
    object_id: str
    exists: bool
    size_matches: bool
    hash_matches: bool
    metadata_matches: bool

    @property
    def valid(self) -> bool:
        return (
            self.exists
            and self.size_matches
            and self.hash_matches
            and self.metadata_matches
        )


def _now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _id(
    prefix: str,
) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _required(
    value: str,
    field: str,
) -> str:
    result = str(
        value
        or ""
    ).strip()

    if not result:
        raise ValueError(
            f"{field} is required"
        )

    return result


def _sha256(
    data: bytes,
) -> str:
    return hashlib.sha256(
        data
    ).hexdigest()


class LocalDocumentVault:
    """
    Deterministic local battle-test adapter for GOAT document storage.

    Production adapters must preserve these semantics using managed object
    storage, provider-side encryption/KMS, immutable versioning, signed
    access, malware scanning, backup policy and lifecycle management.

    This adapter does NOT claim to provide cloud KMS encryption itself.
    `storage_encryption_confirmed` represents an assertion supplied by the
    backing storage adapter/provider.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        max_object_bytes: int = (
            100 * 1024 * 1024
        ),
    ) -> None:
        if max_object_bytes <= 0:
            raise ValueError(
                "max_object_bytes must be positive"
            )

        self.root = Path(
            root
        )

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.blob_root = (
            self.root
            / "blobs"
        )

        self.blob_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.max_object_bytes = (
            max_object_bytes
        )

        self.db_path = (
            self.root
            / "vault.sqlite3"
        )

        self._conn = sqlite3.connect(
            str(
                self.db_path
            ),
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )

        self._conn.row_factory = (
            sqlite3.Row
        )

        self._conn.execute(
            "PRAGMA journal_mode=WAL"
        )

        self._conn.execute(
            "PRAGMA synchronous=FULL"
        )

        self._initialize()

    def close(
        self,
    ) -> None:
        self._conn.close()

    def _initialize(
        self,
    ) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_objects (
                object_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                logical_name TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                version INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mime_type TEXT NOT NULL,
                classification INTEGER NOT NULL,
                state TEXT NOT NULL,
                legal_hold INTEGER NOT NULL,
                previous_object_id TEXT,
                storage_encryption_confirmed INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                UNIQUE (
                    tenant_id,
                    logical_name,
                    version
                )
            )
            """
        )

        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_vault_logical_name
            ON vault_objects (
                tenant_id,
                logical_name,
                version DESC
            )
            """
        )

    @staticmethod
    def _tenant_digest(
        tenant_id: str,
    ) -> str:
        return hashlib.sha256(
            tenant_id.encode(
                "utf-8"
            )
        ).hexdigest()

    def _blob_path(
        self,
        *,
        tenant_id: str,
        content_hash: str,
    ) -> Path:
        tenant_digest = (
            self._tenant_digest(
                tenant_id
            )
        )

        return (
            self.blob_root
            / tenant_digest[:2]
            / tenant_digest
            / content_hash[:2]
            / content_hash
        )

    @staticmethod
    def _row(
        row: sqlite3.Row,
    ) -> VaultObject:
        return VaultObject(
            object_id=(
                row["object_id"]
            ),
            tenant_id=(
                row["tenant_id"]
            ),
            logical_name=(
                row["logical_name"]
            ),
            original_filename=(
                row[
                    "original_filename"
                ]
            ),
            version=int(
                row["version"]
            ),
            content_hash=(
                row["content_hash"]
            ),
            size_bytes=int(
                row["size_bytes"]
            ),
            mime_type=(
                row["mime_type"]
            ),
            classification=(
                DataClassification(
                    int(
                        row[
                            "classification"
                        ]
                    )
                )
            ),
            state=(
                VaultState(
                    row["state"]
                )
            ),
            legal_hold=bool(
                row["legal_hold"]
            ),
            previous_object_id=(
                row[
                    "previous_object_id"
                ]
            ),
            created_at=(
                datetime
                .fromisoformat(
                    row[
                        "created_at"
                    ]
                )
            ),
            created_by=(
                row["created_by"]
            ),
        )

    def put(
        self,
        *,
        tenant_id: str,
        logical_name: str,
        original_filename: str,
        data: bytes,
        mime_type: str,
        classification: (
            DataClassification
        ),
        created_by: str,
        storage_encryption_confirmed: bool = False,
        scanner: (
            Callable[
                [bytes],
                bool,
            ]
            | None
        ) = None,
    ) -> VaultObject:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        logical_name = _required(
            logical_name,
            "logical_name",
        )

        original_filename = (
            _required(
                original_filename,
                "original_filename",
            )
        )

        mime_type = _required(
            mime_type,
            "mime_type",
        )

        created_by = _required(
            created_by,
            "created_by",
        )

        if not isinstance(
            data,
            bytes,
        ):
            raise TypeError(
                "data must be bytes"
            )

        if not data:
            raise VaultPolicyError(
                "zero-byte object rejected"
            )

        if (
            len(data)
            > self.max_object_bytes
        ):
            raise VaultPolicyError(
                "object exceeds size limit"
            )

        if (
            classification
            >= DataClassification
            .RESTRICTED
            and not storage_encryption_confirmed
        ):
            raise VaultPolicyError(
                "restricted/financial object "
                "requires confirmed encrypted storage"
            )

        scan_passed = (
            scanner(data)
            if scanner
            is not None
            else True
        )

        state = (
            VaultState.ACTIVE
            if scan_passed
            else VaultState
            .QUARANTINED
        )

        content_hash = (
            _sha256(
                data
            )
        )

        blob_path = (
            self._blob_path(
                tenant_id=tenant_id,
                content_hash=(
                    content_hash
                ),
            )
        )

        blob_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not blob_path.exists():
            fd, temp_path = (
                tempfile.mkstemp(
                    prefix=(
                        ".goat-object-"
                    ),
                    dir=str(
                        blob_path.parent
                    ),
                )
            )

            try:
                with os.fdopen(
                    fd,
                    "wb",
                ) as fh:
                    fh.write(
                        data
                    )

                    fh.flush()

                    os.fsync(
                        fh.fileno()
                    )

                os.replace(
                    temp_path,
                    blob_path,
                )

            finally:
                if os.path.exists(
                    temp_path
                ):
                    os.unlink(
                        temp_path
                    )

        latest = (
            self._conn.execute(
                """
                SELECT *
                FROM vault_objects
                WHERE tenant_id = ?
                  AND logical_name = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (
                    tenant_id,
                    logical_name,
                ),
            ).fetchone()
        )

        version = (
            int(
                latest["version"]
            )
            + 1
            if latest
            else 1
        )

        previous_object_id = (
            latest["object_id"]
            if latest
            else None
        )

        object_id = _id(
            "obj"
        )

        now = _now()

        self._conn.execute(
            """
            INSERT INTO vault_objects (
                object_id,
                tenant_id,
                logical_name,
                original_filename,
                version,
                content_hash,
                size_bytes,
                mime_type,
                classification,
                state,
                legal_hold,
                previous_object_id,
                storage_encryption_confirmed,
                created_at,
                created_by
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, 0,
                ?, ?, ?, ?
            )
            """,
            (
                object_id,
                tenant_id,
                logical_name,
                original_filename,
                version,
                content_hash,
                len(data),
                mime_type,
                int(
                    classification
                ),
                state.value,
                previous_object_id,
                int(
                    storage_encryption_confirmed
                ),
                now.isoformat(),
                created_by,
            ),
        )

        return self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

    def get_metadata(
        self,
        *,
        tenant_id: str,
        object_id: str,
    ) -> VaultObject:
        row = (
            self._conn.execute(
                """
                SELECT *
                FROM vault_objects
                WHERE tenant_id = ?
                  AND object_id = ?
                """,
                (
                    tenant_id,
                    object_id,
                ),
            ).fetchone()
        )

        if row is None:
            raise VaultObjectNotFound(
                object_id
            )

        return self._row(
            row
        )

    def latest(
        self,
        *,
        tenant_id: str,
        logical_name: str,
    ) -> VaultObject:
        row = (
            self._conn.execute(
                """
                SELECT *
                FROM vault_objects
                WHERE tenant_id = ?
                  AND logical_name = ?
                  AND state != ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (
                    tenant_id,
                    logical_name,
                    VaultState
                    .DELETED
                    .value,
                ),
            ).fetchone()
        )

        if row is None:
            raise VaultObjectNotFound(
                logical_name
            )

        return self._row(
            row
        )

    def get_bytes(
        self,
        *,
        tenant_id: str,
        object_id: str,
        allow_quarantined: bool = False,
    ) -> bytes:
        obj = self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

        if (
            obj.state
            == VaultState.DELETED
        ):
            raise VaultPolicyError(
                "object is deleted"
            )

        if (
            obj.state
            == VaultState.QUARANTINED
            and not allow_quarantined
        ):
            raise VaultPolicyError(
                "object is quarantined"
            )

        blob_path = (
            self._blob_path(
                tenant_id=tenant_id,
                content_hash=(
                    obj.content_hash
                ),
            )
        )

        if not blob_path.exists():
            raise VaultIntegrityError(
                "object blob missing"
            )

        data = blob_path.read_bytes()

        if (
            len(data)
            != obj.size_bytes
        ):
            raise VaultIntegrityError(
                "object size mismatch"
            )

        if (
            _sha256(data)
            != obj.content_hash
        ):
            raise VaultIntegrityError(
                "object hash mismatch"
            )

        return data

    def verify(
        self,
        *,
        tenant_id: str,
        object_id: str,
    ) -> VaultVerification:
        obj = self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

        path = self._blob_path(
            tenant_id=tenant_id,
            content_hash=(
                obj.content_hash
            ),
        )

        if not path.exists():
            return VaultVerification(
                object_id=object_id,
                exists=False,
                size_matches=False,
                hash_matches=False,
                metadata_matches=True,
            )

        data = path.read_bytes()

        return VaultVerification(
            object_id=object_id,
            exists=True,
            size_matches=(
                len(data)
                == obj.size_bytes
            ),
            hash_matches=(
                _sha256(data)
                == obj.content_hash
            ),
            metadata_matches=True,
        )

    def quarantine(
        self,
        *,
        tenant_id: str,
        object_id: str,
    ) -> VaultObject:
        self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

        self._conn.execute(
            """
            UPDATE vault_objects
            SET state = ?
            WHERE tenant_id = ?
              AND object_id = ?
            """,
            (
                VaultState
                .QUARANTINED
                .value,
                tenant_id,
                object_id,
            ),
        )

        return self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

    def set_legal_hold(
        self,
        *,
        tenant_id: str,
        object_id: str,
        enabled: bool,
    ) -> VaultObject:
        self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

        self._conn.execute(
            """
            UPDATE vault_objects
            SET legal_hold = ?
            WHERE tenant_id = ?
              AND object_id = ?
            """,
            (
                int(
                    enabled
                ),
                tenant_id,
                object_id,
            ),
        )

        return self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

    def delete(
        self,
        *,
        tenant_id: str,
        object_id: str,
    ) -> VaultObject:
        obj = self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

        if obj.legal_hold:
            raise VaultLegalHoldError(
                "object is under legal hold"
            )

        self._conn.execute(
            """
            UPDATE vault_objects
            SET state = ?
            WHERE tenant_id = ?
              AND object_id = ?
            """,
            (
                VaultState
                .DELETED
                .value,
                tenant_id,
                object_id,
            ),
        )

        return self.get_metadata(
            tenant_id=tenant_id,
            object_id=object_id,
        )

    def versions(
        self,
        *,
        tenant_id: str,
        logical_name: str,
    ) -> tuple[
        VaultObject,
        ...
    ]:
        rows = (
            self._conn.execute(
                """
                SELECT *
                FROM vault_objects
                WHERE tenant_id = ?
                  AND logical_name = ?
                ORDER BY version ASC
                """,
                (
                    tenant_id,
                    logical_name,
                ),
            ).fetchall()
        )

        return tuple(
            self._row(row)
            for row
            in rows
        )
