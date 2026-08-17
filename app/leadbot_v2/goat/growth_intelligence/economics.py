from __future__ import annotations

from decimal import (
    Decimal,
    ROUND_HALF_UP,
)

from .models import (
    CampaignEconomics,
)


CENT = Decimal(
    "0.01"
)


def money(
    value,
):
    return Decimal(
        str(
            value
        )
    ).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


class MarketingEconomics:
    def calculate(
        self,
        *,
        campaign_id: str,
        spend,
        revenue,
        contribution_profit,
        leads: int,
        qualified_leads: int,
        customers: int,
    ) -> CampaignEconomics:
        spend = money(
            spend
        )

        revenue = money(
            revenue
        )

        contribution_profit = money(
            contribution_profit
        )

        return CampaignEconomics(
            campaign_id=(
                campaign_id
            ),
            spend=spend,
            revenue=revenue,
            contribution_profit=(
                contribution_profit
            ),
            leads=int(
                leads
            ),
            qualified_leads=int(
                qualified_leads
            ),
            customers=int(
                customers
            ),
            cac=(
                money(
                    spend
                    / customers
                )
                if customers > 0
                else None
            ),
            cpl=(
                money(
                    spend
                    / leads
                )
                if leads > 0
                else None
            ),
            qualified_cpl=(
                money(
                    spend
                    / qualified_leads
                )
                if qualified_leads > 0
                else None
            ),
            roas=(
                float(
                    revenue
                    / spend
                )
                if spend > 0
                else None
            ),
            mer=(
                float(
                    revenue
                    / spend
                )
                if spend > 0
                else None
            ),
            contribution_roas=(
                float(
                    contribution_profit
                    / spend
                )
                if spend > 0
                else None
            ),
        )
