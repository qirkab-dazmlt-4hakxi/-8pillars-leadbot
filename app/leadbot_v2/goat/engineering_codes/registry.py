from __future__ import annotations

from collections import defaultdict

from .models import (
    AdoptionStatus,
    CodeAuthority,
    CodeResolutionError,
    EffectiveCodeStack,
)


AUTHORITY_SCORE = {
    CodeAuthority.OFFICIAL: 100,
    CodeAuthority.ADOPTED: 90,
    CodeAuthority.REFERENCE_STANDARD: 70,
    CodeAuthority.GUIDANCE: 40,
    CodeAuthority.UNVERIFIED: 0,
}


class EngineeringCodeRegistry:
    def __init__(
        self,
        *,
        jurisdiction_graph,
    ) -> None:
        self.jurisdictions = (
            jurisdiction_graph
        )

        self._adoptions = {}
        self._amendments = {}

    def add_adoption(
        self,
        adoption,
    ) -> None:
        if adoption.adoption_id in self._adoptions:
            raise CodeResolutionError(
                "duplicate adoption"
            )

        self.jurisdictions.get(
            adoption.jurisdiction_id
        )

        self._adoptions[
            adoption.adoption_id
        ] = adoption

    def add_amendment(
        self,
        amendment,
    ) -> None:
        if (
            amendment.amendment_id
            in self._amendments
        ):
            raise CodeResolutionError(
                "duplicate amendment"
            )

        self.jurisdictions.get(
            amendment.jurisdiction_id
        )

        self._amendments[
            amendment.amendment_id
        ] = amendment

    @staticmethod
    def _active_on(
        start,
        end,
        when,
    ) -> bool:
        if when < start:
            return False

        if (
            end is not None
            and when > end
        ):
            return False

        return True

    def active_adoptions(
        self,
        *,
        project_jurisdiction_id,
        discipline,
        project_date,
    ):
        result = []

        for adoption in self._adoptions.values():
            if (
                adoption.discipline
                != discipline
            ):
                continue

            if (
                adoption.status
                is not AdoptionStatus.ACTIVE
            ):
                continue

            if not self.jurisdictions.contains(
                project_jurisdiction_id,
                adoption.jurisdiction_id,
            ):
                continue

            if not self._active_on(
                adoption.effective_from,
                adoption.effective_until,
                project_date,
            ):
                continue

            result.append(
                adoption
            )

        return tuple(
            result
        )

    def resolve(
        self,
        *,
        project_jurisdiction_id,
        discipline,
        project_date,
        code_family=None,
    ):
        candidates = list(
            self.active_adoptions(
                project_jurisdiction_id=(
                    project_jurisdiction_id
                ),
                discipline=discipline,
                project_date=project_date,
            )
        )

        if code_family:
            candidates = [
                item
                for item in candidates
                if (
                    item.code_family
                    == code_family
                )
            ]

        if not candidates:
            raise CodeResolutionError(
                "no active adopted code found "
                "for requested jurisdiction/discipline/date"
            )

        candidates.sort(
            key=lambda item: (
                self.jurisdictions.specificity(
                    item.jurisdiction_id
                ),
                AUTHORITY_SCORE[
                    item.authority
                ],
                item.effective_from,
                item.adoption_id,
            ),
            reverse=True,
        )

        winner = candidates[0]

        winner_specificity = (
            self.jurisdictions
            .specificity(
                winner.jurisdiction_id
            )
        )

        conflicts = []

        for candidate in candidates[1:]:
            if (
                candidate.code_family
                != winner.code_family
            ):
                continue

            if (
                self.jurisdictions.specificity(
                    candidate.jurisdiction_id
                )
                == winner_specificity
                and candidate.edition
                != winner.edition
            ):
                conflicts.append(
                    candidate.adoption_id
                )

        path = (
            self.jurisdictions
            .path_root_to_leaf(
                project_jurisdiction_id
            )
        )

        path_ids = tuple(
            node.jurisdiction_id
            for node in path
        )

        amendments = []

        for amendment in self._amendments.values():
            if (
                amendment.discipline
                != discipline
            ):
                continue

            if (
                amendment.code_family
                != winner.code_family
            ):
                continue

            if (
                amendment.jurisdiction_id
                not in path_ids
            ):
                continue

            if not self._active_on(
                amendment.effective_from,
                amendment.effective_until,
                project_date,
            ):
                continue

            amendments.append(
                amendment
            )

        amendments.sort(
            key=lambda item: (
                self.jurisdictions.specificity(
                    item.jurisdiction_id
                ),
                item.section,
                item.amendment_id,
            )
        )

        source_fact_ids = [
            winner.source_fact_id
        ]

        source_fact_ids.extend(
            amendment.source_fact_id
            for amendment
            in amendments
        )

        authoritative = (
            winner.authority
            in {
                CodeAuthority.OFFICIAL,
                CodeAuthority.ADOPTED,
            }
            and not conflicts
            and all(
                amendment.authority
                in {
                    CodeAuthority.OFFICIAL,
                    CodeAuthority.ADOPTED,
                }
                for amendment
                in amendments
            )
        )

        return EffectiveCodeStack(
            jurisdiction_path=(
                path_ids
            ),
            adoption=winner,
            amendments=tuple(
                amendments
            ),
            unresolved_conflicts=tuple(
                conflicts
            ),
            source_fact_ids=tuple(
                dict.fromkeys(
                    source_fact_ids
                )
            ),
            authoritative=(
                authoritative
            ),
        )
