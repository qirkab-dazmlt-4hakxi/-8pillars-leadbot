from __future__ import annotations

import json

from datetime import date, datetime
from pathlib import Path
from typing import Any

from leadbot_v2.goat.preconstruction.pricing.engine import (
    PricingUnit,
)
from leadbot_v2.goat.preconstruction.regional_costs.engine import (
    CostRecord,
    LaborBasis,
    SourceKind,
    TexasMarket,
)


class CostDataIngestError(
    ValueError
):
    pass


def _date(
    value,
) -> date | None:
    if value in {
        None,
        "",
    }:
        return None

    return date.fromisoformat(
        str(value)
    )


def _datetime(
    value,
) -> datetime | None:
    if value in {
        None,
        "",
    }:
        return None

    return datetime.fromisoformat(
        str(value)
    )


def record_from_mapping(
    row: dict[str, Any],
) -> CostRecord:
    required = (
        "record_id",
        "source_kind",
        "source_name",
        "trade",
        "description",
        "unit",
        "market",
    )

    missing = [
        key
        for key in required
        if key not in row
    ]

    if missing:
        raise CostDataIngestError(
            "Missing required field(s): "
            + ", ".join(missing)
        )

    return CostRecord(
        record_id=str(
            row["record_id"]
        ),

        source_kind=SourceKind(
            row["source_kind"]
        ),

        source_name=str(
            row["source_name"]
        ),

        source_item_id=(
            str(
                row["source_item_id"]
            )
            if row.get(
                "source_item_id"
            )
            not in {
                None,
                "",
            }
            else None
        ),

        trade=str(
            row["trade"]
        ),

        description=str(
            row["description"]
        ),

        csi_division=(
            str(
                row["csi_division"]
            )
            if row.get(
                "csi_division"
            )
            not in {
                None,
                "",
            }
            else None
        ),

        cost_code=(
            str(
                row["cost_code"]
            )
            if row.get(
                "cost_code"
            )
            not in {
                None,
                "",
            }
            else None
        ),

        unit=PricingUnit(
            row["unit"]
        ),

        market=TexasMarket(
            row["market"]
        ),

        state=str(
            row.get(
                "state",
                "TX",
            )
        ),

        city=row.get(
            "city"
        ),

        county=row.get(
            "county"
        ),

        postal_code=row.get(
            "postal_code"
        ),

        material_cents_per_unit=int(
            row.get(
                "material_cents_per_unit",
                0,
            )
        ),

        labor_cents_per_unit=int(
            row.get(
                "labor_cents_per_unit",
                0,
            )
        ),

        equipment_cents_per_unit=int(
            row.get(
                "equipment_cents_per_unit",
                0,
            )
        ),

        subcontract_cents_per_unit=int(
            row.get(
                "subcontract_cents_per_unit",
                0,
            )
        ),

        other_cents_per_unit=int(
            row.get(
                "other_cents_per_unit",
                0,
            )
        ),

        wage_cents_per_hour=(
            int(
                row[
                    "wage_cents_per_hour"
                ]
            )
            if row.get(
                "wage_cents_per_hour"
            )
            not in {
                None,
                "",
            }
            else None
        ),

        fringe_cents_per_hour=(
            int(
                row[
                    "fringe_cents_per_hour"
                ]
            )
            if row.get(
                "fringe_cents_per_hour"
            )
            not in {
                None,
                "",
            }
            else None
        ),

        labor_basis=LaborBasis(
            row.get(
                "labor_basis",
                LaborBasis.UNKNOWN.value,
            )
        ),

        effective_date=_date(
            row.get(
                "effective_date"
            )
        ),

        expires_date=_date(
            row.get(
                "expires_date"
            )
        ),

        release_quarter=row.get(
            "release_quarter"
        ),

        verified_at=_datetime(
            row.get(
                "verified_at"
            )
        ),

        confidence=float(
            row.get(
                "confidence",
                1.0,
            )
        ),

        project_id=row.get(
            "project_id"
        ),

        vendor_name=row.get(
            "vendor_name"
        ),

        notes=str(
            row.get(
                "notes",
                "",
            )
        ),
    )


def load_json_records(
    path: str | Path,
) -> tuple[
    CostRecord,
    ...
]:
    file_path = Path(
        path
    )

    payload = json.loads(
        file_path.read_text()
    )

    if not isinstance(
        payload,
        list,
    ):
        raise CostDataIngestError(
            "Regional cost JSON must "
            "contain a list of records"
        )

    return tuple(
        record_from_mapping(
            row
        )
        for row in payload
    )
