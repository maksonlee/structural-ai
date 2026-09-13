"""Repository-local commands. Build and solver execution are separate, recorded stages."""
from __future__ import annotations
import argparse
import contextlib
import importlib.util
import json
import re
import subprocess
import sys
import traceback
from pathlib import Path
import yaml
from .provenance import RUNS_RELATIVE, file_hash, make_run, finish_run, write_json, verify_build_inputs


def repository_root(start: Path) -> Path:
    start = start.resolve()
    for p in (start, *start.parents):
        if (p / "pyproject.toml").is_file() and (p / "project" / "project.yaml").is_file():
            return p
    raise ValueError("Run inside a structural-ai checkout, or specify --project inside it.")


def load_project(directory: Path) -> tuple[Path, dict, Path, Path, Path]:
    directory = directory.resolve()
    root = repository_root(directory)
    pfile = directory / "project.yaml"
    doc = yaml.safe_load(pfile.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not re.fullmatch(r"[a-z0-9_-]+", str(doc.get("id", ""))):
        raise ValueError("project.yaml requires a safe lower-case project id.")
    def inside(relative: str) -> Path:
        p = (directory / relative).resolve()
        if not p.is_relative_to(directory):
            raise ValueError("Project input paths must remain inside the project folder.")
        if not p.is_file():
            raise FileNotFoundError(p)
        return p
    source = inside(doc["inputs"]["structural_ifc"])
    cfgpath = inside(doc["inputs"]["analysis"])
    cfg = yaml.safe_load(cfgpath.read_text(encoding="utf-8"))
    if (cfgpath.parent / cfg["source_ifc"]).resolve() != source:
        raise ValueError("project.yaml and analysis.yaml disagree on the authoritative IFC.")
    if file_hash(source) != doc["compatibility"]["source_ifc_sha256"]:
        raise ValueError("IFC changed. Audit the A01-specific converter before updating its compatibility hash; do not simply bypass this guard.")
    return directory, doc, source, cfgpath, root


def validate(directory: Path) -> dict:
    from .ifc_reader import Model
    directory, project, source, cfgpath, root = load_project(directory)
    model = Model(source)
    expected = project["compatibility"]["physical_counts"]
    counts = {key: len(model.by_type(key)) for key in expected}
    if counts != expected:
        raise ValueError(f"Unexpected source-object counts: {counts}")
    cfg = yaml.safe_load(cfgpath.read_text(encoding="utf-8"))
    architectural_scheme(directory, project)
    if cfg.get('revision')=='H03-C':
        received_scheme(directory,project)
        if equipment_basis(directory,project) is None:
            raise ValueError('H03-C requires an authoritative equipment basis')
    if cfg["base"]["elevation_m"] >= 0 or cfg["mesh"]["target_size_m"] <= 0:
        raise ValueError("The adopted A01 trial requires a negative base and positive mesh size.")
    return {"status": "PASS_SCOPED_INPUT_CHECKS_ONLY", "physical_counts": counts,
            "full_ifc_schema_validation": False, "solver_executed": False,
            "project_complete": False, "engineering_approval": False}


def architectural_scheme(directory: Path, project: dict) -> Path:
    path = (directory / project['inputs']['architectural_scheme']).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError('Architectural scheme must be an existing input inside the project')
    scheme = yaml.safe_load(path.read_text())
    if scheme.get('revision') != 'H02':
        raise ValueError('Review H02 architecture-to-load converter before adopting a new scheme')
    return path


def received_scheme(directory: Path, project: dict) -> Path:
    """Immutable received geometry used to regenerate the architectural revision."""
    path=(directory/project['inputs'].get('received_structural_scheme',project['inputs']['structural_ifc'])).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError('Received scheme must remain inside the project')
    expected=project['compatibility'].get('received_source_sha256',project['compatibility']['source_ifc_sha256'])
    if file_hash(path)!=expected:
        raise ValueError('Immutable received scheme changed; source regeneration requires review')
    return path


def equipment_basis(directory: Path, project: dict) -> Path | None:
    relative=project['inputs'].get('equipment_basis')
    if relative is None:
        return None
    path=(directory/relative).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError('Equipment basis must be an existing input inside the project')
    return path


def build_project(directory: Path, mesh_size: float | None = None) -> Path:
    from .model_builder import create
    directory, project, source, cfgpath, root = load_project(directory)
    run, manifest = make_run(root, project["id"], "build")
    manifest["command"] = ["structural-ai", "build", "--project", directory.relative_to(root).as_posix()]
    if mesh_size is not None:
        manifest["command"] += ["--mesh-size", str(mesh_size)]
        manifest["diagnostic_overrides"] = {"mesh_size_m": mesh_size}
    try:
        check = validate(directory)
        write_json(run / "input_checks.json", check)
        with (run / "build.log").open("w", encoding="utf-8") as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                create(source, cfgpath, run, mesh_size=mesh_size,
                       architect_scheme=architectural_scheme(directory, project),
                       equipment_basis=equipment_basis(directory, project))
        finish_run(run, manifest, "COMPLETED_GEOMETRY_AND_ANALYSIS_INPUTS_ONLY")
    except Exception:
        (run / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        finish_run(run, manifest, "FAILED")
        raise
    return run


def analyze_project(directory: Path, model_path: Path, case: str, modes: int) -> Path:
    directory, project, source, cfgpath, root = load_project(directory)
    model_path = model_path.resolve()
    allowed = (root / RUNS_RELATIVE).resolve()
    if not model_path.is_relative_to(allowed) or model_path.name != "analytical_model.json":
        raise ValueError(f"Use analytical_model.json from a recorded build under {RUNS_RELATIVE.as_posix()}/.")
    if modes < 0:
        raise ValueError("--modes must be nonnegative.")
    parent_manifest_path = model_path.parent / "manifest.json"
    parent = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    if parent.get("task") != "build" or parent.get("status") != "COMPLETED_GEOMETRY_AND_ANALYSIS_INPUTS_ONLY":
        raise ValueError("The parent build did not complete successfully.")
    recorded = parent.get("output_sha256", {}).get("analytical_model.json")
    if file_hash(model_path) != recorded:
        raise ValueError("Analytical model differs from its recorded build. Rebuild it.")
    # Prevent comparing newly edited inputs to stale generated analysis data.
    inputs=(source,cfgpath,architectural_scheme(directory,project))
    equipment=equipment_basis(directory,project)
    if equipment is not None:inputs+= (equipment,)
    verify_build_inputs(root,parent,inputs)
    run, manifest = make_run(root, project["id"], "opensees")
    manifest["parent_build"] = parent["run_id"]
    manifest["analytical_model_sha256"] = file_hash(model_path)
    manifest["solver_attempted"] = False
    manifest["command"] = ["python", "-m", "structural_ai.opensees_runner", "--model", model_path.relative_to(root).as_posix(),
                           "--output", (run / "results").relative_to(root).as_posix(), "--case", case, "--modes", str(modes)]
    try:
        if importlib.util.find_spec("openseespy") is None:
            message = "OpenSeesPy is not installed. No fallback solver was used. See docs/development.md."
            (run / "stderr.log").write_text(message + "\n", encoding="utf-8")
            finish_run(run, manifest, "BLOCKED_MISSING_OPENSEES", exit_code=2)
            raise RuntimeError(message + f" Run record: {run}")
        command = [sys.executable, "-m", "structural_ai.opensees_runner", "--model", str(model_path),
                   "--output", str(run / "results"), "--case", case, "--modes", str(modes)]
        manifest["solver_attempted"] = True
        with (run / "stdout.log").open("w", encoding="utf-8") as stdout, (run / "stderr.log").open("w", encoding="utf-8") as stderr:
            proc = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False)
        if proc.returncode:
            finish_run(run, manifest, "FAILED_OPENSEES_PROCESS", exit_code=proc.returncode)
            raise RuntimeError(f"OpenSees process failed with exit code {proc.returncode}; see {run}")
        result = json.loads((run / "results" / "summary.json").read_text(encoding="utf-8"))
        if result.get("engine") != "OpenSeesPy" or not result.get("version"):
            raise RuntimeError("A successful process did not supply an identifiable OpenSees result.")
        expected_cases = json.loads(model_path.read_text())["load_cases"]
        requested = set(expected_cases) if case == "all" else {case}
        if (set(result.get("cases", {})) != requested or len(result.get("modes", [])) != modes
                or result.get("diagnostic_checks_passed") is not True):
            raise RuntimeError("Solver output did not complete the requested diagnostic checks.")
        finish_run(run, manifest, "SOLVER_COMPLETED_NOT_DESIGN_APPROVAL", exit_code=0,
                   solver_executed=True, solver_version=result["version"], diagnostic_checks_passed=True,
                   independent_numerical_validation=False)
    except BaseException:
        # Keep specific failure states rather than converting every error to success.
        if manifest["status"] == "RUNNING":
            (run / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
            finish_run(run, manifest, "FAILED")
        raise
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A01 structural-design workflow; research only.")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("validate", "build", "analyze", "coordinate", "handoff", "core-review"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--project", type=Path, default=Path("project"))
        if name == "build":
            cmd.add_argument("--mesh-size", type=float, help="Recorded diagnostic mesh override in metres; does not edit case inputs")
        if name in ("analyze", "handoff"):
            cmd.add_argument("--model", type=Path, required=True)
        if name == "analyze":
            cmd.add_argument("--case", default="SERVICE_ILLUSTRATION")
            cmd.add_argument("--modes", type=int, default=6)
    args = parser.parse_args(argv)
    try:
        if args.action == "validate":
            print(json.dumps(validate(args.project), indent=2))
        elif args.action == "build":
            print(build_project(args.project, args.mesh_size))
        elif args.action == "coordinate":
            from .coordination import coordinate_project
            print(coordinate_project(args.project))
        elif args.action == "handoff":
            from .handoff import handoff_project
            print(handoff_project(args.project, args.model))
        elif args.action == "core-review":
            from .core_review import core_review_project
            print(core_review_project(args.project))
        else:
            print(analyze_project(args.project, args.model, args.case, args.modes))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
