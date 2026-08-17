from __future__ import annotations


FINANCIAL_DOMAIN = (
    "financial_health"
)


def install_financial_experts(
    kernel,
) -> None:
    kernel.register_expert(
        expert_id=(
            "goat.finance.liquidity"
        ),
        domain=(
            FINANCIAL_DOMAIN
        ),
        handler=(
            _liquidity_expert
        ),
        weight=1.20,
    )

    kernel.register_expert(
        expert_id=(
            "goat.finance.margin"
        ),
        domain=(
            FINANCIAL_DOMAIN
        ),
        handler=(
            _margin_expert
        ),
        weight=1.20,
    )

    kernel.register_expert(
        expert_id=(
            "goat.finance.controls"
        ),
        domain=(
            FINANCIAL_DOMAIN
        ),
        handler=(
            _controls_expert
        ),
        weight=1.00,
    )


def _liquidity_expert(
    context,
):
    runway = context.get(
        "runway_days"
    )

    if (
        runway is not None
        and runway < 30
    ):
        return {
            "answer":
                "corrective_action",
            "confidence":
                0.96,
            "risk":
                "high",
            "reasoning_summary":
                "cash runway below 30 days",
        }

    if (
        runway is not None
        and runway < 60
    ):
        return {
            "answer":
                "corrective_action",
            "confidence":
                0.86,
            "risk":
                "moderate",
            "reasoning_summary":
                "cash runway below preferred reserve",
        }

    return {
        "answer":
            "continue",
        "confidence":
            0.82,
        "risk":
            "low",
        "reasoning_summary":
            "liquidity condition acceptable",
    }


def _margin_expert(
    context,
):
    margin = float(
        context.get(
            "projected_margin",
            0.0,
        )
    )

    erosion = float(
        context.get(
            "margin_erosion",
            0.0,
        )
    )

    if (
        margin < 0.0
        or erosion >= 0.10
    ):
        return {
            "answer":
                "corrective_action",
            "confidence":
                0.97,
            "risk":
                "high",
            "reasoning_summary":
                "project margin materially impaired",
        }

    if erosion >= 0.05:
        return {
            "answer":
                "corrective_action",
            "confidence":
                0.88,
            "risk":
                "moderate",
            "reasoning_summary":
                "margin erosion exceeds control threshold",
        }

    return {
        "answer":
            "continue",
        "confidence":
            0.84,
        "risk":
            "low",
        "reasoning_summary":
            "project margin remains within control band",
    }


def _controls_expert(
    context,
):
    unreconciled = int(
        context.get(
            "unreconciled_transactions",
            0,
        )
    )

    reviews = int(
        context.get(
            "review_queue",
            0,
        )
    )

    if (
        unreconciled >= 10
        or reviews >= 10
    ):
        return {
            "answer":
                "corrective_action",
            "confidence":
                0.90,
            "risk":
                "moderate",
            "reasoning_summary":
                "financial controls backlog exceeds threshold",
        }

    return {
        "answer":
            "continue",
        "confidence":
            0.80,
        "risk":
            "low",
        "reasoning_summary":
            "financial controls backlog acceptable",
    }
