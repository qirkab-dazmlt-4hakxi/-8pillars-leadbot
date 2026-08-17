from __future__ import annotations

import math

from .models import (
    LinearSystemResult,
    NumericalFailure,
)


def vector_norm(values) -> float:
    return math.sqrt(
        sum(
            float(value) * float(value)
            for value in values
        )
    )


def matrix_vector(
    matrix,
    vector,
):
    return tuple(
        sum(
            float(a) * float(b)
            for a, b in zip(
                row,
                vector,
            )
        )
        for row in matrix
    )


def residual(
    matrix,
    solution,
    rhs,
):
    product = matrix_vector(
        matrix,
        solution,
    )

    return tuple(
        product[index]
        - float(rhs[index])
        for index
        in range(len(rhs))
    )


def solve_linear_system(
    matrix,
    rhs,
    *,
    pivot_tolerance=1.0e-12,
    residual_tolerance=1.0e-8,
):
    n = len(matrix)

    if n == 0:
        raise NumericalFailure(
            "linear system is empty"
        )

    if len(rhs) != n:
        raise NumericalFailure(
            "rhs dimension mismatch"
        )

    a = []

    for row in matrix:
        if len(row) != n:
            raise NumericalFailure(
                "matrix must be square"
            )

        a.append(
            [
                float(value)
                for value in row
            ]
        )

    b = [
        float(value)
        for value in rhs
    ]

    original_a = tuple(
        tuple(row)
        for row in a
    )

    original_b = tuple(b)

    pivots = []

    for column in range(n):
        pivot_row = max(
            range(column, n),
            key=lambda row:
                abs(
                    a[row][column]
                ),
        )

        pivot = abs(
            a[pivot_row][column]
        )

        if pivot <= pivot_tolerance:
            raise NumericalFailure(
                "singular or near-singular linear system"
            )

        if pivot_row != column:
            a[column], a[pivot_row] = (
                a[pivot_row],
                a[column],
            )

            b[column], b[pivot_row] = (
                b[pivot_row],
                b[column],
            )

        diagonal = a[column][column]

        pivots.append(
            abs(diagonal)
        )

        for row in range(
            column + 1,
            n,
        ):
            factor = (
                a[row][column]
                / diagonal
            )

            if factor == 0.0:
                continue

            a[row][column] = 0.0

            for col in range(
                column + 1,
                n,
            ):
                a[row][col] -= (
                    factor
                    * a[column][col]
                )

            b[row] -= (
                factor
                * b[column]
            )

    solution = [
        0.0
        for _ in range(n)
    ]

    for row in range(
        n - 1,
        -1,
        -1,
    ):
        subtotal = sum(
            a[row][col]
            * solution[col]
            for col
            in range(
                row + 1,
                n,
            )
        )

        diagonal = a[row][row]

        if (
            abs(diagonal)
            <= pivot_tolerance
        ):
            raise NumericalFailure(
                "singular diagonal during "
                "back substitution"
            )

        solution[row] = (
            b[row]
            - subtotal
        ) / diagonal

    residual_vector = residual(
        original_a,
        solution,
        original_b,
    )

    residual_norm_value = (
        vector_norm(
            residual_vector
        )
    )

    rhs_norm = max(
        vector_norm(
            original_b
        ),
        1.0e-30,
    )

    relative_residual = (
        residual_norm_value
        / rhs_norm
    )

    minimum_pivot = min(pivots)
    maximum_pivot = max(pivots)

    pivot_ratio = (
        maximum_pivot
        / max(
            minimum_pivot,
            1.0e-30,
        )
    )

    return LinearSystemResult(
        solution=tuple(solution),
        residual_norm=(
            residual_norm_value
        ),
        relative_residual=(
            relative_residual
        ),
        minimum_pivot=(
            minimum_pivot
        ),
        maximum_pivot=(
            maximum_pivot
        ),
        pivot_ratio=(
            pivot_ratio
        ),
        converged=(
            relative_residual
            <= residual_tolerance
        ),
    )
