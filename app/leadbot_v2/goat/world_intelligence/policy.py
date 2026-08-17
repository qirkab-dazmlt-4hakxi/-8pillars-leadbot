from __future__ import annotations

from .models import (
    RefreshCadence,
    RefreshPolicy,
    SignalDomain,
)


def default_refresh_policies(
):
    return {
        SignalDomain.WEATHER:
            RefreshPolicy(
                domain=(
                    SignalDomain.WEATHER
                ),
                cadence=(
                    RefreshCadence.HOURLY
                ),
                freshness_seconds=3600,
            ),

        SignalDomain.NEWS:
            RefreshPolicy(
                domain=(
                    SignalDomain.NEWS
                ),
                cadence=(
                    RefreshCadence.HOURLY
                ),
                freshness_seconds=7200,
            ),

        SignalDomain.SECURITIES:
            RefreshPolicy(
                domain=(
                    SignalDomain.SECURITIES
                ),
                cadence=(
                    RefreshCadence.HOURLY
                ),
                freshness_seconds=3600,
            ),

        SignalDomain.MATERIALS:
            RefreshPolicy(
                domain=(
                    SignalDomain.MATERIALS
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=86400,
            ),

        SignalDomain.ECONOMICS:
            RefreshPolicy(
                domain=(
                    SignalDomain.ECONOMICS
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=604800,
            ),

        SignalDomain.CONSTRUCTION:
            RefreshPolicy(
                domain=(
                    SignalDomain.CONSTRUCTION
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=604800,
            ),

        SignalDomain.BUILDING_CODE:
            RefreshPolicy(
                domain=(
                    SignalDomain.BUILDING_CODE
                ),
                cadence=(
                    RefreshCadence.WEEKLY
                ),
                freshness_seconds=2592000,
            ),

        SignalDomain.LEGAL_REGULATORY:
            RefreshPolicy(
                domain=(
                    SignalDomain.LEGAL_REGULATORY
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=604800,
            ),

        SignalDomain.SAFETY:
            RefreshPolicy(
                domain=(
                    SignalDomain.SAFETY
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=604800,
            ),

        SignalDomain.ENGINEERING:
            RefreshPolicy(
                domain=(
                    SignalDomain.ENGINEERING
                ),
                cadence=(
                    RefreshCadence.WEEKLY
                ),
                freshness_seconds=2592000,
            ),

        SignalDomain.TECHNOLOGY:
            RefreshPolicy(
                domain=(
                    SignalDomain.TECHNOLOGY
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=604800,
            ),

        SignalDomain.ENERGY:
            RefreshPolicy(
                domain=(
                    SignalDomain.ENERGY
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=86400,
            ),

        SignalDomain.OIL_GAS:
            RefreshPolicy(
                domain=(
                    SignalDomain.OIL_GAS
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=604800,
            ),

        SignalDomain.GEOLOGY:
            RefreshPolicy(
                domain=(
                    SignalDomain.GEOLOGY
                ),
                cadence=(
                    RefreshCadence.MONTHLY
                ),
                freshness_seconds=7776000,
            ),

        SignalDomain.WATER:
            RefreshPolicy(
                domain=(
                    SignalDomain.WATER
                ),
                cadence=(
                    RefreshCadence.WEEKLY
                ),
                freshness_seconds=2592000,
            ),

        SignalDomain.LAND:
            RefreshPolicy(
                domain=(
                    SignalDomain.LAND
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=604800,
            ),

        SignalDomain.AGRICULTURE:
            RefreshPolicy(
                domain=(
                    SignalDomain.AGRICULTURE
                ),
                cadence=(
                    RefreshCadence.WEEKLY
                ),
                freshness_seconds=1209600,
            ),

        SignalDomain.FINANCE:
            RefreshPolicy(
                domain=(
                    SignalDomain.FINANCE
                ),
                cadence=(
                    RefreshCadence.DAILY
                ),
                freshness_seconds=86400,
            ),
    }
