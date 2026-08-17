from __future__ import annotations

from .models import (
    EngineeringDiscipline,
    StructureContext,
)


class DisciplineApplicabilityEngine:
    """
    Determines which engineering domains require evaluation.

    This is intentionally conservative: complex or underground scopes activate
    more review domains rather than silently excluding them.
    """

    BASE = {
        EngineeringDiscipline.ARCHITECTURAL,
        EngineeringDiscipline.STRUCTURAL,
        EngineeringDiscipline.CIVIL,
        EngineeringDiscipline.MECHANICAL,
        EngineeringDiscipline.ELECTRICAL,
        EngineeringDiscipline.PLUMBING,
        EngineeringDiscipline.FIRE,
        EngineeringDiscipline.ACCESSIBILITY,
    }

    def determine(
        self,
        context,
    ):
        result = set(
            self.BASE
        )

        tags = {
            tag.lower()
            for tag
            in context.project_tags
        }

        if (
            context.structure_context
            in {
                StructureContext.BELOW_GRADE,
                StructureContext.UNDERGROUND,
                StructureContext.MIXED,
            }
        ):
            result.update(
                {
                    EngineeringDiscipline.GEOTECHNICAL,
                    EngineeringDiscipline.WATERPROOFING,
                    EngineeringDiscipline.EARTHWORK,
                    EngineeringDiscipline.ENVIRONMENTAL,
                    EngineeringDiscipline.CONCRETE,
                }
            )

        if (
            "concrete"
            in tags
            or "foundation"
            in tags
            or context.stories_below_grade > 0
        ):
            result.add(
                EngineeringDiscipline.CONCRETE
            )

        if (
            "steel"
            in tags
            or "structural_steel"
            in tags
        ):
            result.add(
                EngineeringDiscipline.STEEL
            )

        if (
            "excavation"
            in tags
            or "retaining_wall"
            in tags
            or "deep_foundation"
            in tags
        ):
            result.update(
                {
                    EngineeringDiscipline.GEOTECHNICAL,
                    EngineeringDiscipline.EARTHWORK,
                }
            )

        if (
            "energy_model"
            in tags
            or "envelope"
            in tags
        ):
            result.add(
                EngineeringDiscipline.ENERGY
            )

        return frozenset(
            result
        )


class RequirementApplicability:
    def applies(
        self,
        requirement,
        context,
    ) -> bool:
        if (
            requirement.jurisdictions
            and context.jurisdiction_id
            not in requirement.jurisdictions
        ):
            return False

        if (
            requirement
            .applicable_structure_contexts
            and context.structure_context
            not in requirement
            .applicable_structure_contexts
        ):
            return False

        if (
            requirement.required_tags
            and not requirement.required_tags
            .issubset(
                context.project_tags
            )
        ):
            return False

        return True
