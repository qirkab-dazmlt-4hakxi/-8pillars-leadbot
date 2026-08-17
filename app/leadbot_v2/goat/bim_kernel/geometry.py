from __future__ import annotations

import math

from .models import (
    AABB,
    GeometryError,
    Vec3,
)


EPS = 1.0e-9


def add(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.x + b.x,
        a.y + b.y,
        a.z + b.z,
    )


def subtract(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.x - b.x,
        a.y - b.y,
        a.z - b.z,
    )


def scale(value: Vec3, factor: float) -> Vec3:
    return Vec3(
        value.x * factor,
        value.y * factor,
        value.z * factor,
    )


def dot(a: Vec3, b: Vec3) -> float:
    return (
        a.x * b.x
        + a.y * b.y
        + a.z * b.z
    )


def cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def magnitude(value: Vec3) -> float:
    return math.sqrt(
        dot(value, value)
    )


def normalize(value: Vec3) -> Vec3:
    length = magnitude(value)

    if length <= EPS:
        raise GeometryError(
            "cannot normalize zero vector"
        )

    return scale(
        value,
        1.0 / length,
    )


def distance(a: Vec3, b: Vec3) -> float:
    return magnitude(
        subtract(a, b)
    )


def validate_aabb(bounds: AABB) -> AABB:
    if (
        bounds.minimum.x > bounds.maximum.x
        or bounds.minimum.y > bounds.maximum.y
        or bounds.minimum.z > bounds.maximum.z
    ):
        raise GeometryError(
            "invalid AABB min/max order"
        )

    return bounds


def box_from_center(
    center: Vec3,
    size_x: float,
    size_y: float,
    size_z: float,
) -> AABB:
    if min(
        size_x,
        size_y,
        size_z,
    ) < 0:
        raise GeometryError(
            "box dimensions cannot be negative"
        )

    hx = size_x / 2.0
    hy = size_y / 2.0
    hz = size_z / 2.0

    return AABB(
        minimum=Vec3(
            center.x - hx,
            center.y - hy,
            center.z - hz,
        ),
        maximum=Vec3(
            center.x + hx,
            center.y + hy,
            center.z + hz,
        ),
    )


def bounds_from_points(points) -> AABB:
    points = tuple(points)

    if not points:
        raise GeometryError(
            "bounds require at least one point"
        )

    return AABB(
        minimum=Vec3(
            min(p.x for p in points),
            min(p.y for p in points),
            min(p.z for p in points),
        ),
        maximum=Vec3(
            max(p.x for p in points),
            max(p.y for p in points),
            max(p.z for p in points),
        ),
    )


def center(bounds: AABB) -> Vec3:
    validate_aabb(bounds)

    return Vec3(
        (
            bounds.minimum.x
            + bounds.maximum.x
        ) / 2.0,
        (
            bounds.minimum.y
            + bounds.maximum.y
        ) / 2.0,
        (
            bounds.minimum.z
            + bounds.maximum.z
        ) / 2.0,
    )


def size(bounds: AABB) -> Vec3:
    validate_aabb(bounds)

    return Vec3(
        bounds.maximum.x
        - bounds.minimum.x,
        bounds.maximum.y
        - bounds.minimum.y,
        bounds.maximum.z
        - bounds.minimum.z,
    )


def volume(bounds: AABB) -> float:
    extent = size(bounds)

    return (
        extent.x
        * extent.y
        * extent.z
    )


def expand(
    bounds: AABB,
    amount: float,
) -> AABB:
    validate_aabb(bounds)

    if amount < 0:
        raise GeometryError(
            "expansion cannot be negative"
        )

    return AABB(
        minimum=Vec3(
            bounds.minimum.x - amount,
            bounds.minimum.y - amount,
            bounds.minimum.z - amount,
        ),
        maximum=Vec3(
            bounds.maximum.x + amount,
            bounds.maximum.y + amount,
            bounds.maximum.z + amount,
        ),
    )


def translate(
    bounds: AABB,
    delta: Vec3,
) -> AABB:
    validate_aabb(bounds)

    return AABB(
        minimum=add(
            bounds.minimum,
            delta,
        ),
        maximum=add(
            bounds.maximum,
            delta,
        ),
    )


def union(a: AABB, b: AABB) -> AABB:
    validate_aabb(a)
    validate_aabb(b)

    return AABB(
        minimum=Vec3(
            min(
                a.minimum.x,
                b.minimum.x,
            ),
            min(
                a.minimum.y,
                b.minimum.y,
            ),
            min(
                a.minimum.z,
                b.minimum.z,
            ),
        ),
        maximum=Vec3(
            max(
                a.maximum.x,
                b.maximum.x,
            ),
            max(
                a.maximum.y,
                b.maximum.y,
            ),
            max(
                a.maximum.z,
                b.maximum.z,
            ),
        ),
    )


def overlap_depths(a: AABB, b: AABB):
    validate_aabb(a)
    validate_aabb(b)

    return (
        min(
            a.maximum.x,
            b.maximum.x,
        )
        - max(
            a.minimum.x,
            b.minimum.x,
        ),
        min(
            a.maximum.y,
            b.maximum.y,
        )
        - max(
            a.minimum.y,
            b.minimum.y,
        ),
        min(
            a.maximum.z,
            b.maximum.z,
        )
        - max(
            a.minimum.z,
            b.minimum.z,
        ),
    )


def hard_intersects(
    a: AABB,
    b: AABB,
    *,
    tolerance=EPS,
) -> bool:
    dx, dy, dz = overlap_depths(
        a,
        b,
    )

    return (
        dx > tolerance
        and dy > tolerance
        and dz > tolerance
    )


def overlap_volume(
    a: AABB,
    b: AABB,
) -> float:
    dx, dy, dz = overlap_depths(
        a,
        b,
    )

    return (
        max(0.0, dx)
        * max(0.0, dy)
        * max(0.0, dz)
    )


def axis_gap(
    min_a,
    max_a,
    min_b,
    max_b,
) -> float:
    if max_a < min_b:
        return min_b - max_a

    if max_b < min_a:
        return min_a - max_b

    return 0.0


def aabb_distance(
    a: AABB,
    b: AABB,
) -> float:
    validate_aabb(a)
    validate_aabb(b)

    gx = axis_gap(
        a.minimum.x,
        a.maximum.x,
        b.minimum.x,
        b.maximum.x,
    )

    gy = axis_gap(
        a.minimum.y,
        a.maximum.y,
        b.minimum.y,
        b.maximum.y,
    )

    gz = axis_gap(
        a.minimum.z,
        a.maximum.z,
        b.minimum.z,
        b.maximum.z,
    )

    return math.sqrt(
        gx * gx
        + gy * gy
        + gz * gz
    )


def segment_bounds(
    start: Vec3,
    end: Vec3,
    *,
    radius_ft=0.0,
) -> AABB:
    if radius_ft < 0:
        raise GeometryError(
            "segment radius cannot be negative"
        )

    return expand(
        bounds_from_points(
            (
                start,
                end,
            )
        ),
        radius_ft,
    )
