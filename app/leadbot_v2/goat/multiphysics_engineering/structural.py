from __future__ import annotations

import math

from .models import (
    EngineeringModelError,
    StructuralAnalysisResult,
    TrussMemberResult,
)

from .numerics import (
    solve_linear_system,
)


class Truss2DSolver:
    """
    Deterministic small-displacement linear-elastic 2D truss solver.

    Professional engineering review remains required for final design,
    modeling assumptions, stability, connections, buckling, load generation,
    nonlinear effects, and governing-code compliance.
    """

    def solve(
        self,
        *,
        nodes,
        members,
        loads,
    ):
        nodes = tuple(nodes)
        members = tuple(members)
        loads = tuple(loads)

        if not nodes:
            raise EngineeringModelError(
                "truss requires nodes"
            )

        node_map = {}

        for node in nodes:
            if node.node_id in node_map:
                raise EngineeringModelError(
                    "duplicate node id"
                )

            node_map[
                node.node_id
            ] = node

        index = {
            node.node_id:
                position
            for position, node
            in enumerate(nodes)
        }

        dof_count = (
            2 * len(nodes)
        )

        stiffness = [
            [
                0.0
                for _ in range(
                    dof_count
                )
            ]
            for _ in range(
                dof_count
            )
        ]

        geometry = {}

        for member in members:
            if (
                member.node_i
                not in node_map
                or member.node_j
                not in node_map
            ):
                raise EngineeringModelError(
                    "member references unknown node"
                )

            if member.area <= 0:
                raise EngineeringModelError(
                    "member area must be positive"
                )

            if (
                member.elastic_modulus
                <= 0
            ):
                raise EngineeringModelError(
                    "elastic modulus must be positive"
                )

            ni = node_map[
                member.node_i
            ]

            nj = node_map[
                member.node_j
            ]

            dx = nj.x - ni.x
            dy = nj.y - ni.y

            length = math.hypot(
                dx,
                dy,
            )

            if length <= 1.0e-12:
                raise EngineeringModelError(
                    "zero-length truss member"
                )

            c = dx / length
            s = dy / length

            scale = (
                member.area
                * member.elastic_modulus
                / length
            )

            base = (
                (c*c, c*s, -c*c, -c*s),
                (c*s, s*s, -c*s, -s*s),
                (-c*c, -c*s, c*c, c*s),
                (-c*s, -s*s, c*s, s*s),
            )

            element = tuple(
                tuple(
                    scale * value
                    for value in row
                )
                for row in base
            )

            i = index[
                member.node_i
            ]

            j = index[
                member.node_j
            ]

            dofs = (
                2*i,
                2*i + 1,
                2*j,
                2*j + 1,
            )

            for r in range(4):
                for col in range(4):
                    stiffness[
                        dofs[r]
                    ][
                        dofs[col]
                    ] += (
                        element[r][col]
                    )

            geometry[
                member.member_id
            ] = (
                member,
                length,
                c,
                s,
            )

        force = [
            0.0
            for _ in range(
                dof_count
            )
        ]

        applied_fx = 0.0
        applied_fy = 0.0

        for load in loads:
            if load.node_id not in node_map:
                raise EngineeringModelError(
                    "load references unknown node"
                )

            position = index[
                load.node_id
            ]

            force[
                2 * position
            ] += load.fx

            force[
                2 * position + 1
            ] += load.fy

            applied_fx += load.fx
            applied_fy += load.fy

        restrained = set()

        for node in nodes:
            position = index[
                node.node_id
            ]

            if node.restrained_x:
                restrained.add(
                    2 * position
                )

            if node.restrained_y:
                restrained.add(
                    2 * position + 1
                )

        free = tuple(
            dof
            for dof
            in range(dof_count)
            if dof not in restrained
        )

        if not free:
            raise EngineeringModelError(
                "no free degrees of freedom"
            )

        reduced_k = tuple(
            tuple(
                stiffness[row][col]
                for col in free
            )
            for row in free
        )

        reduced_f = tuple(
            force[dof]
            for dof in free
        )

        solver = solve_linear_system(
            reduced_k,
            reduced_f,
        )

        if not solver.converged:
            raise EngineeringModelError(
                "structural linear solver "
                "residual exceeded tolerance"
            )

        displacement = [
            0.0
            for _ in range(
                dof_count
            )
        ]

        for position, dof in enumerate(
            free
        ):
            displacement[dof] = (
                solver.solution[position]
            )

        internal_force = [
            sum(
                stiffness[row][col]
                * displacement[col]
                for col
                in range(dof_count)
            )
            for row
            in range(dof_count)
        ]

        reaction = [
            internal_force[dof]
            - force[dof]
            for dof
            in range(dof_count)
        ]

        node_displacements = {}
        support_reactions = {}

        for node in nodes:
            position = index[
                node.node_id
            ]

            node_displacements[
                node.node_id
            ] = (
                displacement[
                    2 * position
                ],
                displacement[
                    2 * position + 1
                ],
            )

            support_reactions[
                node.node_id
            ] = (
                reaction[
                    2 * position
                ]
                if node.restrained_x
                else 0.0,

                reaction[
                    2 * position + 1
                ]
                if node.restrained_y
                else 0.0,
            )

        member_results = []

        for (
            member,
            length,
            c,
            s,
        ) in geometry.values():
            i = index[
                member.node_i
            ]

            j = index[
                member.node_j
            ]

            uix = displacement[2*i]
            uiy = displacement[2*i + 1]

            ujx = displacement[2*j]
            ujy = displacement[2*j + 1]

            extension = (
                c * (ujx - uix)
                + s * (ujy - uiy)
            )

            strain = (
                extension
                / length
            )

            stress = (
                member.elastic_modulus
                * strain
            )

            axial_force = (
                stress
                * member.area
            )

            member_results.append(
                TrussMemberResult(
                    member_id=(
                        member.member_id
                    ),
                    axial_force=(
                        axial_force
                    ),
                    axial_stress=stress,
                    axial_strain=strain,
                    elongation=extension,
                )
            )

        reaction_fx = sum(
            pair[0]
            for pair
            in support_reactions.values()
        )

        reaction_fy = sum(
            pair[1]
            for pair
            in support_reactions.values()
        )

        equilibrium_error = (
            math.hypot(
                reaction_fx
                + applied_fx,
                reaction_fy
                + applied_fy,
            )
        )

        return StructuralAnalysisResult(
            node_displacements=(
                node_displacements
            ),
            support_reactions=(
                support_reactions
            ),
            member_results=tuple(
                member_results
            ),
            solver=solver,
            equilibrium_error=(
                equilibrium_error
            ),
        )
