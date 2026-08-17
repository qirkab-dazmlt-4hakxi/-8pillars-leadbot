from __future__ import annotations

from collections import defaultdict

from .canonical import (
    stable_hash,
)

from .models import (
    SignalDomain,
    WorldSignal,
)


class WorldSignalEngine:
    def normalize(
        self,
        *,
        domain,
        name,
        timestamp,
        value,
        unit,
        geography,
        source_id,
        confidence,
        metadata=None,
    ):
        confidence = max(
            0.0,
            min(
                1.0,
                float(
                    confidence
                ),
            ),
        )

        signal_id = stable_hash(
            {
                "domain":
                    domain,

                "name":
                    name,

                "timestamp":
                    timestamp,

                "value":
                    float(
                        value
                    ),

                "unit":
                    unit,

                "geography":
                    geography,

                "source_id":
                    source_id,
            }
        )[:32]

        return WorldSignal(
            signal_id=(
                signal_id
            ),
            domain=domain,
            name=name,
            timestamp=timestamp,
            value=float(
                value
            ),
            unit=unit,
            geography=geography,
            source_id=source_id,
            confidence=confidence,
            metadata=dict(
                metadata or {}
            ),
        )

    def summarize(
        self,
        signals,
    ):
        groups = defaultdict(
            list
        )

        for signal in signals:
            groups[
                (
                    signal.domain,
                    signal.name,
                    signal.geography,
                )
            ].append(
                signal
            )

        result = []

        for key, rows in groups.items():
            denominator = sum(
                max(
                    0.000001,
                    row.confidence
                )
                for row
                in rows
            )

            weighted = sum(
                row.value
                * max(
                    0.000001,
                    row.confidence
                )
                for row
                in rows
            ) / denominator

            result.append(
                {
                    "domain":
                        key[
                            0
                        ],

                    "name":
                        key[
                            1
                        ],

                    "geography":
                        key[
                            2
                        ],

                    "weighted_value":
                        weighted,

                    "source_count":
                        len(
                            {
                                row.source_id
                                for row
                                in rows
                            }
                        ),

                    "average_confidence":
                        sum(
                            row.confidence
                            for row
                            in rows
                        )
                        / len(
                            rows
                        ),
                }
            )

        return tuple(
            sorted(
                result,
                key=lambda item: (
                    item[
                        "domain"
                    ].value,
                    item[
                        "name"
                    ],
                    str(
                        item[
                            "geography"
                        ]
                    ),
                ),
            )
        )


class PublicMarketInformationPolicy:
    """
    Market intelligence may ingest and reason over lawful public information.

    It must not characterize private, stolen, embargoed, misappropriated, or
    other non-public material information as an investment signal.
    """

    PRIVATE_MARKERS = {
        "private_tip",
        "inside_information",
        "material_nonpublic",
        "embargoed_private",
        "stolen_information",
    }

    def validate(
        self,
        metadata,
    ):
        tags = {
            str(
                tag
            ).strip().lower()
            for tag
            in metadata.get(
                "information_tags",
                ()
            )
        }

        forbidden = (
            tags
            & self.PRIVATE_MARKERS
        )

        if forbidden:
            raise ValueError(
                "non-public market information "
                "is prohibited"
            )

        return True
