from __future__ import annotations

from .canonical import (
    stable_hash,
)

from .models import (
    CreativeKind,
    ProductionPlan,
    ProductionShot,
)


class CreativeAssetValidator:
    def validate(
        self,
        asset,
    ):
        findings = []

        if not asset.rights_confirmed:
            findings.append(
                "usage rights not confirmed"
            )

        if (
            asset.kind
            in {
                CreativeKind.VIDEO,
                CreativeKind.DRONE,
            }
            and (
                asset.duration_seconds
                is None
                or asset.duration_seconds
                <= 0
            )
        ):
            findings.append(
                "video duration missing"
            )

        if (
            asset.kind
            is CreativeKind.VIDEO
            and asset.has_audio
            and not asset.has_captions
        ):
            findings.append(
                "spoken video should include captions"
            )

        if (
            asset.width is not None
            and asset.width <= 0
        ):
            findings.append(
                "invalid width"
            )

        if (
            asset.height is not None
            and asset.height <= 0
        ):
            findings.append(
                "invalid height"
            )

        return tuple(
            findings
        )


class CreativeStudioPlanner:
    def create_plan(
        self,
        *,
        campaign_name: str,
        objective: str,
        include_drone: bool = True,
    ) -> ProductionPlan:
        shots = [
            ProductionShot(
                shot_id="hero-wide",
                kind=(
                    CreativeKind.VIDEO
                ),
                description=(
                    "Wide establishing shot of completed work"
                ),
                duration_seconds=4.0,
                required=True,
            ),

            ProductionShot(
                shot_id="detail-quality",
                kind=(
                    CreativeKind.VIDEO
                ),
                description=(
                    "Close detail showing workmanship and finish"
                ),
                duration_seconds=4.0,
                required=True,
            ),

            ProductionShot(
                shot_id="crew-process",
                kind=(
                    CreativeKind.VIDEO
                ),
                description=(
                    "Safe work-process footage without exposing "
                    "private customer information"
                ),
                duration_seconds=5.0,
                required=True,
            ),

            ProductionShot(
                shot_id="hero-photo",
                kind=(
                    CreativeKind.PHOTO
                ),
                description=(
                    "High-resolution finished-project hero image"
                ),
                duration_seconds=None,
                required=True,
            ),
        ]

        if include_drone:
            shots.append(
                ProductionShot(
                    shot_id="aerial-context",
                    kind=(
                        CreativeKind.DRONE
                    ),
                    description=(
                        "Authorized aerial context shot where flight "
                        "operations and location permit"
                    ),
                    duration_seconds=5.0,
                    required=False,
                )
            )

        deliverables = (
            "16:9 master",
            "9:16 vertical cut",
            "1:1 social cut",
            "15-second cutdown",
            "30-second commercial cut",
            "captioned version",
            "thumbnail set",
            "high-resolution still set",
        )

        plan_id = stable_hash(
            {
                "campaign_name":
                    campaign_name,
                "objective":
                    objective,
                "include_drone":
                    include_drone,
                "deliverables":
                    deliverables,
            }
        )[:24]

        return ProductionPlan(
            plan_id=plan_id,
            campaign_name=(
                campaign_name
            ),
            objective=objective,
            shots=tuple(
                shots
            ),
            deliverables=(
                deliverables
            ),
            required_claim_evidence=(
                "project authorization",
                "customer/media release where required",
                "substantiation for performance claims",
                "usage-rights confirmation",
            ),
        )
