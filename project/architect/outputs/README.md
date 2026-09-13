# Architect's outputs

Begin with the [project requirements](scheme.yaml) and [core layout](core-proposal.yaml).
They describe the simulated office spaces, stair/lift interfaces, openings and
finish allowances.

| Output | Purpose |
|---|---|
| [IFC overview SVG](ifc-overview.svg) | Three-dimensional view of the actual proposal, with transparent floors/walls and labelled stairs, shaft and shared wall |
| [Architectural review PDF](architectural-review.pdf) | Two sheets: building/core arrangement and entrance details |
| [Architectural plan SVG](architectural-plan.svg) | Vector version of the arrangement sheet |
| [Entrance detail SVG](entrance-detail.svg) | Vector version of the entrance sheet |
| [Core model IFC](core-candidate.ifc) | Geometry supplied for structural interpretation |
| [Review notes](architectural-review.md) | Checked dimensions and unresolved architectural work |

The [handoff inventory](handoff.yaml) records the initial intake, before this
proposal was generated. Its missing-file statuses and the earlier review notes in
the two YAML specifications are preserved generation inputs, not current approval
status. Read [the review notes](architectural-review.md) for current dimensions
and open items; `architectural-review.json` contains the numerical screens.

`received-scheme.ifc` is the starting reference. The generated `core-candidate.ifc`
develops its stairs, landings, openings and lift/pit/roof interfaces while retaining
the main frame. The structural role explicitly adopted the candidate as
`structural.ifc`; those two files currently have identical content. The
[project configuration](../../project.yaml) and
[model receipt](../../structural/outputs/deliverables/model-adoption.json) identify
that adoption. These are simulated outputs, not an architectural-office issue or
a complete permit package.
