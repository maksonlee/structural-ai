# Structural inputs

The structural role receives the architect's geometry and requirements, then
records the assumptions needed for analysis.

| Input | Authority |
|---|---|
| `structural.ifc` | Adopted physical geometry, matching the architect's core model |
| `analysis.yaml` | Materials, analytical stiffness/supports, loads, mass and diagnostic cases |
| `../design/core-interface-loads.yaml` | Explicit synthetic equipment/panel/roof allowances |
| `../../architect/outputs/scheme.yaml` | Space/equipment requirements and stair finishes |
| `coordination.yaml` | Declared coordination screens and their scope |

[Project configuration](../../project.yaml) names the field owners.
[The model receipt](../outputs/deliverables/model-adoption.json) binds the input
hashes to actual verification. Changing a source requires converter/consistency
review and affected downstream calculations, not replacing an expected hash.

`received-scheme.ifc` is an immutable regeneration input used by the converter
and tests. It is not the geometry to read as the architect's completed proposal.
Internal schema IDs support compatibility; they are not separate active projects.

Unknown soil/equipment/finish inputs are not confirmed zero. The fixed base is a
diagnostic assumption, and the source IFC alone does not define a complete design.
