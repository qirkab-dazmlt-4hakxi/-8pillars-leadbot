from __future__ import annotations

import re
import uuid

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class BidPackageError(RuntimeError):
    pass


class BidPackageNotFound(
    BidPackageError
):
    pass


class BidDocumentNotFound(
    BidPackageError
):
    pass


class BidRevisionNotFound(
    BidPackageError
):
    pass


class DuplicateDocumentError(
    BidPackageError
):
    pass


class DocumentControlError(
    BidPackageError
):
    pass


class FrozenRevisionError(
    DocumentControlError
):
    pass


class PackageSource(str, Enum):
    BUILDING_CONNECTED = (
        "building_connected"
    )

    CONSTRUCT_CONNECT = (
        "construct_connect"
    )

    DODGE = "dodge"

    GOVERNMENT = "government"

    DIRECT_GC = "direct_gc"

    CLIENT = "client"

    PUBLIC = "public"

    INTERNAL = "internal"

    OTHER = "other"


class DocumentKind(str, Enum):
    PLANS = "plans"

    SPECIFICATIONS = (
        "specifications"
    )

    ADDENDUM = "addendum"

    INVITATION = "invitation"

    BID_FORM = "bid_form"

    RFI = "rfi"

    GEOTECHNICAL = (
        "geotechnical"
    )

    SCHEDULE = "schedule"

    REPORT = "report"

    SCOPE = "scope"

    OTHER = "other"


class Discipline(str, Enum):
    GENERAL = "general"

    ARCHITECTURAL = (
        "architectural"
    )

    STRUCTURAL = "structural"

    CIVIL = "civil"

    ELECTRICAL = "electrical"

    PLUMBING = "plumbing"

    MECHANICAL = "mechanical"

    FIRE_PROTECTION = (
        "fire_protection"
    )

    LANDSCAPE = "landscape"

    IRRIGATION = "irrigation"

    OTHER = "other"


class ControlSeverity(str, Enum):
    INFO = "info"

    REVIEW = "review"

    BLOCKER = "blocker"


@dataclass(frozen=True)
class ControlFinding:
    code: str

    severity: ControlSeverity

    message: str

    document_id: str | None = None

    revision_id: str | None = None

    source_ref: str | None = None


@dataclass(frozen=True)
class BidDocument:
    document_id: str

    package_id: str

    file_name: str

    sha256: str

    size_bytes: int

    kind: DocumentKind

    discipline: Discipline

    logical_key: str

    source_ref: str

    revision_label: str | None

    issue_date: date | None

    sheet_count: int | None

    supersedes_document_id: (
        str | None
    )

    created_at: datetime

    created_by: str


@dataclass(frozen=True)
class BidPackageRevision:
    revision_id: str

    package_id: str

    label: str

    parent_revision_id: (
        str | None
    )

    reason: str

    issued_at: datetime

    created_at: datetime

    created_by: str

    document_ids: tuple[
        str,
        ...
    ]

    frozen: bool = False

    freeze_note: str | None = None


@dataclass(frozen=True)
class BidPackage:
    package_id: str

    tenant_id: str

    business_unit_id: str

    opportunity_id: str | None

    project_name: str

    city: str

    source: PackageSource

    invited_by: str | None

    gc_name: str | None

    client_name: str | None

    due_at: datetime | None

    current_revision_id: str

    created_at: datetime

    created_by: str


@dataclass(frozen=True)
class PackageEvent:
    event_id: str

    package_id: str

    event_type: str

    actor_id: str

    occurred_at: datetime

    payload: tuple[
        tuple[
            str,
            str,
        ],
        ...
    ]


@dataclass(frozen=True)
class RevisionDiff:
    old_revision_id: str

    new_revision_id: str

    added_document_ids: tuple[
        str,
        ...
    ]

    removed_document_ids: tuple[
        str,
        ...
    ]

    replaced_document_pairs: tuple[
        tuple[
            str,
            str,
        ],
        ...
    ]

    unchanged_document_ids: tuple[
        str,
        ...
    ]

    @property
    def changed(
        self,
    ) -> bool:
        return bool(
            self.added_document_ids
            or self.removed_document_ids
            or self
            .replaced_document_pairs
        )


@dataclass(frozen=True)
class PackageReadiness:
    package_id: str

    revision_id: str

    ready: bool

    findings: tuple[
        ControlFinding,
        ...
    ]

    current_document_ids: tuple[
        str,
        ...
    ]

    due_in_seconds: (
        int | None
    )

    @property
    def blockers(
        self,
    ) -> tuple[
        ControlFinding,
        ...
    ]:
        return tuple(
            item
            for item
            in self.findings
            if (
                item.severity
                == ControlSeverity.BLOCKER
            )
        )

    @property
    def review_items(
        self,
    ) -> tuple[
        ControlFinding,
        ...
    ]:
        return tuple(
            item
            for item
            in self.findings
            if (
                item.severity
                == ControlSeverity.REVIEW
            )
        )


@dataclass(frozen=True)
class PackageExecutionManifest:
    package_id: str

    revision_id: str

    previous_revision_id: (
        str | None
    )

    project_name: str

    city: str

    opportunity_id: str | None

    gc_name: str | None

    client_name: str | None

    package_source: str

    due_at: datetime | None

    plan_document_ids: tuple[
        str,
        ...
    ]

    specification_document_ids: tuple[
        str,
        ...
    ]

    addendum_document_ids: tuple[
        str,
        ...
    ]

    supporting_document_ids: tuple[
        str,
        ...
    ]

    all_document_ids: tuple[
        str,
        ...
    ]

    ready_for_execution: bool

    findings: tuple[
        ControlFinding,
        ...
    ]


SHA256_RE = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _new_id(
    prefix: str,
) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _require_text(
    value: str,
    field: str,
) -> str:
    normalized = (
        str(
            value
        )
        .strip()
    )

    if not normalized:
        raise ValueError(
            f"{field} is required"
        )

    return normalized


def _require_aware(
    value: datetime | None,
    field: str,
) -> datetime | None:
    if value is None:
        return None

    if (
        value.tzinfo is None
        or value
        .utcoffset()
        is None
    ):
        raise ValueError(
            f"{field} must be "
            "timezone-aware"
        )

    return value


def _logical_key(
    value: str,
) -> str:
    normalized = (
        " ".join(
            _require_text(
                value,
                "logical_key",
            )
            .upper()
            .split()
        )
    )

    return normalized


def _safe_file_name(
    value: str,
) -> str:
    normalized = (
        _require_text(
            value,
            "file_name",
        )
    )

    if "\x00" in normalized:
        raise ValueError(
            "file_name contains "
            "invalid character"
        )

    if (
        Path(
            normalized
        ).name
        != normalized
    ):
        raise ValueError(
            "file_name must be "
            "a base name"
        )

    return normalized


class BidPackageControlService:
    """
    Authoritative preconstruction document-control boundary.

    Documents are immutable.

    Revisions contain immutable document-reference sets.
    Changing the current package produces a new revision
    or mutates only an unfrozen current draft revision.

    Historical revisions are never rewritten.
    """

    def __init__(
        self,
    ) -> None:
        self._packages: dict[
            str,
            BidPackage,
        ] = {}

        self._documents: dict[
            str,
            BidDocument,
        ] = {}

        self._revisions: dict[
            str,
            BidPackageRevision,
        ] = {}

        self._events: list[
            PackageEvent
        ] = []

    def _emit(
        self,
        *,
        package_id: str,
        event_type: str,
        actor_id: str,
        payload: (
            dict[
                str,
                Any,
            ]
            | None
        ) = None,
    ) -> PackageEvent:
        event = PackageEvent(
            event_id=(
                _new_id(
                    "pevt"
                )
            ),
            package_id=(
                package_id
            ),
            event_type=(
                event_type
            ),
            actor_id=(
                actor_id
            ),
            occurred_at=(
                _utc_now()
            ),
            payload=tuple(
                sorted(
                    (
                        str(
                            key
                        ),
                        str(
                            value
                        ),
                    )
                    for key, value
                    in (
                        payload
                        or {}
                    ).items()
                )
            ),
        )

        self._events.append(
            event
        )

        return event

    def get_package(
        self,
        package_id: str,
    ) -> BidPackage:
        package = (
            self._packages.get(
                package_id
            )
        )

        if package is None:
            raise BidPackageNotFound(
                package_id
            )

        return package

    def get_document(
        self,
        document_id: str,
    ) -> BidDocument:
        document = (
            self._documents.get(
                document_id
            )
        )

        if document is None:
            raise BidDocumentNotFound(
                document_id
            )

        return document

    def get_revision(
        self,
        revision_id: str,
    ) -> BidPackageRevision:
        revision = (
            self._revisions.get(
                revision_id
            )
        )

        if revision is None:
            raise BidRevisionNotFound(
                revision_id
            )

        return revision

    def current_revision(
        self,
        package_id: str,
    ) -> BidPackageRevision:
        package = (
            self.get_package(
                package_id
            )
        )

        return (
            self.get_revision(
                package
                .current_revision_id
            )
        )

    def documents_for_revision(
        self,
        revision_id: str,
    ) -> tuple[
        BidDocument,
        ...
    ]:
        revision = (
            self.get_revision(
                revision_id
            )
        )

        return tuple(
            self.get_document(
                document_id
            )
            for document_id
            in revision
            .document_ids
        )

    def current_documents(
        self,
        package_id: str,
    ) -> tuple[
        BidDocument,
        ...
    ]:
        return (
            self.documents_for_revision(
                self
                .current_revision(
                    package_id
                )
                .revision_id
            )
        )

    def create_package(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        project_name: str,
        city: str,
        source: PackageSource,
        created_by: str,
        opportunity_id: (
            str | None
        ) = None,
        invited_by: (
            str | None
        ) = None,
        gc_name: (
            str | None
        ) = None,
        client_name: (
            str | None
        ) = None,
        due_at: (
            datetime | None
        ) = None,
    ) -> BidPackage:
        tenant_id = _require_text(
            tenant_id,
            "tenant_id",
        )

        business_unit_id = (
            _require_text(
                business_unit_id,
                "business_unit_id",
            )
        )

        project_name = (
            _require_text(
                project_name,
                "project_name",
            )
        )

        city = _require_text(
            city,
            "city",
        )

        created_by = (
            _require_text(
                created_by,
                "created_by",
            )
        )

        due_at = _require_aware(
            due_at,
            "due_at",
        )

        package_id = _new_id(
            "bpkg"
        )

        revision_id = _new_id(
            "brev"
        )

        now = _utc_now()

        revision = (
            BidPackageRevision(
                revision_id=(
                    revision_id
                ),
                package_id=(
                    package_id
                ),
                label="INITIAL",
                parent_revision_id=None,
                reason=(
                    "Initial bid package"
                ),
                issued_at=now,
                created_at=now,
                created_by=(
                    created_by
                ),
                document_ids=(),
            )
        )

        package = BidPackage(
            package_id=(
                package_id
            ),
            tenant_id=(
                tenant_id
            ),
            business_unit_id=(
                business_unit_id
            ),
            opportunity_id=(
                opportunity_id
            ),
            project_name=(
                project_name
            ),
            city=city,
            source=source,
            invited_by=(
                invited_by
            ),
            gc_name=gc_name,
            client_name=(
                client_name
            ),
            due_at=due_at,
            current_revision_id=(
                revision_id
            ),
            created_at=now,
            created_by=(
                created_by
            ),
        )

        self._packages[
            package_id
        ] = package

        self._revisions[
            revision_id
        ] = revision

        self._emit(
            package_id=(
                package_id
            ),
            event_type=(
                "bid_package.created"
            ),
            actor_id=(
                created_by
            ),
            payload={
                "revision_id":
                    revision_id,
                "project_name":
                    project_name,
                "source":
                    source.value,
            },
        )

        return package

    def create_revision(
        self,
        *,
        package_id: str,
        actor_id: str,
        label: str,
        reason: str,
        issued_at: (
            datetime | None
        ) = None,
    ) -> BidPackageRevision:
        package = (
            self.get_package(
                package_id
            )
        )

        actor_id = _require_text(
            actor_id,
            "actor_id",
        )

        label = _require_text(
            label,
            "label",
        ).upper()

        reason = _require_text(
            reason,
            "reason",
        )

        issued_at = (
            _require_aware(
                issued_at,
                "issued_at",
            )
            or _utc_now()
        )

        for existing in (
            self._revisions
            .values()
        ):
            if (
                existing.package_id
                == package_id
                and existing.label
                == label
            ):
                raise DocumentControlError(
                    "revision label "
                    "already exists"
                )

        parent = (
            self.current_revision(
                package_id
            )
        )

        revision = (
            BidPackageRevision(
                revision_id=(
                    _new_id(
                        "brev"
                    )
                ),
                package_id=(
                    package_id
                ),
                label=label,
                parent_revision_id=(
                    parent
                    .revision_id
                ),
                reason=reason,
                issued_at=(
                    issued_at
                ),
                created_at=(
                    _utc_now()
                ),
                created_by=(
                    actor_id
                ),
                document_ids=(
                    parent
                    .document_ids
                ),
            )
        )

        self._revisions[
            revision
            .revision_id
        ] = revision

        self._packages[
            package_id
        ] = replace(
            package,
            current_revision_id=(
                revision
                .revision_id
            ),
        )

        self._emit(
            package_id=(
                package_id
            ),
            event_type=(
                "bid_package.revision_created"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "revision_id":
                    revision
                    .revision_id,
                "parent_revision_id":
                    parent
                    .revision_id,
                "label":
                    label,
                "reason":
                    reason,
            },
        )

        return revision

    def _assert_mutable(
        self,
        revision: BidPackageRevision,
    ) -> None:
        if revision.frozen:
            raise FrozenRevisionError(
                "current revision is "
                "frozen; create a new "
                "revision before changing "
                "document control"
            )

    def _current_by_logical_key(
        self,
        package_id: str,
    ) -> dict[
        str,
        BidDocument,
    ]:
        result = {}

        for document in (
            self.current_documents(
                package_id
            )
        ):
            if (
                document.logical_key
                in result
            ):
                raise DocumentControlError(
                    "current revision "
                    "contains duplicate "
                    "logical document key"
                )

            result[
                document.logical_key
            ] = document

        return result

    def _duplicate_hash(
        self,
        *,
        package_id: str,
        sha256: str,
    ) -> BidDocument | None:
        for document in (
            self._documents
            .values()
        ):
            if (
                document.package_id
                == package_id
                and document.sha256
                .lower()
                == sha256.lower()
            ):
                return document

        return None

    def ingest_document(
        self,
        *,
        package_id: str,
        actor_id: str,
        file_name: str,
        sha256: str,
        size_bytes: int,
        kind: DocumentKind,
        logical_key: str,
        source_ref: str,
        discipline: (
            Discipline
        ) = Discipline.GENERAL,
        revision_label: (
            str | None
        ) = None,
        issue_date: (
            date | None
        ) = None,
        sheet_count: (
            int | None
        ) = None,
    ) -> BidDocument:
        self.get_package(
            package_id
        )

        actor_id = _require_text(
            actor_id,
            "actor_id",
        )

        file_name = _safe_file_name(
            file_name
        )

        source_ref = _require_text(
            source_ref,
            "source_ref",
        )

        logical_key = _logical_key(
            logical_key
        )

        sha256 = (
            str(
                sha256
            )
            .strip()
            .lower()
        )

        if not SHA256_RE.fullmatch(
            sha256
        ):
            raise ValueError(
                "sha256 must contain "
                "64 hexadecimal characters"
            )

        if (
            isinstance(
                size_bytes,
                bool,
            )
            or int(
                size_bytes
            )
            <= 0
        ):
            raise ValueError(
                "size_bytes must be "
                "positive"
            )

        size_bytes = int(
            size_bytes
        )

        if (
            sheet_count is not None
            and (
                isinstance(
                    sheet_count,
                    bool,
                )
                or int(
                    sheet_count
                )
                <= 0
            )
        ):
            raise ValueError(
                "sheet_count must be "
                "positive when supplied"
            )

        if sheet_count is not None:
            sheet_count = int(
                sheet_count
            )

        revision = (
            self.current_revision(
                package_id
            )
        )

        self._assert_mutable(
            revision
        )

        duplicate = (
            self._duplicate_hash(
                package_id=(
                    package_id
                ),
                sha256=sha256,
            )
        )

        if duplicate is not None:
            raise DuplicateDocumentError(
                "identical document "
                "content already exists "
                f"as {duplicate.document_id}"
            )

        current_map = (
            self._current_by_logical_key(
                package_id
            )
        )

        prior = current_map.get(
            logical_key
        )

        document = BidDocument(
            document_id=(
                _new_id(
                    "bdoc"
                )
            ),
            package_id=(
                package_id
            ),
            file_name=(
                file_name
            ),
            sha256=sha256,
            size_bytes=(
                size_bytes
            ),
            kind=kind,
            discipline=(
                discipline
            ),
            logical_key=(
                logical_key
            ),
            source_ref=(
                source_ref
            ),
            revision_label=(
                revision_label
            ),
            issue_date=(
                issue_date
            ),
            sheet_count=(
                sheet_count
            ),
            supersedes_document_id=(
                prior.document_id
                if prior
                is not None
                else None
            ),
            created_at=(
                _utc_now()
            ),
            created_by=(
                actor_id
            ),
        )

        self._documents[
            document
            .document_id
        ] = document

        document_ids = [
            document_id
            for document_id
            in revision.document_ids
            if (
                prior is None
                or document_id
                != prior.document_id
            )
        ]

        document_ids.append(
            document.document_id
        )

        updated_revision = (
            replace(
                revision,
                document_ids=tuple(
                    document_ids
                ),
            )
        )

        self._revisions[
            revision
            .revision_id
        ] = updated_revision

        self._emit(
            package_id=(
                package_id
            ),
            event_type=(
                "bid_document.ingested"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "document_id":
                    document
                    .document_id,
                "logical_key":
                    logical_key,
                "kind":
                    kind.value,
                "discipline":
                    discipline.value,
                "revision_id":
                    revision
                    .revision_id,
                "supersedes":
                    document
                    .supersedes_document_id
                    or "",
            },
        )

        return document

    def remove_document(
        self,
        *,
        package_id: str,
        document_id: str,
        actor_id: str,
        reason: str,
    ) -> BidPackageRevision:
        revision = (
            self.current_revision(
                package_id
            )
        )

        self._assert_mutable(
            revision
        )

        document = (
            self.get_document(
                document_id
            )
        )

        if (
            document.package_id
            != package_id
        ):
            raise DocumentControlError(
                "document belongs to "
                "another package"
            )

        if (
            document_id
            not in revision
            .document_ids
        ):
            raise DocumentControlError(
                "document is not part "
                "of current revision"
            )

        reason = _require_text(
            reason,
            "reason",
        )

        updated = replace(
            revision,
            document_ids=tuple(
                existing
                for existing
                in revision
                .document_ids
                if existing
                != document_id
            ),
        )

        self._revisions[
            revision
            .revision_id
        ] = updated

        self._emit(
            package_id=(
                package_id
            ),
            event_type=(
                "bid_document.removed"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "document_id":
                    document_id,
                "revision_id":
                    revision
                    .revision_id,
                "reason":
                    reason,
            },
        )

        return updated

    def freeze_current_revision(
        self,
        *,
        package_id: str,
        actor_id: str,
        note: str,
    ) -> BidPackageRevision:
        revision = (
            self.current_revision(
                package_id
            )
        )

        note = _require_text(
            note,
            "note",
        )

        if revision.frozen:
            return revision

        frozen = replace(
            revision,
            frozen=True,
            freeze_note=note,
        )

        self._revisions[
            revision
            .revision_id
        ] = frozen

        self._emit(
            package_id=(
                package_id
            ),
            event_type=(
                "bid_package.revision_frozen"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "revision_id":
                    revision
                    .revision_id,
                "note":
                    note,
            },
        )

        return frozen

    def update_due_at(
        self,
        *,
        package_id: str,
        actor_id: str,
        due_at: (
            datetime | None
        ),
    ) -> BidPackage:
        package = (
            self.get_package(
                package_id
            )
        )

        due_at = _require_aware(
            due_at,
            "due_at",
        )

        updated = replace(
            package,
            due_at=due_at,
        )

        self._packages[
            package_id
        ] = updated

        self._emit(
            package_id=(
                package_id
            ),
            event_type=(
                "bid_package.due_at_changed"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "due_at":
                    due_at.isoformat()
                    if due_at
                    else "",
            },
        )

        return updated

    def diff_revisions(
        self,
        *,
        old_revision_id: str,
        new_revision_id: str,
    ) -> RevisionDiff:
        old = (
            self.get_revision(
                old_revision_id
            )
        )

        new = (
            self.get_revision(
                new_revision_id
            )
        )

        if (
            old.package_id
            != new.package_id
        ):
            raise DocumentControlError(
                "cannot compare revisions "
                "from different packages"
            )

        old_docs = {
            self.get_document(
                document_id
            ).logical_key:
                self.get_document(
                    document_id
                )

            for document_id
            in old.document_ids
        }

        new_docs = {
            self.get_document(
                document_id
            ).logical_key:
                self.get_document(
                    document_id
                )

            for document_id
            in new.document_ids
        }

        old_keys = set(
            old_docs
        )

        new_keys = set(
            new_docs
        )

        added = tuple(
            new_docs[
                key
            ].document_id
            for key
            in sorted(
                new_keys
                - old_keys
            )
        )

        removed = tuple(
            old_docs[
                key
            ].document_id
            for key
            in sorted(
                old_keys
                - new_keys
            )
        )

        replacements = []

        unchanged = []

        for key in sorted(
            old_keys
            & new_keys
        ):
            old_doc = (
                old_docs[
                    key
                ]
            )

            new_doc = (
                new_docs[
                    key
                ]
            )

            if (
                old_doc.document_id
                == new_doc.document_id
            ):
                unchanged.append(
                    old_doc
                    .document_id
                )

            else:
                replacements.append(
                    (
                        old_doc
                        .document_id,
                        new_doc
                        .document_id,
                    )
                )

        return RevisionDiff(
            old_revision_id=(
                old_revision_id
            ),
            new_revision_id=(
                new_revision_id
            ),
            added_document_ids=(
                added
            ),
            removed_document_ids=(
                removed
            ),
            replaced_document_pairs=tuple(
                replacements
            ),
            unchanged_document_ids=tuple(
                unchanged
            ),
        )

    def readiness(
        self,
        *,
        package_id: str,
        as_of: (
            datetime | None
        ) = None,
    ) -> PackageReadiness:
        package = (
            self.get_package(
                package_id
            )
        )

        revision = (
            self.current_revision(
                package_id
            )
        )

        documents = (
            self.current_documents(
                package_id
            )
        )

        as_of = (
            _require_aware(
                as_of,
                "as_of",
            )
            or _utc_now()
        )

        findings = []

        if not documents:
            findings.append(
                ControlFinding(
                    code=(
                        "CURRENT_PACKAGE_EMPTY"
                    ),
                    severity=(
                        ControlSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Current bid package "
                        "contains no documents."
                    ),
                    revision_id=(
                        revision
                        .revision_id
                    ),
                )
            )

        plan_docs = tuple(
            document
            for document
            in documents
            if (
                document.kind
                == DocumentKind.PLANS
            )
        )

        if not plan_docs:
            findings.append(
                ControlFinding(
                    code=(
                        "PLAN_SET_MISSING"
                    ),
                    severity=(
                        ControlSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Authoritative current "
                        "package has no plan set."
                    ),
                    revision_id=(
                        revision
                        .revision_id
                    ),
                )
            )

        specification_docs = (
            tuple(
                document
                for document
                in documents
                if (
                    document.kind
                    == DocumentKind
                    .SPECIFICATIONS
                )
            )
        )

        if not specification_docs:
            findings.append(
                ControlFinding(
                    code=(
                        "SPECIFICATIONS_MISSING"
                    ),
                    severity=(
                        ControlSeverity
                        .REVIEW
                    ),
                    message=(
                        "No specifications are "
                        "present in the current "
                        "bid package."
                    ),
                    revision_id=(
                        revision
                        .revision_id
                    ),
                )
            )

        logical_keys = set()

        for document in (
            documents
        ):
            if (
                document.logical_key
                in logical_keys
            ):
                findings.append(
                    ControlFinding(
                        code=(
                            "DUPLICATE_LOGICAL_KEY"
                        ),
                        severity=(
                            ControlSeverity
                            .BLOCKER
                        ),
                        message=(
                            "Current package "
                            "contains duplicate "
                            "logical document keys."
                        ),
                        document_id=(
                            document
                            .document_id
                        ),
                        revision_id=(
                            revision
                            .revision_id
                        ),
                        source_ref=(
                            document
                            .source_ref
                        ),
                    )
                )

            logical_keys.add(
                document
                .logical_key
            )

            if (
                document
                .supersedes_document_id
                is not None
            ):
                try:
                    prior = (
                        self.get_document(
                            document
                            .supersedes_document_id
                        )
                    )

                except BidDocumentNotFound:
                    findings.append(
                        ControlFinding(
                            code=(
                                "SUPERSEDED_DOCUMENT_MISSING"
                            ),
                            severity=(
                                ControlSeverity
                                .BLOCKER
                            ),
                            message=(
                                "Replacement document "
                                "references a missing "
                                "prior document."
                            ),
                            document_id=(
                                document
                                .document_id
                            ),
                        )
                    )

                else:
                    if (
                        prior.logical_key
                        != document
                        .logical_key
                    ):
                        findings.append(
                            ControlFinding(
                                code=(
                                    "DOCUMENT_LINEAGE_MISMATCH"
                                ),
                                severity=(
                                    ControlSeverity
                                    .BLOCKER
                                ),
                                message=(
                                    "Replacement document "
                                    "does not match the "
                                    "logical key of the "
                                    "document it supersedes."
                                ),
                                document_id=(
                                    document
                                    .document_id
                                ),
                            )
                        )

        if (
            revision.label
            == "INITIAL"
            and any(
                document.kind
                == DocumentKind.ADDENDUM
                for document
                in documents
            )
        ):
            findings.append(
                ControlFinding(
                    code=(
                        "ADDENDUM_ON_INITIAL_REVISION"
                    ),
                    severity=(
                        ControlSeverity.REVIEW
                    ),
                    message=(
                        "Addendum exists on the "
                        "initial package revision. "
                        "Confirm revision chronology."
                    ),
                    revision_id=(
                        revision
                        .revision_id
                    ),
                )
            )

        due_in_seconds = None

        if package.due_at is None:
            findings.append(
                ControlFinding(
                    code=(
                        "BID_DUE_DATE_MISSING"
                    ),
                    severity=(
                        ControlSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Bid due date/time has "
                        "not been established."
                    ),
                )
            )

        else:
            due_in_seconds = int(
                (
                    package.due_at
                    - as_of
                )
                .total_seconds()
            )

            if due_in_seconds <= 0:
                findings.append(
                    ControlFinding(
                        code=(
                            "BID_DUE_DATE_PASSED"
                        ),
                        severity=(
                            ControlSeverity
                            .BLOCKER
                        ),
                        message=(
                            "Bid due date/time "
                            "has already passed."
                        ),
                    )
                )

            elif (
                due_in_seconds
                <= 24 * 60 * 60
            ):
                findings.append(
                    ControlFinding(
                        code=(
                            "BID_DUE_WITHIN_24_HOURS"
                        ),
                        severity=(
                            ControlSeverity
                            .REVIEW
                        ),
                        message=(
                            "Bid is due within "
                            "24 hours."
                        ),
                    )
                )

        if revision.frozen:
            findings.append(
                ControlFinding(
                    code=(
                        "CURRENT_REVISION_FROZEN"
                    ),
                    severity=(
                        ControlSeverity.INFO
                    ),
                    message=(
                        "Current document package "
                        "revision is frozen."
                    ),
                    revision_id=(
                        revision
                        .revision_id
                    ),
                )
            )

        blockers = tuple(
            finding
            for finding
            in findings
            if (
                finding.severity
                == ControlSeverity
                .BLOCKER
            )
        )

        return PackageReadiness(
            package_id=(
                package_id
            ),
            revision_id=(
                revision
                .revision_id
            ),
            ready=(
                not blockers
            ),
            findings=tuple(
                findings
            ),
            current_document_ids=(
                revision
                .document_ids
            ),
            due_in_seconds=(
                due_in_seconds
            ),
        )

    def execution_manifest(
        self,
        *,
        package_id: str,
        as_of: (
            datetime | None
        ) = None,
    ) -> PackageExecutionManifest:
        package = (
            self.get_package(
                package_id
            )
        )

        revision = (
            self.current_revision(
                package_id
            )
        )

        documents = (
            self.current_documents(
                package_id
            )
        )

        readiness = (
            self.readiness(
                package_id=(
                    package_id
                ),
                as_of=as_of,
            )
        )

        plan_ids = tuple(
            document.document_id
            for document
            in documents
            if (
                document.kind
                == DocumentKind.PLANS
            )
        )

        specification_ids = (
            tuple(
                document.document_id
                for document
                in documents
                if (
                    document.kind
                    == DocumentKind
                    .SPECIFICATIONS
                )
            )
        )

        addendum_ids = tuple(
            document.document_id
            for document
            in documents
            if (
                document.kind
                == DocumentKind.ADDENDUM
            )
        )

        core = set(
            plan_ids
            + specification_ids
            + addendum_ids
        )

        supporting = tuple(
            document.document_id
            for document
            in documents
            if (
                document.document_id
                not in core
            )
        )

        return PackageExecutionManifest(
            package_id=(
                package_id
            ),
            revision_id=(
                revision
                .revision_id
            ),
            previous_revision_id=(
                revision
                .parent_revision_id
            ),
            project_name=(
                package
                .project_name
            ),
            city=(
                package.city
            ),
            opportunity_id=(
                package
                .opportunity_id
            ),
            gc_name=(
                package.gc_name
            ),
            client_name=(
                package
                .client_name
            ),
            package_source=(
                package.source.value
            ),
            due_at=(
                package.due_at
            ),
            plan_document_ids=(
                plan_ids
            ),
            specification_document_ids=(
                specification_ids
            ),
            addendum_document_ids=(
                addendum_ids
            ),
            supporting_document_ids=(
                supporting
            ),
            all_document_ids=(
                revision
                .document_ids
            ),
            ready_for_execution=(
                readiness.ready
            ),
            findings=(
                readiness.findings
            ),
        )

    def chronology(
        self,
        *,
        package_id: str,
    ) -> tuple[
        PackageEvent,
        ...
    ]:
        self.get_package(
            package_id
        )

        return tuple(
            sorted(
                (
                    event
                    for event
                    in self._events
                    if (
                        event.package_id
                        == package_id
                    )
                ),
                key=lambda event:
                    (
                        event
                        .occurred_at,
                        event
                        .event_id,
                    ),
            )
        )

    def revisions(
        self,
        *,
        package_id: str,
    ) -> tuple[
        BidPackageRevision,
        ...
    ]:
        self.get_package(
            package_id
        )

        return tuple(
            sorted(
                (
                    revision
                    for revision
                    in self._revisions
                    .values()
                    if (
                        revision.package_id
                        == package_id
                    )
                ),
                key=lambda revision:
                    (
                        revision
                        .created_at,
                        revision
                        .revision_id,
                    ),
            )
        )
