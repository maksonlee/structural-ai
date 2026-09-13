"""Small run recorder. Never stores hostnames, usernames, environment variables or credentials."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from importlib import metadata
from pathlib import Path
import json
import os
import platform
import subprocess
import uuid

RUNS_RELATIVE = Path("project/structural/outputs/runs")
# Historical manifests remain byte-for-byte evidence of the pre-move commands.
LEGACY_INPUT_PATHS = {
    "project/structural/inputs/structural.ifc": "projects/a01/inputs/structural.ifc",
    "project/structural/inputs/analysis.yaml": "projects/a01/inputs/analysis.yaml",
}


def verify_build_inputs(root: Path, parent: dict, inputs: tuple[Path, ...]) -> None:
    recorded = parent.get("input_and_source_sha256", {})
    for path in inputs:
        key = path.relative_to(root).as_posix()
        keys = [key]
        if parent.get("layout_version", 1) == 1 and key in LEGACY_INPUT_PATHS:
            keys.append(LEGACY_INPUT_PATHS[key])
        hashes = [recorded[k] for k in keys if k in recorded]
        if not hashes or any(value != file_hash(path) for value in hashes):
            raise ValueError("Inputs changed after model generation. Rebuild before solving.")


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git_state(root: Path) -> dict:
    def git(*args: str) -> str:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return proc.stdout.strip()
    try:
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "note": "No committed Git history available"}


def inventory(root: Path) -> dict:
    selected = []
    for folder in ("src", "project", "tests", "scripts", "docs"):
        p = root / folder
        if p.exists():
            for directory, dirs, files in os.walk(p):
                directory = Path(directory)
                dirs[:] = [name for name in dirs if name != "__pycache__"
                           and not name.endswith(".egg-info")
                           and directory / name != root / RUNS_RELATIVE]
                selected.extend(directory / name for name in files if not name.endswith(".pyc"))
    for name in ("pyproject.toml", "AGENTS.md"):
        if (root / name).is_file():
            selected.append(root / name)
    return {p.relative_to(root).as_posix(): file_hash(p) for p in sorted(set(selected))}


def make_run(root: Path, project_id: str, task: str) -> tuple[Path, dict]:
    # The case ID is metadata; this checkout has one project and one run location.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{task}-{uuid.uuid4().hex[:8]}"
    path = root / RUNS_RELATIVE / run_id
    path.mkdir(parents=True, exist_ok=False)
    versions = {}
    for name in ("numpy", "shapely", "PyYAML", "openseespy", "openseespylinux", "ifcopenshell"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    manifest = {
        "run_id": run_id, "task": task, "project": project_id, "layout_version": 2,
        "started_at_utc": utc_now(), "status": "RUNNING", "git": git_state(root),
        "python": platform.python_version(), "dependencies": versions,
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "libc": list(platform.libc_ver())},
        "input_and_source_sha256": inventory(root), "solver_executed": False,
        "engineering_approval": False, "construction_release": "BLOCKED",
    }
    write_json(path / "manifest.json", manifest)
    return path, manifest


def finish_run(path: Path, manifest: dict, status: str, **details) -> None:
    manifest.update(details)
    manifest.update({"status": status, "finished_at_utc": utc_now()})
    manifest["output_sha256"] = {
        p.relative_to(path).as_posix(): file_hash(p)
        for p in sorted(path.rglob("*")) if p.is_file() and p.name != "manifest.json"
    }
    write_json(path / "manifest.json", manifest)
