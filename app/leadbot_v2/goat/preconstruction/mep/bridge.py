from __future__ import annotations


class MEPEstimateBridge:
    """
    Common bridge for electrical/plumbing priced scopes.

    The estimating workflow remains the authoritative
    estimate lifecycle and preserves source provenance.
    """

    @staticmethod
    def add_scope(
        *,
        workflow,
        estimate_id: str,
        actor_id: str,
        priced_scope,
        cost_code: str,
    ):
        refs = (
            priced_scope
            .provenance
            .source_ref,
            *priced_scope
            .provenance
            .geometry_ids,
            *priced_scope
            .provenance
            .text_refs,
        )

        return workflow.add_manual_line(
            estimate_id=estimate_id,
            actor_id=actor_id,
            description=(
                priced_scope.description
            ),
            cost_code=cost_code,
            quantity=1.0,
            unit="LS",
            direct_cost_cents=(
                priced_scope
                .direct_cost_cents
            ),
            bid_price_cents=(
                priced_scope
                .bid_price_cents
            ),
            source_refs=tuple(
                dict.fromkeys(
                    refs
                )
            ),
            confidence=(
                priced_scope.confidence
            ),
            requires_review=(
                priced_scope
                .requires_review
            ),
        )
