# Local development and reproduction

Run commands from the checkout root on Ubuntu, using a project virtual environment.
Reproduction requires no AI account or Codex installation.
Read [the project](../project/README.md) and [current work](current-work.md).

The tested Linux x86_64 environment is Python 3.14.4, OpenSeesPy/Linux 3.8.0.0
(engine 3.8.0), IfcOpenShell 0.8.5, NumPy 2.5.3, Shapely 2.1.2 and PyYAML 6.0.3.
Pins are in [the tested dependency list](requirements-linux-py314.txt); they describe
this environment, not a universal lock. Use an available Python 3.14 interpreter
with venv support; Ubuntu's default `python3` may be a different version. Do not
replace the system Python. Other Python/platform combinations require compatible
dependency resolution and a fresh verification run; the package's `>=3.10` metadata
does not establish compatibility with these exact pins. In the installed pins,
NumPy and OpenSeesPy's Linux backend require Python 3.12 or later.
Review [upstream terms](../THIRD_PARTY_NOTICES.md) before installation or reuse.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -c docs/requirements-linux-py314.txt -e '.[analysis,ifc-validation]'
```

Use local environments; no sudo pip or global Python replacement. The IFC extra
includes pytest for IfcOpenShell EXPRESS assertion support; project tests use
unittest. No solver binaries or regulation/vendor documents are bundled.

The commands below are portable reader commands. The original development host
additionally requires its locally installed `codex-build-limited --` wrapper for
installation, tests, building, solving and rendering, with sequential execution:
2 CPUs, 2 GiB memory-high, 4 GiB memory-max and 1 GiB swap. That administrative
wrapper is not bundled or required on other hosts. Agents working on the original
host must still use its configured wrapper and must not retry without limits.

## Build and solve

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m structural_ai validate --project project
structural_build=$(.venv/bin/python -m structural_ai build --project project)
.venv/bin/python -m structural_ai analyze --project project --model "$structural_build/analytical_model.json" --case all --modes 12
```

Continue only after each command succeeds. The variable captures the actual emitted
build path. Input hashes reject stale IFC, configuration,
architectural requirements and equipment. Missing/failed OpenSees does not invoke
a fallback. Check numerical results, not just the process return code.

To reproduce all five variants, source checks, repeat/refinement and modes:

```sh
.venv/bin/python scripts/verify_core_candidate.py --project project --revision H03-C
```

Here `H03-C` is the internal adapter selector for the verified model. It is
not a reader-facing file revision or another project. Keep the explicit argument:
the verifier's default selects a different regression formulation.
Each variant has 19 static cases and 12 modes. This command does not change
adopted inputs or establish code actions/member design.

## Drawings and reinforcement illustration

```sh
.venv/bin/python -m structural_ai core-review --project project
.venv/bin/python scripts/draw_wall_interfaces.py --source project/structural/inputs/structural.ifc --verification 'project/structural/outputs/runs/<verification-id>' --output 'project/structural/outputs/runs/<task-id>/interface-drawings'
```

Replace `<verification-id>` with the directory printed by the completed five-variant
verifier above, and `<task-id>` with a new descriptive run ID. Keep the quotes;
angle brackets are shell redirection characters when unquoted. Use unused output
directories. Architectural generation checks the source,
requirements and adoption identity before drawing. Structural drawing generation
checks completed evidence and source sections.

Use the same completed verifier directory for the landing calculation:

```sh
.venv/bin/python scripts/design_landing_strip.py --verification 'project/structural/outputs/runs/<verification-id>' --output 'project/structural/outputs/runs/<task-id>/landing'
```

The selector checks successful verification, current engineering inputs and
implementation, recorded output hashes, and the exact adopted analytical model.
Article prose and run timestamps do not define that model identity. The source,
load ledger and actual OpenSees summary must remain bound to the selected run.
This reproduces the same adopted case; it does not adopt a changed design.

Without `--verification`, the command uses the original run and exact manifest
hash named in [model-adoption.json](../project/structural/outputs/deliverables/model-adoption.json).
Raw runs are ignored by Git, so a fresh checkout should run the verifier and pass
its new directory as shown above. Do not rename a run or edit receipt hashes.

The local calculation derives its geometry/load ledger from the model receipt,
then performs three gravity cases and a refined governing case through real OpenSees.

SVG/JSON generation needs no browser. Optionally print the generated HTML at
A3 landscape using Chromium with `--headless --disable-gpu --no-pdf-header-footer`
and `--print-to-pdf='<output.pdf>'` (replace the quoted path). Inspect every page before promoting reader
copies. Source GUIDs, geometry and calculated values must survive caption changes.

The article's three-dimensional overview comes directly from the architectural
IFC using the installed IfcOpenShell geometry engine, including opening
subtractions. Reproduce its SVG and source-GUID review record with:

```sh
.venv/bin/python -m structural_ai.ifc_overview --project project --output 'project/structural/outputs/runs/<task-id>/ifc-overview'
```

Use an unused output directory. Open the SVG in a browser; the article PNG is a
Chromium rendering at its native 1800 × 1200 pixels. Colours and transparency
explain the core without changing the IFC or implying design approval.

## Checks and scope

The immutable received IFC and focused fixtures support deterministic generation
and regression. Do not replace these inputs merely to remove an internal label.
The current `core-review` and interface generators are the drawing path;
`coordinate`, `handoff` and `verify_diagnostics.py` retain different diagnostic
formulations and reject the adopted model. There is one active source tree.

[Validation](validation.md) separates software, numerical, design and publication
gates. Do not rerun the whole building for prose or filenames alone.
Use Git status/history, recorded hashes and explicit path mappings to identify
the inputs and outputs associated with each revision.
