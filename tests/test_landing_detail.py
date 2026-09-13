"""Independent statics, real solver, code arithmetic and source-evidence guards."""
import math
import json
from pathlib import Path
import tempfile
import unittest
import yaml

from structural_ai.landing_detail import (
    VERIFICATION_IMPLEMENTATION_FILES, checked_json, load_verification,
    patch_statics, section_check, solve_patch,
)
from structural_ai.provenance import RUNS_RELATIVE, file_hash, write_json


class VerificationSelectionTests(unittest.TestCase):
    """Isolated receipt/manifest fixtures, not simulated solver execution."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        project = self.root/"project"
        files = {
            "structural/inputs/structural.ifc": "isolated adopted geometry\n",
            "structural/inputs/received-scheme.ifc": "isolated received geometry\n",
            "architect/outputs/core-candidate.ifc": "isolated adopted geometry\n",
            "architect/outputs/scheme.yaml": "revision: H02\n",
            "architect/outputs/core-proposal.yaml": "revision: H03-B\n",
            "structural/design/equipment.yaml": "roof: {synthetic_equipment_dead_kN: 20}\n",
        }
        for name, body in files.items():
            path = project/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        config = {"revision": "H03-C", "source_ifc": "structural.ifc", "base": {"elevation_m": -1.8}}
        (project/"structural/inputs/analysis.yaml").write_text(yaml.safe_dump(config))
        doc = {"id": "a01", "inputs": {
            "structural_ifc": "structural/inputs/structural.ifc", "analysis": "structural/inputs/analysis.yaml",
            "architectural_scheme": "architect/outputs/scheme.yaml",
            "received_structural_scheme": "structural/inputs/received-scheme.ifc",
            "equipment_basis": "structural/design/equipment.yaml"},
            "architectural_handoff": {"core_proposal": "architect/outputs/core-proposal.yaml",
                                     "core_candidate_ifc": "architect/outputs/core-candidate.ifc"},
            "compatibility": {"source_ifc_sha256": file_hash(project/"structural/inputs/structural.ifc")}}
        (project/"project.yaml").write_text(yaml.safe_dump(doc))
        for name in VERIFICATION_IMPLEMENTATION_FILES:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("isolated implementation identity: " + name)
        inventory = {p.relative_to(self.root).as_posix(): file_hash(p)
                     for p in self.root.rglob("*") if p.is_file()}
        self.run = self.root/RUNS_RELATIVE/"isolated-new-verification"
        self.run.mkdir(parents=True)
        snapshot = {**config, "source_ifc": "project/architect/outputs/core-candidate.ifc"}
        (self.run/"baseline-build").mkdir()
        (self.run/"baseline-build/candidate-analysis.yaml").write_text(yaml.safe_dump(snapshot))
        (self.run/"baseline-build/candidate-equipment.yaml").write_text(files["structural/design/equipment.yaml"])
        self.model = {"revision": "H03-C", "source_ifc_sha256": doc["compatibility"]["source_ifc_sha256"],
                      "architectural_scheme_sha256": file_hash(project/"architect/outputs/scheme.yaml"),
                      "equipment_basis_sha256": file_hash(self.run/"baseline-build/candidate-equipment.yaml"),
                      "load_cases": {f"case-{i}": {} for i in range(19)}}
        write_json(self.run/"baseline-build/analytical_model.json", self.model)
        write_json(self.run/"baseline-build/stair_transfer.json", {"sources": []})
        write_json(self.run/"baseline-analysis/results/summary.json", {
            "engine": "OpenSeesPy", "version": "fixture", "diagnostic_checks_passed": True,
            "cases": {name: {"return_code": 0, "numerical_checks_passed": True} for name in self.model["load_cases"]},
            "modes": [{"mode": i, "eigenvalue_rad2_s2": float(i)} for i in range(1, 13)]})
        labels = ["candidate-ifc", "connections", "baseline-analysis", "repeat-analysis", "mesh050-analysis",
                  "equipment-high-analysis", "base-deeper-analysis", "repeat-comparison", "mesh050-comparison",
                  "eigenpairs", "generated-ifc"]
        write_json(self.run/"commands.json", {"commands": [{"label": name, "return_code": 0} for name in labels]})
        self.manifest = {"run_id": self.run.name, "task": "candidate-verification", "project": "a01",
                         "layout_version": 2, "status": "COMPLETED_CANDIDATE_DIAGNOSTICS_AWAITING_ADOPTION_REVIEW",
                         "exit_code": 0, "solver_executed": True, "finished_at_utc": "isolated fixture",
                         "command": ["python", "scripts/verify_core_candidate.py", "--project", "project", "--revision", "H03-C"],
                         "input_and_source_sha256": inventory,
                         "output_sha256": {p.relative_to(self.run).as_posix(): file_hash(p)
                                           for p in self.run.rglob("*") if p.is_file()}}
        self.receipt = {"verification_run_id": "absent-historical-run", "verification_manifest_sha256": "0"*64,
                        "verified_model_sha256": file_hash(self.run/"baseline-build/analytical_model.json")}
        self.save_manifest()

    def save_manifest(self):
        write_json(self.run/"manifest.json", self.manifest)

    def replace_record(self, name, record):
        write_json(self.run/name, record)
        self.manifest["output_sha256"][name] = file_hash(self.run/name)
        self.save_manifest()

    def test_fresh_run_needs_no_historical_folder_and_allows_prose_changes(self):
        (self.root/"docs").mkdir()
        (self.root/"docs/notes.md").write_text("New article explanation, same engineering inputs.")
        run, model, _, _ = load_verification(self.root, self.receipt, self.run)
        self.assertEqual(run, self.run)
        self.assertEqual(model, self.model)
        self.assertFalse((self.root/RUNS_RELATIVE/self.receipt["verification_run_id"]).exists())

    def test_default_and_explicit_retained_run_keep_exact_receipt_guard(self):
        receipt = {**self.receipt, "verification_run_id": self.run.name,
                   "verification_manifest_sha256": file_hash(self.run/"manifest.json")}
        self.assertEqual(load_verification(self.root, receipt), load_verification(self.root, receipt, self.run))
        self.manifest["finished_at_utc"] = "changed"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Changed evidence"):
            load_verification(self.root, receipt)

    def test_missing_or_outside_run_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            load_verification(self.root, self.receipt, self.run.parent/"missing")
        with self.assertRaises(ValueError):
            load_verification(self.root, self.receipt, self.root/"outside")

    def test_changed_engineering_inputs_and_implementation_are_rejected(self):
        for name in ("project/structural/inputs/analysis.yaml", "project/architect/outputs/scheme.yaml",
                     "project/architect/outputs/core-proposal.yaml", "project/structural/design/equipment.yaml",
                     "src/structural_ai/model_builder.py", "scripts/verify_core_candidate.py"):
            with self.subTest(path=name):
                path = self.root/name
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n# changed\n")
                    with self.assertRaises(ValueError):
                        load_verification(self.root, self.receipt, self.run)
                finally:
                    path.write_bytes(original)

    def test_tampered_or_missing_output_is_rejected(self):
        path = self.run/"baseline-build/stair_transfer.json"
        path.write_text('{"sources": ["changed"]}')
        with self.assertRaisesRegex(ValueError, "Changed verification output"):
            load_verification(self.root, self.receipt, self.run)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            load_verification(self.root, self.receipt, self.run)

    def test_rehashed_different_model_does_not_replace_adopted_identity(self):
        self.replace_record("baseline-build/analytical_model.json", {**self.model, "base_elevation_m": -2.1})
        with self.assertRaisesRegex(ValueError, "model differs"):
            load_verification(self.root, self.receipt, self.run)

    def test_incomplete_or_failed_manifest_and_commands_are_rejected(self):
        for key, value in (("status", "RUNNING"), ("exit_code", 1), ("solver_executed", False)):
            with self.subTest(field=key):
                original = self.manifest[key]
                self.manifest[key] = value
                self.save_manifest()
                with self.assertRaisesRegex(ValueError, "completed successful"):
                    load_verification(self.root, self.receipt, self.run)
                self.manifest[key] = original
        self.replace_record("commands.json", {"commands": []})
        with self.assertRaisesRegex(ValueError, "commands are incomplete"):
            load_verification(self.root, self.receipt, self.run)

    def test_contradictory_case_failure_is_rejected_even_with_top_level_pass(self):
        name = "baseline-analysis/results/summary.json"
        summary = json.loads((self.run/name).read_text())
        summary["cases"]["case-0"]["return_code"] = 1
        self.replace_record(name, summary)
        with self.assertRaisesRegex(ValueError, "baseline analysis is incomplete"):
            load_verification(self.root, self.receipt, self.run)


class LandingTests(unittest.TestCase):
    def test_asymmetric_patch_hand_equilibrium(self):
        # 2 kN/m on x=1..3 in a 6 m span: W=4 at x=2, RB=4/3.
        answer = patch_statics(6, 1, 3, 2)
        self.assertAlmostEqual(answer["reactions_kN"][0], 8/3)
        self.assertAlmostEqual(answer["reactions_kN"][1], 4/3)
        self.assertAlmostEqual(answer["peak_x_m"], 7/3)
        self.assertAlmostEqual(answer["moment_kNm"], 40/9)

    def test_real_backend_patch_and_mesh(self):
        # No skip/fallback: optional backend must be installed to verify this stage.
        for n in (2, 8):
            answer = solve_patch(6, 1, 3, 2, 25e6, .18, n)
            self.assertEqual(answer["solver"], "OpenSees")
            self.assertAlmostEqual(answer["peak"]["M_kNm"], 40/9, places=7)
            self.assertAlmostEqual(answer["reactions_kN"][1]*6, 8, places=7)

    def test_real_backend_full_udl_deflection_and_sign(self):
        answer = solve_patch(4, 0, 4, 3, 25e6, .2)
        expected_mm = -5*3*4**4/(384*25e6*(.2**3/12))*1000
        self.assertAlmostEqual(answer["midspan_vertical_mm"], expected_mm, places=8)
        self.assertAlmostEqual(answer["peak"]["M_kNm"], 6, places=8)
        self.assertAlmostEqual(answer["max_abs_shear_kN"], 6, places=8)

    def test_code_section_independent_hand_values(self):
        # Construct As=400 and d=160 mm: a=120/17 mm; phi Mn=23.65835294.
        bar = {"diameter_mm": 10, "area_mm2": 80, "mass_kg_m": .63}
        result = section_check(28, 420, 185, 20, 20, bar, 200, 15, 17)
        self.assertAlmostEqual(result["effective_depth_mm"], 160)
        self.assertAlmostEqual(result["stress_block_a_mm"], 120/17)
        self.assertAlmostEqual(result["phi_Mn_kNm_m"], 23.65835294117647)
        self.assertAlmostEqual(result["minimum_steel_mm2_m"], 333)
        # Vc with Taiwan's 0.68, rho=.0025, lambda_s=1, then phi=.75.
        self.assertAlmostEqual(result["phi_Vc_kN_m"], 58.60245957792363, places=6)
        self.assertTrue(result["selected_checks_passed"])

    def test_minimum_steel_can_control_even_with_flexural_capacity(self):
        bar = {"diameter_mm": 9.53, "area_mm2": 71.33, "mass_kg_m": .56}
        result = section_check(28, 420, 180, 20, 20, bar, 250, 14.23, 16.84)
        self.assertEqual(result["checks"]["positive_flexure"]["status"], "PASS_SCOPED")
        self.assertEqual(result["checks"]["minimum_flexural_steel"]["status"], "FAIL")
        self.assertFalse(result["selected_checks_passed"])

    def test_invalid_patch_and_changed_materials_rejected(self):
        for args in [(6, -1, 3, 2), (6, 1, 8, 2), (6, 1, 3, math.nan), (6, 1, 3, 0)]:
            with self.assertRaises(ValueError): patch_statics(*args)
        with self.assertRaises(ValueError):
            section_check(35, 420, 180, 20, 20, {"diameter_mm": 10, "area_mm2": 80}, 200, 10, 10)

    def test_modified_retained_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"evidence.json"
            path.write_text('{"verified": true}')
            digest = file_hash(path)
            self.assertTrue(checked_json(path, digest)["verified"])
            path.write_text('{"verified": false}')
            with self.assertRaises(ValueError): checked_json(path, digest)
