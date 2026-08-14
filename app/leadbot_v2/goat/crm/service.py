from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from leadbot_v2.goat.data_spine.models import (
    Contact,
    Lead,
    Opportunity,
    OpportunityStage,
    Project,
    ProjectState,
    TERMINAL_OPPORTUNITY_STAGES,
    new_id,
    utc_now,
)
from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)


class CRMValidationError(ValueError):
    pass


class CRMTransitionError(RuntimeError):
    pass


class GoatCRM:
    """
    GOAT CRM domain service.

    The CRM owns business transitions.
    Persistence is delegated to the Data Spine.
    """

    def __init__(
        self,
        spine: InMemoryDataSpine,
    ) -> None:
        self.spine = spine

    def create_contact(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        actor_id: str,
        display_name: str,
        company_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        source: str | None = None,
    ) -> Contact:
        contact = Contact(
            entity_id=new_id("contact"),
            tenant_id=tenant_id,
            business_unit_id=business_unit_id,
            created_at=utc_now(),
            updated_at=utc_now(),
            display_name=display_name.strip(),
            company_name=company_name,
            email=email,
            phone=phone,
            source=source,
        )

        return self.spine.create(
            contact,
            actor_id=actor_id,
            event_type="crm.contact.created",
        )

    def create_lead(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        actor_id: str,
        title: str,
        source: str,
        contact_id: str | None = None,
        owner_user_id: str | None = None,
        description: str = "",
        next_action: str = "",
        next_action_due_at: datetime | None = None,
        source_url: str | None = None,
    ) -> Lead:
        if bool(next_action.strip()) != bool(next_action_due_at):
            raise CRMValidationError(
                "next action and due date must be set together"
            )

        if contact_id:
            self.spine.get(
                entity_id=contact_id,
                tenant_id=tenant_id,
                expected_type=Contact,
            )

        lead = Lead(
            entity_id=new_id("lead"),
            tenant_id=tenant_id,
            business_unit_id=business_unit_id,
            created_at=utc_now(),
            updated_at=utc_now(),
            title=title,
            source=source,
            contact_id=contact_id,
            owner_user_id=owner_user_id,
            description=description,
            next_action=next_action,
            next_action_due_at=next_action_due_at,
            source_url=source_url,
        )

        return self.spine.create(
            lead,
            actor_id=actor_id,
            event_type="crm.lead.created",
            payload={
                "source": source,
                "contact_id": contact_id,
            },
        )

    def set_lead_next_action(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        lead_id: str,
        action: str,
        due_at: datetime,
    ) -> Lead:
        if not action.strip():
            raise CRMValidationError("next action required")

        lead = self.spine.get(
            entity_id=lead_id,
            tenant_id=tenant_id,
            expected_type=Lead,
        )

        candidate = replace(
            lead,
            next_action=action.strip(),
            next_action_due_at=due_at,
        )

        return self.spine.update(
            candidate,
            tenant_id=tenant_id,
            expected_version=lead.version,
            actor_id=actor_id,
            event_type="crm.lead.next_action.set",
            payload={
                "next_action": action.strip(),
                "due_at": due_at.isoformat(),
            },
        )

    def promote_lead(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        lead_id: str,
        opportunity_title: str | None = None,
        bid_due_at: datetime | None = None,
        estimated_value_cents: int | None = None,
    ) -> Opportunity:
        lead = self.spine.get(
            entity_id=lead_id,
            tenant_id=tenant_id,
            expected_type=Lead,
        )

        opportunity = Opportunity(
            entity_id=new_id("opp"),
            tenant_id=lead.tenant_id,
            business_unit_id=lead.business_unit_id,
            created_at=utc_now(),
            updated_at=utc_now(),
            title=opportunity_title or lead.title,
            lead_id=lead.entity_id,
            contact_id=lead.contact_id,
            owner_user_id=lead.owner_user_id,
            stage=OpportunityStage.QUALIFYING,
            estimated_value_cents=estimated_value_cents,
            bid_due_at=bid_due_at,
            source=lead.source,
            next_action=lead.next_action,
            next_action_due_at=lead.next_action_due_at,
        )

        created = self.spine.create(
            opportunity,
            actor_id=actor_id,
            event_type="crm.opportunity.created_from_lead",
            payload={
                "lead_id": lead.entity_id,
                "contact_id": lead.contact_id,
                "source": lead.source,
            },
        )

        self.spine.append_event(
            tenant_id=tenant_id,
            aggregate_type="Lead",
            aggregate_id=lead.entity_id,
            event_type="crm.lead.promoted",
            actor_id=actor_id,
            payload={
                "opportunity_id": created.entity_id,
            },
        )

        return created

    def set_opportunity_stage(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        opportunity_id: str,
        stage: OpportunityStage,
        lost_reason: str | None = None,
    ) -> Opportunity:
        opportunity = self.spine.get(
            entity_id=opportunity_id,
            tenant_id=tenant_id,
            expected_type=Opportunity,
        )

        if (
            stage == OpportunityStage.LOST
            and not (lost_reason or "").strip()
        ):
            raise CRMValidationError(
                "lost opportunities require a reason"
            )

        if (
            opportunity.stage in TERMINAL_OPPORTUNITY_STAGES
            and stage != opportunity.stage
        ):
            raise CRMTransitionError(
                "terminal opportunity stage cannot be changed "
                "without an explicit reopen workflow"
            )

        candidate = replace(
            opportunity,
            stage=stage,
            lost_reason=(
                lost_reason.strip()
                if lost_reason
                else opportunity.lost_reason
            ),
        )

        return self.spine.update(
            candidate,
            tenant_id=tenant_id,
            expected_version=opportunity.version,
            actor_id=actor_id,
            event_type="crm.opportunity.stage_changed",
            payload={
                "from": opportunity.stage.value,
                "to": stage.value,
                "lost_reason": lost_reason,
            },
        )

    def set_opportunity_next_action(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        opportunity_id: str,
        action: str,
        due_at: datetime,
    ) -> Opportunity:
        if not action.strip():
            raise CRMValidationError("next action required")

        opportunity = self.spine.get(
            entity_id=opportunity_id,
            tenant_id=tenant_id,
            expected_type=Opportunity,
        )

        if opportunity.stage in TERMINAL_OPPORTUNITY_STAGES:
            raise CRMTransitionError(
                "terminal opportunity does not accept next actions"
            )

        candidate = replace(
            opportunity,
            next_action=action.strip(),
            next_action_due_at=due_at,
        )

        return self.spine.update(
            candidate,
            tenant_id=tenant_id,
            expected_version=opportunity.version,
            actor_id=actor_id,
            event_type="crm.opportunity.next_action.set",
            payload={
                "next_action": action.strip(),
                "due_at": due_at.isoformat(),
            },
        )

    def create_project_from_won_opportunity(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        opportunity_id: str,
        project_manager_user_id: str | None = None,
        contract_value_cents: int | None = None,
    ) -> Project:
        opportunity = self.spine.get(
            entity_id=opportunity_id,
            tenant_id=tenant_id,
            expected_type=Opportunity,
        )

        if opportunity.stage != OpportunityStage.WON:
            raise CRMTransitionError(
                "project can only be created from a won opportunity"
            )

        existing = [
            project
            for project in self.spine.list_type(
                tenant_id=tenant_id,
                entity_type=Project,
            )
            if project.opportunity_id == opportunity.entity_id
        ]

        if existing:
            raise CRMTransitionError(
                "opportunity already has a project"
            )

        project = Project(
            entity_id=new_id("project"),
            tenant_id=opportunity.tenant_id,
            business_unit_id=opportunity.business_unit_id,
            created_at=utc_now(),
            updated_at=utc_now(),
            name=opportunity.title,
            opportunity_id=opportunity.entity_id,
            contact_id=opportunity.contact_id,
            project_manager_user_id=project_manager_user_id,
            project_state=ProjectState.PRECONSTRUCTION,
            contract_value_cents=(
                contract_value_cents
                if contract_value_cents is not None
                else opportunity.estimated_value_cents
            ),
        )

        return self.spine.create(
            project,
            actor_id=actor_id,
            event_type="operations.project.created_from_opportunity",
            payload={
                "opportunity_id": opportunity.entity_id,
                "lead_id": opportunity.lead_id,
                "contact_id": opportunity.contact_id,
            },
        )
