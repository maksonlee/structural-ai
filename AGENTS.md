# Project instructions for coding agents

## Mission and completion criteria

The owner's current priority is one accessible WordPress article about AI-assisted
architectural and structural coordination, illustrated by this simulated building.
Explain the shared workflow; Taiwan identifies the case location and applicable
regulations. Keep attributed local practice as background evidence without presenting
it as the only workflow or claiming that professional practice is identical worldwide.
Read the scope in README.md and docs/current-work.md. The article is maintained in WordPress,
not in this repository; the current-work document identifies its draft and style basis.
Present the case from its brief through design-stage outputs; no development
history or internal revision code belongs in reader filenames or figure titles. Keep the whole design workflow visible, with unfinished stages explicit;
do not require a long engineering course or expand the toolchain for the article.
Organize work around the architect's deliverables and the structural engineer's
inputs, design decisions and outputs. Repeated coordination must lead to structural
drawings evaluated for code compliance, architectural requirements, cost control
and construction feasibility. A solver run or a folder reorganization does not
close any of those design acceptance gates.
Do not reduce the scope of the story to OpenSees-only work or an isolated member demo. Do not
create a general replacement for ETABS or another finite-element solver kernel.

Read README.md, docs/development.md, docs/validation.md,
project/README.md, project/decisions.md and project/issues.yaml.

## Repository rules

One active copy of code in src/structural_ai and one project in project/.
Architect deliverables belong in project/architect/outputs/. Structural inputs,
design work and outputs belong in project/structural/{inputs,design,outputs}/.
Shared decisions, issues and comparison records remain at project level.
Tests belong in tests; reviewed outputs in project/structural/outputs/deliverables/.
Generated builds/logs/results belong in new ignored project/structural/outputs/runs/<run-id> dirs.
Do not recreate baseline/, work/, old/, final2/ or R01/R02 source copies.
Do not recreate projects/a01/ or artifacts/a01/. Retain historical A01 IDs.
The owner authorizes removal of obsolete raw runs after dependency review; keep
the current design's evidence and required comparison inputs. Record removed IDs
and evidence limitations instead of claiming all historical runs remain available.
Reader filenames describe their purpose. Use project/structural/outputs/current.md;
model-adoption.json and drawing-manifest.json identify current inputs/outputs.
Technical schema IDs and immutable execution/failure records remain where needed
for reproduction. Do not restore obsolete housekeeping diaries to the article.
Presentation path mappings are recorded in docs/provenance/presentation.json.
Do not delete runs merely by age, overwrite evidence or bypass changed hashes.
Git commits/tags preserve history. Preserve external original archives; do not delete
or import them wholesale into this public-intended checkout.

Use English for source comments, public documentation and agent instructions.
Keep original-language regulation titles where necessary and identify the source.
No frontend, microservices or database is required to complete this case study.

## Model integrity and truthfulness

Do not silently redesign accepted geometry: retain regular frame, B2/C2 columns,
orthogonal continuous main beam lines, rear 7.5 m bay and shared stair/lift wall.
Openings are real voids; no opaque fills, unexplained inter-core gap or arbitrary
beam cutoff. These are case-specific design intentions, not universal structural laws.
If analysis or code checking requires a change, propose and document the whole
coordinated revision rather than hiding it in a geometry patch.

Fixed bases are diagnostic assumptions, NOT foundation design. A future full
design claim requires explicit simulated ground assumptions and foundation
analysis/design; an introductory article may identify that work as unfinished.
No basement or ground-floor diaphragm is implied.
Unknown equipment/soil/input is not zero. Preserve units, loads, mass, offsets and
web/flange treatment for the first diagnostic comparison; never force agreement.

The adopted H03-C converter derives core geometry and owned wall strips from the
reviewed source, with case-specific frame dimensions and interface assumptions.
Immutable received R05 and focused H02 fixtures support historical reproduction.
The active source and received-source SHA256 guards are deliberate. A source
change requires an adapter/consistency review, not just changing the hash. The
IFC subset reader is not a full validator. Independently validate IFC as needed.
Keep source-GUID-to-analytical-element mapping and one authority for each field.

## Execution evidence

Historical SciPy results are NOT OpenSees results or ETABS results. Scoped runtime
verification is recorded in the dated A01 diagnostic report; read
docs/current-work.md before repeating the migration milestone. Do not claim a solver run because a
file exists, syntax passed, or a process wrapper ran. No fallback custom solver.
Use actual solver/version/command/exit status and outputs, with input/source hashes.
Update stage status only with evidence; not_checked is not pass. Code tests,
analysis verification, member design, full project completion and public publication
are separate gates. Do not label drawings for construction.

H03-C adopts the reviewed H03-B geometry for verified gross elastic diagnostics.
Direct wall/frame contacts, concrete ownership, eccentric forces, the web centre
and load-coordinate precision are corrected. Five 19-case/12-mode variants and
ordinary CLI reproduction passed; four review sheets match the current source.
Read the current output index, structural review, model receipt and interface
method before continuing. Preserve the failed first mesh-moment check; thresholds
were not relaxed. Rigid joints do not establish RC or construction acceptance.
B2 does NOT obstruct the portal: its north face is y=4.50 m and the portal starts
at y=4.60 m. Equipment loads remain synthetic. The article is now a WordPress draft
with three figures and RC-001, a scoped existing-landing gravity reinforcement
example. Read its report and compact execution record; all 75 tests passed and
JSON/SVG reproduction matched. Whole landing, anchorage and full design remain
open. Article drafting and its three original figure uploads are authorized.
Continue editorial work in WordPress; do not recreate a local article copy.
Publication is a separate action. Do not restart
the initial solver milestone or automatically launch all-member design.

## Full workflow and industry comparison

Maintain project/structural/design/checklist.yaml and project/comparison/ alongside each stage.
Capture inputs/tools/human and AI work/iterations/outputs/checks/effort/limitations.
Separate setup and debugging from recurring project/change effort. Do not invent
industry times, ETABS runs, equivalence or savings. Official tool features support
what a product can do, not what every engineering firm does. Verify claims with sources.
Small known-answer member tests are useful internal tests, never the final scope.

## Regulations and public release

Before implementing a check, verify current official source, effective version,
clause, application category, units and limits. Inherited code values are provisional,
not a substitute for current verification. Simulated reports must not impersonate
licensed offices, surveyed ground conditions or vendor-certified equipment data.

This repository is intended for eventual public release, but do not publish, push,
change visibility or upload private artifacts without explicit authorization.
Do not embed personal machine names, usernames, absolute paths, credentials or
raw chat logs. Preserve attribution and licenses. Review OpenSees restrictions.
Never assume MIT on our own code covers third-party libraries or regulations.
Use local virtual environments; no sudo pip, global Python replacement or root Codex.

## First work on the target machine

Confirm clean imports/tests/build reproduction. Verify installation compatibility,
install OpenSeesPy in the project venv, and independently validate the adapter using
small known-solution tests. Then run A01 gravity, modal and X/Y calibration cases.
Keep full-project work on the roadmap; do not end the project at this milestone.
Finish each task with actual edits, commands, test scope, results, failures and next
blocking decisions. AGENTS.md is guidance; implement critical rules as tests/checks.


## Taiwan practice research before implementation

Read docs/industry/taiwan-workflow.md and project/comparison/research-gaps.yaml
before treating any generated output as representative of Taiwan practice.
The project owner does not supply professional-office experience; proactively
research the missing process rather than asking them to discover omissions in a model.

For each active design stage, first identify an attributable Taiwan practice
source and the applicable current official requirements, then implement and compare.
Keep statutory requirements, dated practitioner accounts, vendor capabilities,
historical examples and A01 assumptions distinct in comparison/evidence.yaml.
Do not infer national prevalence from a job posting, an API, one firm or one old report.
Do not represent a search snippet, unviewed video or inaccessible PDF as fully reviewed.
Do not use obsolete example coefficients or vendor defaults as the current design code.

Document remaining questions without inventing interviews, professional approval,
ETABS results or timing. Article 7 software filing and Taipei special-review
applicability require separate verification for real submissions; they are not
claimed approvals or barriers to the simulated research runs. Preserve all open
engineering gates. Link sources, not full copyrighted manuals or private project data.
