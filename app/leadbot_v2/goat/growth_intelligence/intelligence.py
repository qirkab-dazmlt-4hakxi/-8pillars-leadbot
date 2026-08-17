from __future__ import annotations


GROWTH_DOMAIN = (
    "growth_strategy"
)


def install_growth_experts(
    kernel,
) -> None:
    kernel.register_expert(
        expert_id=(
            "goat.growth.economics"
        ),
        domain=(
            GROWTH_DOMAIN
        ),
        weight=1.20,
        handler=(
            _economics_expert
        ),
    )

    kernel.register_expert(
        expert_id=(
            "goat.growth.search"
        ),
        domain=(
            GROWTH_DOMAIN
        ),
        weight=1.10,
        handler=(
            _search_expert
        ),
    )

    kernel.register_expert(
        expert_id=(
            "goat.growth.brand"
        ),
        domain=(
            GROWTH_DOMAIN
        ),
        weight=1.20,
        handler=(
            _brand_expert
        ),
    )


def _economics_expert(
    context,
):
    contribution_roas = (
        context.get(
            "contribution_roas"
        )
    )

    if (
        contribution_roas
        is not None
        and contribution_roas < 1.0
    ):
        return {
            "answer":
                "corrective_action",

            "confidence":
                0.95,

            "risk":
                "high",

            "reasoning_summary":
                (
                    "campaign contribution return "
                    "is below break-even"
                ),
        }

    return {
        "answer":
            "continue",

        "confidence":
            0.82,

        "risk":
            "low",

        "reasoning_summary":
            "growth economics acceptable",
    }


def _search_expert(
    context,
):
    seo_score = float(
        context.get(
            "seo_score",
            100.0,
        )
    )

    if seo_score < 60:
        return {
            "answer":
                "corrective_action",

            "confidence":
                0.90,

            "risk":
                "moderate",

            "reasoning_summary":
                "technical search visibility is impaired",
        }

    return {
        "answer":
            "continue",

        "confidence":
            0.80,

        "risk":
            "low",

        "reasoning_summary":
            "search health acceptable",
    }


def _brand_expert(
    context,
):
    brand_risk = str(
        context.get(
            "brand_risk",
            "low",
        )
    ).lower()

    if brand_risk in {
        "high",
        "critical",
    }:
        return {
            "answer":
                "corrective_action",

            "confidence":
                0.96,

            "risk":
                "high",

            "reasoning_summary":
                "brand/reputation risk requires intervention",
        }

    return {
        "answer":
            "continue",

        "confidence":
            0.82,

        "risk":
            "low",

        "reasoning_summary":
            "brand risk inside control band",
    }
