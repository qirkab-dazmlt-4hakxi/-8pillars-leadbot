from __future__ import annotations

from collections import defaultdict


class CompetitorSignalAnalyzer:
    """
    Analyzes public business-level market signals.

    This intentionally avoids personal dossiers or retaliatory targeting.
    """

    def summarize(
        self,
        signals,
    ):
        groups = defaultdict(
            list
        )

        for signal in signals:
            groups[
                signal.competitor_id
            ].append(
                signal
            )

        summaries = []

        for (
            competitor_id,
            rows,
        ) in groups.items():
            strength = (
                sum(
                    max(
                        0.0,
                        min(
                            1.0,
                            row.strength,
                        ),
                    )
                    for row
                    in rows
                )
                / len(
                    rows
                )
            )

            signal_types = tuple(
                sorted(
                    {
                        row.signal_type
                        for row
                        in rows
                    }
                )
            )

            summaries.append(
                {
                    "competitor_id":
                        competitor_id,

                    "business_name":
                        rows[
                            0
                        ].business_name,

                    "signal_count":
                        len(
                            rows
                        ),

                    "average_strength":
                        strength,

                    "signal_types":
                        signal_types,
                }
            )

        summaries.sort(
            key=lambda row: (
                row[
                    "average_strength"
                ],
                row[
                    "signal_count"
                ],
                row[
                    "competitor_id"
                ],
            ),
            reverse=True,
        )

        return tuple(
            summaries
        )
