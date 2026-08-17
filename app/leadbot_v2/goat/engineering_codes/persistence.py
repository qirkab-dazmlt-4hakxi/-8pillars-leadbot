from __future__ import annotations


JURISDICTION_ENTITY = (
    "goat.engineering.jurisdiction"
)

CODE_ADOPTION_ENTITY = (
    "goat.engineering.code_adoption"
)

CODE_AMENDMENT_ENTITY = (
    "goat.engineering.code_amendment"
)

CALCULATION_ENTITY = (
    "goat.engineering.calculation"
)

COMPLIANCE_ENTITY = (
    "goat.engineering.compliance"
)

WATER_ASSESSMENT_ENTITY = (
    "goat.engineering.water_assessment"
)


class EngineeringCodeRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id,
        actor_id=(
            "goat-engineering-codes"
        ),
    ) -> None:
        self.store = store
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def _upsert(
        self,
        *,
        entity_type,
        entity_id,
        payload,
    ):
        current = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        expected = (
            None
            if current is None
            else int(
                current.version
            )
        )

        return self.store.put_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            actor_id=self.actor_id,
            expected_version=expected,
        )

    def save_jurisdiction(
        self,
        jurisdiction,
    ):
        return self._upsert(
            entity_type=(
                JURISDICTION_ENTITY
            ),
            entity_id=(
                jurisdiction
                .jurisdiction_id
            ),
            payload={
                "name":
                    jurisdiction.name,

                "jurisdiction_type":
                    jurisdiction
                    .jurisdiction_type
                    .value,

                "state_code":
                    jurisdiction.state_code,

                "parent_id":
                    jurisdiction.parent_id,

                "fips_code":
                    jurisdiction.fips_code,

                "metadata":
                    jurisdiction.metadata,
            },
        )

    def save_adoption(
        self,
        adoption,
    ):
        return self._upsert(
            entity_type=(
                CODE_ADOPTION_ENTITY
            ),
            entity_id=(
                adoption.adoption_id
            ),
            payload={
                "jurisdiction_id":
                    adoption
                    .jurisdiction_id,

                "discipline":
                    adoption
                    .discipline
                    .value,

                "code_family":
                    adoption.code_family,

                "edition":
                    adoption.edition,

                "effective_from":
                    adoption
                    .effective_from
                    .isoformat(),

                "effective_until":
                    (
                        adoption
                        .effective_until
                        .isoformat()
                        if adoption
                        .effective_until
                        else None
                    ),

                "authority":
                    adoption
                    .authority
                    .value,

                "status":
                    adoption.status.value,

                "source_fact_id":
                    adoption
                    .source_fact_id,

                "amendment_ids":
                    list(
                        adoption
                        .amendment_ids
                    ),
            },
        )

    def save_amendment(
        self,
        amendment,
    ):
        return self._upsert(
            entity_type=(
                CODE_AMENDMENT_ENTITY
            ),
            entity_id=(
                amendment.amendment_id
            ),
            payload={
                "jurisdiction_id":
                    amendment
                    .jurisdiction_id,

                "discipline":
                    amendment
                    .discipline
                    .value,

                "code_family":
                    amendment.code_family,

                "section":
                    amendment.section,

                "operation":
                    amendment.operation,

                "payload":
                    amendment.payload,

                "effective_from":
                    amendment
                    .effective_from
                    .isoformat(),

                "effective_until":
                    (
                        amendment
                        .effective_until
                        .isoformat()
                        if amendment
                        .effective_until
                        else None
                    ),

                "source_fact_id":
                    amendment
                    .source_fact_id,

                "authority":
                    amendment
                    .authority
                    .value,
            },
        )

    def save_calculation(
        self,
        trace,
    ):
        return self._upsert(
            entity_type=(
                CALCULATION_ENTITY
            ),
            entity_id=(
                trace.calculation_id
            ),
            payload={
                "engine":
                    trace.engine,

                "engine_version":
                    trace.engine_version,

                "inputs":
                    trace.inputs,

                "outputs":
                    trace.outputs,

                "source_fact_ids":
                    list(
                        trace.source_fact_ids
                    ),

                "executed_at":
                    trace.executed_at
                    .isoformat(),

                "previous_hash":
                    trace.previous_hash,

                "content_hash":
                    trace.content_hash,

                "chain_hash":
                    trace.chain_hash,
            },
        )

    def save_water_assessment(
        self,
        *,
        assessment_id,
        assessment,
    ):
        return self._upsert(
            entity_type=(
                WATER_ASSESSMENT_ENTITY
            ),
            entity_id=(
                assessment_id
            ),
            payload={
                "governing_water_elevation_ft":
                    assessment
                    .governing_water_elevation_ft,

                "hydrostatic_head_ft":
                    assessment
                    .hydrostatic_head_ft,

                "base_pressure_psi":
                    assessment
                    .base_pressure_psi,

                "estimated_uplift_kips":
                    assessment
                    .estimated_uplift_kips,

                "intrusion_probability_index":
                    assessment
                    .intrusion_probability_index,

                "risk_level":
                    assessment
                    .risk_level
                    .value,

                "notes":
                    list(
                        assessment.notes
                    ),

                "professional_review_required":
                    assessment
                    .professional_review_required,
            },
        )
