from __future__ import annotations

import math

from .geometry import (
    expand,
    validate_aabb,
)

from .models import (
    SpatialIndexError,
)


class SpatialHash3D:
    """
    Uniform 3D broad-phase index.

    Intended to reduce clash candidate generation from naive
    global pairwise comparison for spatially distributed BIM models.
    """

    def __init__(
        self,
        *,
        cell_size_ft=10.0,
    ):
        if cell_size_ft <= 0:
            raise SpatialIndexError(
                "cell size must be positive"
            )

        self.cell_size_ft = float(
            cell_size_ft
        )

        self._cells = {}
        self._element_cells = {}
        self._elements = {}

        self.max_clearance_ft = 0.0

    def _coordinate(self, value):
        return math.floor(
            float(value)
            / self.cell_size_ft
        )

    def cells_for_bounds(
        self,
        bounds,
    ):
        validate_aabb(bounds)

        xs = range(
            self._coordinate(
                bounds.minimum.x
            ),
            self._coordinate(
                bounds.maximum.x
            ) + 1,
        )

        ys = range(
            self._coordinate(
                bounds.minimum.y
            ),
            self._coordinate(
                bounds.maximum.y
            ) + 1,
        )

        zs = range(
            self._coordinate(
                bounds.minimum.z
            ),
            self._coordinate(
                bounds.maximum.z
            ) + 1,
        )

        return tuple(
            (x, y, z)
            for x in xs
            for y in ys
            for z in zs
        )

    def insert(
        self,
        element,
    ):
        if (
            element.element_id
            in self._elements
        ):
            raise SpatialIndexError(
                "duplicate indexed element"
            )

        cells = self.cells_for_bounds(
            element.bounds
        )

        self._elements[
            element.element_id
        ] = element

        self._element_cells[
            element.element_id
        ] = cells

        for cell in cells:
            self._cells.setdefault(
                cell,
                set(),
            ).add(
                element.element_id
            )

        self.max_clearance_ft = max(
            self.max_clearance_ft,
            max(
                0.0,
                element.clearance_ft,
            ),
        )

    def remove(
        self,
        element_id,
    ):
        cells = self._element_cells.pop(
            element_id,
            (),
        )

        for cell in cells:
            bucket = self._cells.get(
                cell
            )

            if bucket is None:
                continue

            bucket.discard(
                element_id
            )

            if not bucket:
                self._cells.pop(
                    cell,
                    None,
                )

        self._elements.pop(
            element_id,
            None,
        )

        self.max_clearance_ft = max(
            (
                max(
                    0.0,
                    element.clearance_ft,
                )
                for element
                in self._elements.values()
            ),
            default=0.0,
        )

    def update(
        self,
        element,
    ):
        self.remove(
            element.element_id
        )

        self.insert(
            element
        )

    def get(
        self,
        element_id,
    ):
        return self._elements.get(
            element_id
        )

    def elements(self):
        return tuple(
            self._elements.values()
        )

    def query(
        self,
        bounds,
        *,
        expansion_ft=0.0,
    ):
        if expansion_ft < 0:
            raise SpatialIndexError(
                "query expansion cannot be negative"
            )

        query_bounds = (
            expand(
                bounds,
                expansion_ft,
            )
            if expansion_ft > 0
            else bounds
        )

        result = set()

        for cell in self.cells_for_bounds(
            query_bounds
        ):
            result.update(
                self._cells.get(
                    cell,
                    (),
                )
            )

        return tuple(
            sorted(result)
        )

    def candidate_pairs(self):
        pairs = set()

        for element in self._elements.values():
            expansion_ft = (
                max(
                    0.0,
                    element.clearance_ft,
                )
                + self.max_clearance_ft
            )

            for other_id in self.query(
                element.bounds,
                expansion_ft=expansion_ft,
            ):
                if (
                    other_id
                    == element.element_id
                ):
                    continue

                pairs.add(
                    tuple(
                        sorted(
                            (
                                element.element_id,
                                other_id,
                            )
                        )
                    )
                )

        return tuple(
            sorted(pairs)
        )
