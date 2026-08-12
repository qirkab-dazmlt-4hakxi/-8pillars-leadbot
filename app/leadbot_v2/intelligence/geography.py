from __future__ import annotations

from dataclasses import dataclass


TARGET_CITIES = {
    "frisco",
    "mckinney",
    "prosper",
    "celina",
    "little elm",
    "aubrey",
    "denton",
}

DFW_SIGNALS = {
    "dfw",
    "north texas",
    "collin county",
    "denton county",
}


MARKET_ALIASES = {
    "windsong ranch": "Prosper",
    "light farms": "Celina",
    "mustang lakes": "Celina",
    "paloma creek": "Little Elm",
    "savannah": "Aubrey",
    "union park": "Little Elm",
    "pga frisco": "Frisco",
    "star trail": "Prosper",
    "fields frisco": "Frisco",
    "trinity falls": "McKinney",
}

COUNTY_ALIASES = {
    "collin county": "Collin County",
    "denton county": "Denton County",
}

OUT_OF_AREA = {
    "california",
    "los angeles",
    "san diego",
    "san francisco",
    "oklahoma",
    "oklahoma city",
    "phoenix",
    "arizona",
    "chicago",
    "new york",
    "florida",
    "seattle",
}


@dataclass
class GeoDecision:
    confidence: float
    matched_city: str | None
    in_market: bool
    conflict: bool
    reason: str


class GeographicIntelligence:
    def analyze(
        self,
        *,
        target_city: str | None,
        title: str,
        text: str,
        url: str,
    ) -> GeoDecision:
        haystack = f"{title}\n{text}\n{url}".lower()

        target = (target_city or "").lower().strip()

        out_hits = [
            place for place in OUT_OF_AREA
            if place in haystack
        ]

        target_hit = bool(target and target in haystack)

        if target_hit and out_hits:
            return GeoDecision(
                confidence=0.10,
                matched_city=target_city,
                in_market=False,
                conflict=True,
                reason=(
                    "conflicting geography: target city plus "
                    + ", ".join(out_hits[:3])
                ),
            )

        if target_hit:
            return GeoDecision(
                confidence=0.98,
                matched_city=target_city,
                in_market=True,
                conflict=False,
                reason="target city explicitly matched",
            )

        for alias, city_name in MARKET_ALIASES.items():
            if alias in haystack:
                return GeoDecision(
                    confidence=0.93,
                    matched_city=city_name,
                    in_market=True,
                    conflict=False,
                    reason=f"market subdivision/alias matched: {alias}",
                )

        for county in COUNTY_ALIASES:
            if county in haystack:
                return GeoDecision(
                    confidence=0.86,
                    matched_city=None,
                    in_market=True,
                    conflict=False,
                    reason=f"target county matched: {county}",
                )

        for city in TARGET_CITIES:
            if city in haystack:
                return GeoDecision(
                    confidence=0.90,
                    matched_city=city.title(),
                    in_market=True,
                    conflict=False,
                    reason="North Texas target city matched",
                )

        if any(signal in haystack for signal in DFW_SIGNALS):
            return GeoDecision(
                confidence=0.78,
                matched_city=None,
                in_market=True,
                conflict=False,
                reason="DFW/North Texas regional signal matched",
            )

        if out_hits:
            return GeoDecision(
                confidence=0.05,
                matched_city=None,
                in_market=False,
                conflict=True,
                reason=(
                    "out-of-market location detected: "
                    + ", ".join(out_hits[:3])
                ),
            )

        return GeoDecision(
            confidence=0.30,
            matched_city=None,
            in_market=False,
            conflict=False,
            reason="location not proven",
        )
