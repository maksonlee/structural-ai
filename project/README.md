# One building, from brief to structural review

The example is a simulated three-storey RC office without a basement, approximately
18 x 12 m, in Taipei's Datong District, Jianming Village.

| Step | Input or output | Work shown |
|---|---|---|
| 1. Architect | [Brief and proposal](architect/outputs/README.md) | Office uses, spaces, stairs/lift, openings and architectural review drawings |
| 2. Structural engineer | [Inputs](structural/inputs/README.md) | Interpret geometry, select analytical assumptions and record loads |
| 3. Calculate and coordinate | [Report and drawings](structural/outputs/current.md) | Actual analysis, an interface correction and returned review sheets |
| 4. Show reinforcement | [Landing example](structural/outputs/deliverables/landing-strip.md) | Selected gravity checks, bar alternatives and a scoped drawing |
| 5. Compare with practice | [Taiwan comparison](comparison/README.md) | Attributed work products, existing automation and AI assistance |

Read these as the stages of one project. Revision codes are not part of the
reader's filenames or required background.

`project.yaml` names the input authorities. `scheme.yaml` owns space/equipment
requirements and stair finishes; `core-proposal.yaml` specifies the core layout;
`structural/inputs/structural.ifc` owns adopted geometry. A generated IFC does
not automatically update structural assumptions.

The article is maintained in WordPress; [current work](../docs/current-work.md)
identifies the draft. The
[engineering checklist](structural/design/checklist.yaml) separates the performed
examples from unfinished whole-building design. `decisions.md` explains the
design basis; `issues.yaml` lists unresolved work. Optional raw calculation
evidence lives under structural outputs, outside the article reading path.
