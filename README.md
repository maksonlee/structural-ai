# structural-ai

The inputs, scripts and reviewed outputs behind
[a WordPress case study](docs/current-work.md) about AI-assisted architectural and
structural coordination. The example is one simulated three-storey RC office in
Taipei, approximately 18 × 12 m, without a basement.

## Follow the case

| Stage | Input and work | Open the output |
|---|---|---|
| Architect | Organize spaces, levels, stairs, lift requirements and openings | [Brief, IFC proposal and review drawings](project/architect/outputs/README.md) |
| Structural engineer | Interpret the architectural package; record materials, loads, supports and interface questions | [Structural inputs](project/structural/inputs/README.md) |
| Analysis and coordination | Run OpenSees, check results, resolve an interface issue and update the review sheets | [Structural report and drawings](project/structural/outputs/current.md) |
| Reinforcement illustration | Use one landing strip's geometry and gravity demand to compare reinforcement | [Calculation and drawing](project/structural/outputs/deliverables/landing-strip.md) |
| Comparison | Compare recorded work with attributable sources, existing automation and AI assistance | [Workflow evidence and gaps](project/comparison/README.md) |

AI assists with organizing information, developing scripts and tracing revisions.
IfcOpenShell handles IFC geometry, Python prepares models and reports, and
OpenSees performs the numerical analysis. The case compares published accounts
and tool capabilities; it does not establish a universal office workflow,
matched ETABS results or measured labour savings.

## Scope

The current deliverable is an introductory article supported by this reproducible
case. It follows architectural requirements through structural interpretation,
calculation, coordination feedback and revised drawings. Each performed stage
needs identifiable inputs/outputs, attributable sources, and clear limitations.
The article includes one actual coordination iteration and a scoped reinforcement
example. Keep its practical narrative and three principal figures; detailed
calculations belong in the companion files. The approximate 1,000-word editorial
target can expand for useful explanations without becoming an engineering course.

The wider design objectives are architectural fit, applicable regulations, cost
control and construction feasibility. Taiwan supplies this case's location and
code basis. Current evidence covers diagnostic whole-building analysis and one
local gravity reinforcement example. Full earthquake/wind design, all-member RC,
complete stairs/joints/anchorage, foundations, pricing and construction acceptance
remain open in the [design checklist](project/structural/design/checklist.yaml).

A completed solve is not full design approval. Fixed supports are not foundation
design; synthetic inputs are not actual surveys or supplier confirmations.
NOT_CHECKED is not PASS, and NOT_APPLICABLE requires a reason. Article readiness,
numerical verification, full design and professional approval are separate states.
All outputs are research material. The project does not develop a general FEM
solver, an ETABS replacement or a web platform.

## Files and data authority

| Location | Purpose |
|---|---|
| `project/architect/outputs/` | Architectural requirements, core specification, IFC and review drawings |
| `project/structural/inputs/` | Explicitly adopted geometry and analytical assumptions |
| `project/structural/design/` | Calculations, check coverage and synthetic equipment inputs |
| `project/structural/outputs/deliverables/` | Reviewed calculation results, drawings and source receipts |
| `project/structural/outputs/runs/` | Ignored generated models, logs and raw execution evidence |
| `project/comparison/` | Industry evidence, workflow comparison, effort and gaps |
| `src/structural_ai/`, `tests/` | One implementation and its verification tests |
| `docs/` | Reproduction instructions, sources, verification methods and original article figures |

[Project configuration](project/project.yaml) assigns one authority to each field.
Requirements and core specifications generate an architectural proposal; source,
converter and interface review precede explicit structural adoption. Generated IFC
does not automatically update analysis assumptions. The immutable received IFC
and focused fixtures remain regeneration inputs, with source GUIDs preserved.
The model-adoption and drawing manifests bind current inputs to reviewed outputs.
Changes to geometry or paths require consistency and identity checks.

Keep current verification, material failure evidence and required fixtures; do not
imply deleted historical runs still exist. Case decisions and unresolved work live
in [decisions](project/decisions.md) and [issues](project/issues.yaml).

## Reproduce and check

Start with [setup and commands](docs/development.md). Reproduction uses a local
Python environment and needs no AI account. The supporting references are
[dependency versions](docs/requirements-linux-py314.txt),
[verification methods and limits](docs/validation.md),
[wall/frame interfaces](docs/wall-interface-method.md), and
[the source register](docs/sources.yaml).

WordPress holds the article; this repository holds its companion files.
No project-wide licence has been selected. Preserve existing
[notices](THIRD_PARTY_NOTICES.md) and review [release requirements](docs/publishing.md)
before publication or redistribution.
