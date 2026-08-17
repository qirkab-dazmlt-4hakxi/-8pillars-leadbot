from __future__ import annotations

from .models import (
    JurisdictionResolutionError,
    JurisdictionType,
)


SPECIFICITY = {
    JurisdictionType.STATE: 10,
    JurisdictionType.COUNTY: 20,
    JurisdictionType.CITY: 30,
    JurisdictionType.SPECIAL_DISTRICT: 40,
    JurisdictionType.AHJ: 50,
}


class JurisdictionGraph:
    """
    Explicit jurisdiction ancestry.

    GOAT does not infer legal authority merely from a postal address.
    Resolved project locations must be mapped to a verified jurisdiction
    record backed by official source evidence.
    """

    def __init__(self) -> None:
        self._nodes = {}

    def add(self, jurisdiction) -> None:
        if jurisdiction.jurisdiction_id in self._nodes:
            raise JurisdictionResolutionError(
                "duplicate jurisdiction"
            )

        if (
            jurisdiction.state_code.upper()
            != "TX"
        ):
            raise JurisdictionResolutionError(
                "Texas jurisdiction fabric only accepts TX nodes"
            )

        if (
            jurisdiction.parent_id is not None
            and jurisdiction.parent_id
            not in self._nodes
        ):
            raise JurisdictionResolutionError(
                "parent jurisdiction must exist first"
            )

        cursor = jurisdiction.parent_id
        seen = {
            jurisdiction.jurisdiction_id
        }

        while cursor is not None:
            if cursor in seen:
                raise JurisdictionResolutionError(
                    "jurisdiction cycle detected"
                )

            seen.add(cursor)

            parent = self._nodes.get(
                cursor
            )

            if parent is None:
                break

            cursor = parent.parent_id

        self._nodes[
            jurisdiction.jurisdiction_id
        ] = jurisdiction

    def get(self, jurisdiction_id):
        try:
            return self._nodes[
                jurisdiction_id
            ]
        except KeyError as exc:
            raise JurisdictionResolutionError(
                f"unknown jurisdiction: "
                f"{jurisdiction_id}"
            ) from exc

    def ancestry(
        self,
        jurisdiction_id,
    ):
        result = []

        cursor = self.get(
            jurisdiction_id
        )

        while cursor is not None:
            result.append(
                cursor
            )

            cursor = (
                self._nodes.get(
                    cursor.parent_id
                )
                if cursor.parent_id
                else None
            )

        return tuple(
            result
        )

    def path_root_to_leaf(
        self,
        jurisdiction_id,
    ):
        return tuple(
            reversed(
                self.ancestry(
                    jurisdiction_id
                )
            )
        )

    def contains(
        self,
        project_jurisdiction_id,
        candidate_jurisdiction_id,
    ) -> bool:
        return candidate_jurisdiction_id in {
            node.jurisdiction_id
            for node
            in self.ancestry(
                project_jurisdiction_id
            )
        }

    def specificity(
        self,
        jurisdiction_id,
    ) -> int:
        node = self.get(
            jurisdiction_id
        )

        depth = len(
            self.ancestry(
                jurisdiction_id
            )
        )

        return (
            SPECIFICITY[
                node.jurisdiction_type
            ]
            + depth
        )
