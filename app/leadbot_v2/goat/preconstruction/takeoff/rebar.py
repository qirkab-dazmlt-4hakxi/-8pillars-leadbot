from __future__ import annotations

import re
from dataclasses import dataclass

from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)


BAR_WEIGHT_LB_PER_FT = {
    3: 0.376,
    4: 0.668,
    5: 1.043,
    6: 1.502,
    7: 2.044,
    8: 2.670,
    9: 3.400,
    10: 4.303,
    11: 5.313,
    14: 7.650,
    18: 13.600,
}


REBAR_PATTERN = re.compile(
    r"#(?P<size>\d+)\s*"
    r"@\s*"
    r"(?P<spacing>\d+(?:\.\d+)?)\s*"
    r"[\"”]?"
    r"(?:\s*O\.?\s*C\.?)?",
    re.I,
)


@dataclass(frozen=True)
class RebarSpec:
    bar_size: int
    spacing_inches: float
    directions: int
    layers: int
    raw: str
    confidence: float

    def __post_init__(self) -> None:
        if self.bar_size not in (
            BAR_WEIGHT_LB_PER_FT
        ):
            raise ValueError(
                f"unsupported bar size "
                f"#{self.bar_size}"
            )

        if self.spacing_inches <= 0:
            raise ValueError(
                "rebar spacing must be positive"
            )

        if self.directions < 1:
            raise ValueError(
                "directions must be >= 1"
            )

        if self.layers < 1:
            raise ValueError(
                "layers must be >= 1"
            )


@dataclass(frozen=True)
class RebarTakeoff:
    specification: RebarSpec
    total_linear_feet: float
    total_weight_lb: float
    lap_waste_factor: float
    formula: str
    provenance: GeometryProvenance
    confidence: float


class RebarIntelligence:

    @staticmethod
    def parse(
        text: str,
    ) -> RebarSpec | None:
        match = REBAR_PATTERN.search(
            text
        )

        if not match:
            return None

        upper = text.upper()

        directions = 1

        if (
            " EACH WAY" in f" {upper}"
            or re.search(
                r"\bE\.?W\.?\b",
                upper,
            )
        ):
            directions = 2

        layers = 1

        if (
            re.search(
                r"\bT\s*&\s*B\b",
                upper,
            )
            or "TOP AND BOTTOM"
            in upper
            or "TOP & BOTTOM"
            in upper
        ):
            layers = 2

        mats = re.search(
            r"\b(?P<count>\d+)\s+MATS?\b",
            upper,
        )

        if mats:
            layers = max(
                layers,
                int(
                    mats.group("count")
                ),
            )

        return RebarSpec(
            bar_size=int(
                match.group("size")
            ),
            spacing_inches=float(
                match.group("spacing")
            ),
            directions=directions,
            layers=layers,
            raw=text.strip(),
            confidence=0.96,
        )

    @staticmethod
    def slab_grid_takeoff(
        *,
        spec: RebarSpec,
        area_sqft: float,
        provenance: GeometryProvenance,
        lap_waste_percent: float = 10.0,
    ) -> RebarTakeoff:
        if area_sqft <= 0:
            raise ValueError(
                "area must be positive"
            )

        if lap_waste_percent < 0:
            raise ValueError(
                "lap/waste percent cannot be negative"
            )

        spacing_ft = (
            spec.spacing_inches
            / 12.0
        )

        theoretical_lf = (
            area_sqft
            / spacing_ft
            * spec.directions
            * spec.layers
        )

        factor = (
            1.0
            + lap_waste_percent
            / 100.0
        )

        total_lf = (
            theoretical_lf
            * factor
        )

        weight = (
            total_lf
            * BAR_WEIGHT_LB_PER_FT[
                spec.bar_size
            ]
        )

        confidence = min(
            spec.confidence,
            provenance.confidence,
        )

        return RebarTakeoff(
            specification=spec,
            total_linear_feet=total_lf,
            total_weight_lb=weight,
            lap_waste_factor=factor,
            formula=(
                f"{area_sqft:.3f} SF "
                f"/ {spacing_ft:.3f} FT spacing "
                f"× {spec.directions} direction(s) "
                f"× {spec.layers} layer(s) "
                f"× {factor:.3f} lap/waste"
            ),
            provenance=provenance,
            confidence=confidence,
        )
