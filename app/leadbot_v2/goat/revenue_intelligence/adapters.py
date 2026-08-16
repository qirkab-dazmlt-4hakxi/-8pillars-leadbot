from __future__ import annotations

import inspect

from typing import Any

from .models import (
    ActionPlan,
    CanonicalLead,
)


class BusinessContractError(
    RuntimeError
):
    pass


ALIASES = {
    "name": (
        "name",
        "full_name",
        "contact_name",
    ),
    "phone": (
        "phone",
        "mobile",
        "phone_number",
    ),
    "email": (
        "email",
        "email_address",
    ),
    "company": (
        "company",
        "company_name",
    ),
    "contact_id": (
        "contact_id",
        "person_id",
    ),
    "lead_id": (
        "lead_id",
        "id",
    ),
    "source": (
        "source",
        "source_type",
        "lead_source",
    ),
    "notes": (
        "notes",
        "description",
        "raw_text",
    ),
    "next_action": (
        "next_action",
        "action",
        "action_type",
    ),
}


def _lookup(
    parameter: str,
    payload: dict[str, Any],
):
    if parameter in payload:
        return (
            True,
            payload[
                parameter
            ],
        )

    for canonical, aliases in (
        ALIASES.items()
    ):
        if parameter not in aliases:
            continue

        if canonical in payload:
            return (
                True,
                payload[
                    canonical
                ],
            )

    return (
        False,
        None,
    )


def invoke_adaptive(
    target,
    method_name: str,
    payload: dict[str, Any],
):
    method = getattr(
        target,
        method_name,
        None,
    )

    if method is None:
        raise BusinessContractError(
            f"missing method: "
            f"{method_name}"
        )

    signature = inspect.signature(
        method
    )

    kwargs = {}
    missing = []

    for name, parameter in (
        signature.parameters.items()
    ):
        if name == "self":
            continue

        if parameter.kind in {
            inspect.Parameter
            .VAR_POSITIONAL,
            inspect.Parameter
            .VAR_KEYWORD,
        }:
            continue

        found, value = _lookup(
            name,
            payload,
        )

        if found:
            kwargs[
                name
            ] = value

        elif (
            parameter.default
            is inspect.Parameter.empty
        ):
            missing.append(
                name
            )

    if missing:
        raise BusinessContractError(
            f"{method_name} has unsupported "
            f"required parameters: "
            f"{', '.join(missing)}"
        )

    return method(
        **kwargs
    )


def extract_id(
    value,
    *names,
):
    names = names or (
        "id",
        "contact_id",
        "lead_id",
        "opportunity_id",
    )

    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        return value

    if isinstance(
        value,
        dict,
    ):
        for name in names:
            if value.get(
                name
            ):
                return str(
                    value[
                        name
                    ]
                )

    for name in names:
        result = getattr(
            value,
            name,
            None,
        )

        if result:
            return str(
                result
            )

    return None


class GoatCRMAdapter:
    def __init__(
        self,
        crm,
    ) -> None:
        self.crm = crm

    def sync(
        self,
        lead: CanonicalLead,
        action: ActionPlan,
    ) -> dict[str, Any]:
        base = {
            "name":
                lead.name,
            "phone":
                lead.phone,
            "email":
                lead.email,
            "company":
                lead.company,
            "source":
                lead.source_type.value,
            "notes":
                lead.raw_text,
        }

        contact = invoke_adaptive(
            self.crm,
            "create_contact",
            base,
        )

        contact_id = extract_id(
            contact,
            "contact_id",
            "id",
        )

        crm_lead = invoke_adaptive(
            self.crm,
            "create_lead",
            {
                **base,
                "contact_id":
                    contact_id,
            },
        )

        lead_id = extract_id(
            crm_lead,
            "lead_id",
            "id",
        )

        if lead_id:
            invoke_adaptive(
                self.crm,
                "set_lead_next_action",
                {
                    "lead_id":
                        lead_id,
                    "next_action":
                        action.kind.value,
                },
            )

        return {
            "contact":
                contact,
            "contact_id":
                contact_id,
            "crm_lead":
                crm_lead,
            "crm_lead_id":
                lead_id,
        }
