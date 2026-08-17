from __future__ import annotations

import math


class AttributionEngine:
    def attribute(
        self,
        touches,
        *,
        model: str = "linear",
    ):
        touches = tuple(
            sorted(
                touches,
                key=lambda touch:
                    touch.timestamp,
            )
        )

        if not touches:
            return {}

        keys = [
            (
                touch.campaign_id
                or touch.channel.value
            )
            for touch
            in touches
        ]

        credits = {
            key:
                0.0
            for key
            in keys
        }

        if model == "first_touch":
            credits[
                keys[
                    0
                ]
            ] += 1.0

        elif model == "last_touch":
            credits[
                keys[
                    -1
                ]
            ] += 1.0

        elif model == "linear":
            weight = (
                1.0
                / len(
                    touches
                )
            )

            for key in keys:
                credits[
                    key
                ] += weight

        elif model == "time_decay":
            raw = []

            latest = (
                touches[
                    -1
                ].timestamp
            )

            for touch in touches:
                days = max(
                    0.0,
                    (
                        latest
                        - touch.timestamp
                    ).total_seconds()
                    / 86400.0,
                )

                raw.append(
                    math.pow(
                        0.5,
                        days
                        / 7.0,
                    )
                )

            denominator = sum(
                raw
            )

            for key, weight in zip(
                keys,
                raw,
            ):
                credits[
                    key
                ] += (
                    weight
                    / denominator
                )

        else:
            raise ValueError(
                f"unknown attribution model: "
                f"{model}"
            )

        total = sum(
            credits.values()
        )

        if total:
            credits = {
                key:
                    value
                    / total
                for key, value
                in credits.items()
            }

        return credits
