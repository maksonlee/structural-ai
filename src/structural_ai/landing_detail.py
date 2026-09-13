"""A01 article example: an existing landing's released gravity strip, not full stair design."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import yaml
from shapely.geometry import Polygon, box

from structural_ai.coordination import Sheet, read_geometry
from structural_ai.provenance import RUNS_RELATIVE, file_hash, verify_build_inputs


# Files used by the whole-building verifier, rather than unrelated prose/figures.
VERIFICATION_IMPLEMENTATION_FILES = (
    "src/structural_ai/cli.py", "src/structural_ai/provenance.py",
    "src/structural_ai/model_builder.py", "src/structural_ai/ifc_reader.py",
    "src/structural_ai/core_revision.py", "src/structural_ai/core_review.py",
    "src/structural_ai/coordination.py", "src/structural_ai/core_loads.py",
    "src/structural_ai/stair_transfer.py", "src/structural_ai/rectilinear.py",
    "src/structural_ai/wall_interfaces.py", "src/structural_ai/joint_constraints.py",
    "src/structural_ai/opensees_runner.py", "scripts/verify_core_candidate.py",
    "scripts/audit_ifc.py", "scripts/audit_wall_interfaces.py",
    "scripts/check_analysis.py", "scripts/check_modes.py", "pyproject.toml",
)
LANDING_EVIDENCE_FILES = (
    "baseline-build/analytical_model.json", "baseline-build/stair_transfer.json",
    "baseline-analysis/results/summary.json",
)


def checked_json(path: Path, digest: str) -> dict:
    if file_hash(path) != digest:
        raise ValueError("Changed evidence: " + path.name)
    return json.loads(path.read_text())


def load_verification(root: Path, receipt: dict, verification: Path | None = None):
    """Select unchanged retained evidence or a fresh verification of the adopted model."""
    root = root.resolve()
    selected = verification is not None
    verification = ((root/RUNS_RELATIVE/receipt["verification_run_id"])
                    if verification is None else verification.resolve())
    if verification.parent != root/RUNS_RELATIVE:
        raise ValueError("Use a verification run directly under the project's runs directory")
    manifest_path = verification/"manifest.json"
    retained = file_hash(manifest_path) == receipt["verification_manifest_sha256"]
    if not selected or retained:
        manifest = checked_json(manifest_path, receipt["verification_manifest_sha256"])
    else:
        manifest = json.loads(manifest_path.read_text())
    if manifest.get("run_id") != verification.name:
        raise ValueError("Verification directory differs from its recorded run ID")

    if selected and not retained:
        from structural_ai.cli import load_project
        directory, project, source, config_path, _ = load_project(root/"project")
        if (manifest.get("task") != "candidate-verification" or manifest.get("layout_version") != 2
                or manifest.get("project") != project["id"]
                or manifest.get("status") != "COMPLETED_CANDIDATE_DIAGNOSTICS_AWAITING_ADOPTION_REVIEW"
                or manifest.get("exit_code") != 0 or manifest.get("solver_executed") is not True
                or not manifest.get("finished_at_utc")
                or manifest.get("command") != ["python", "scripts/verify_core_candidate.py",
                                               "--project", "project", "--revision", "H03-C"]):
            raise ValueError("A completed successful H03-C whole-building verification is required")
        inputs = [root/"project/project.yaml", source, config_path]
        inputs += [directory/project["inputs"][key] for key in
                   ("architectural_scheme", "received_structural_scheme", "equipment_basis")]
        inputs += [directory/project["architectural_handoff"][key] for key in
                   ("core_proposal", "core_candidate_ifc")]
        inputs += [root/name for name in VERIFICATION_IMPLEMENTATION_FILES]
        verify_build_inputs(root, manifest, tuple(inputs))
        for name, digest in manifest["output_sha256"].items():
            path = (verification/name).resolve()
            if not path.is_relative_to(verification) or file_hash(path) != digest:
                raise ValueError("Changed verification output: " + name)
        required = (*LANDING_EVIDENCE_FILES, "commands.json",
                    "baseline-build/candidate-analysis.yaml", "baseline-build/candidate-equipment.yaml")
        if not all(name in manifest["output_sha256"] for name in required):
            raise ValueError("Verification lacks required landing evidence")
        commands = json.loads((verification/"commands.json").read_text())["commands"]
        expected = {"candidate-ifc", "connections", "baseline-analysis", "repeat-analysis",
                    "mesh050-analysis", "equipment-high-analysis", "base-deeper-analysis",
                    "repeat-comparison", "mesh050-comparison", "eigenpairs", "generated-ifc"}
        if (len(commands) != len(expected) or {c["label"] for c in commands} != expected
                or any(c.get("return_code") != 0 for c in commands)):
            raise ValueError("Whole-building verification commands are incomplete or failed")
        config = yaml.safe_load(config_path.read_text())
        snapshot = yaml.safe_load((verification/"baseline-build/candidate-analysis.yaml").read_text())
        candidate = directory/project["architectural_handoff"]["core_candidate_ifc"]
        if snapshot.get("source_ifc") != candidate.relative_to(root).as_posix():
            raise ValueError("Verification configuration uses a different candidate")
        snapshot["source_ifc"] = config["source_ifc"]  # Same bound IFC, different source path.
        if snapshot != config or config.get("revision") != "H03-C":
            raise ValueError("Verification configuration differs from the adopted analysis")
        equipment_path = directory/project["inputs"]["equipment_basis"]
        equipment_snapshot = verification/"baseline-build/candidate-equipment.yaml"
        if yaml.safe_load(equipment_snapshot.read_text()) != yaml.safe_load(equipment_path.read_text()):
            raise ValueError("Verification equipment differs from the current load authority")
        if file_hash(verification/LANDING_EVIDENCE_FILES[0]) != receipt["verified_model_sha256"]:
            raise ValueError("Verification model differs from the reviewed adopted model")

    model, ledger, summary = [checked_json(verification/name, manifest["output_sha256"][name])
                              for name in LANDING_EVIDENCE_FILES]
    if selected and not retained:
        scheme = directory/project["inputs"]["architectural_scheme"]
        if (model.get("revision") != "H03-C" or model.get("source_ifc_sha256") != file_hash(source)
                or model.get("architectural_scheme_sha256") != file_hash(scheme)
                or model.get("equipment_basis_sha256") != file_hash(equipment_snapshot)):
            raise ValueError("Verification model source, architecture or equipment identity differs")
        if (summary.get("engine") != "OpenSeesPy" or not summary.get("version")
                or summary.get("diagnostic_checks_passed") is not True
                or len(model.get("load_cases", {})) != 19
                or set(summary.get("cases", {})) != set(model["load_cases"])
                or any(case.get("return_code") != 0 or case.get("numerical_checks_passed") is not True
                       for case in summary["cases"].values())
                or [mode.get("mode") for mode in summary.get("modes", [])] != list(range(1, 13))
                or any(not math.isfinite(mode["eigenvalue_rad2_s2"]) or mode["eigenvalue_rad2_s2"] <= 0
                       for mode in summary["modes"])):
            raise ValueError("Verification baseline analysis is incomplete")
    return verification, model, ledger, summary


def patch_statics(span: float, start: float, end: float, q: float) -> dict:
    """Independent equilibrium and integration of a downward uniform patch (kN, m)."""
    if not all(math.isfinite(v) for v in (span, start, end, q)) or not (0 <= start < end <= span and q > 0):
        raise ValueError("Expected a positive finite load patch within a positive span")
    weight = q * (end-start)
    right = weight * (start+end) / (2*span)
    left = weight-right
    peak = start+left/q
    return {"reactions_kN": [left, right], "peak_x_m": peak,
            "moment_kNm": left*peak-q*(peak-start)**2/2}


def solve_patch(span, start, end, q, elastic_modulus, thickness, subdivisions=2):
    """Real 2D OpenSees beam: local x right, y up, positive section moment sagging."""
    import openseespy.opensees as ops
    exact = patch_statics(span, start, end, q)
    if elastic_modulus <= 0 or thickness <= 0 or subdivisions < 2:
        raise ValueError("Invalid section or mesh")
    points = sorted(set([0., start, span/2, end, span] +
                        np.linspace(start, end, subdivisions+1).tolist()))
    try:
        ops.wipe()
        ops.model("basic", "-ndm", 2, "-ndf", 3)
        for n, x in enumerate(points, 1):
            ops.node(n, x, 0.)
        ops.fix(1, 1, 1, 0)
        ops.fix(len(points), 0, 1, 0)
        ops.geomTransf("Linear", 1)
        for n in range(1, len(points)):
            ops.element("elasticBeamColumn", n, n, n+1,
                        thickness, elastic_modulus, thickness**3/12, 1)
        ops.timeSeries("Linear", 1)
        ops.pattern("Plain", 1, 1)
        for n, (a, b) in enumerate(zip(points, points[1:]), 1):
            if start <= (a+b)/2 <= end:
                ops.eleLoad("-ele", n, "-type", "-beamUniform", -q, 0.)
        ops.system("BandGeneral")
        ops.numberer("RCM")
        ops.constraints("Plain")
        ops.integrator("LoadControl", 1.)
        ops.algorithm("Linear")
        ops.analysis("Static")
        code = ops.analyze(1)
        if code:
            raise RuntimeError(f"OpenSees returned {code}; no fallback")
        ops.reactions()
        reactions = [ops.nodeReaction(n, 2) for n in (1, len(points))]
        elements, stations = [], []
        for n, (a, b) in enumerate(zip(points, points[1:]), 1):
            force = list(ops.eleResponse(n, "localForce"))
            load = q if start <= (a+b)/2 <= end else 0.
            offsets = [0., b-a]
            if load and 0 < force[1]/load < b-a:
                offsets.append(force[1]/load)
            for s in offsets:
                stations.append({"x_m": a+s, "V_kN": force[1]-load*s,
                                 "M_kNm": -force[2]+force[1]*s-load*s*s/2})
            elements.append({"id": n, "x_m": [a, b], "local_force_kN_kNm": force})
        peak = max(stations, key=lambda s: s["M_kNm"])
        residuals = [sum(reactions)-q*(end-start),
                     reactions[1]*span-q*(end-start)*(start+end)/2]
        displacement = ops.nodeDisp(points.index(span/2)+1, 2)*1000
        values = [*reactions, *residuals, displacement, peak["M_kNm"]]
        values += [v for e in elements for v in e["local_force_kN_kNm"]]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Nonfinite OpenSees result")
        np.testing.assert_allclose(reactions, exact["reactions_kN"], rtol=1e-8, atol=1e-8)
        np.testing.assert_allclose(residuals, 0., rtol=0, atol=1e-7)
        np.testing.assert_allclose(peak["M_kNm"], exact["moment_kNm"], rtol=1e-8, atol=1e-8)
        return {"solver": "OpenSees", "version": ops.version(), "return_code": code,
                "q_kN_m": q, "reactions_kN": reactions, "peak": peak,
                "max_abs_shear_kN": max(abs(s["V_kN"]) for s in stations),
                "midspan_vertical_mm": displacement, "elements": elements,
                "force_moment_residual_kN_kNm": residuals, "closed_form": exact,
                "numerical_checks_passed": True}
    finally:
        ops.wipe()


def section_check(fc, fy, h, cover, aggregate, bar, spacing, moment, shear):
    """Selected Taiwan 2024 provisions, MPa/mm/N internally; restricted A01 materials."""
    if fc != 28 or fy != 420 or cover != 20:
        raise ValueError("Review code applicability before changing the scoped material/exposure basis")
    if min(h, aggregate, spacing, bar["diameter_mm"], bar["area_mm2"]) <= 0 or min(moment, shear) < 0:
        raise ValueError("Invalid section demand or dimension")
    d = h-cover-bar["diameter_mm"]/2
    steel = bar["area_mm2"]*1000/spacing
    a = steel*fy/(.85*fc*1000)
    c = a/.85  # Table 22.2.2.4.3, fc = 28 MPa.
    strain = .003*(d-c)/c
    # 21.2.2.1 explicitly permits epsilon_ty = .002 for fy = 420 MPa.
    if strain < .005:
        raise ValueError("Example requires a tension-controlled section; redesign explicitly")
    capacity = .9*steel*fy*(d-a/2)/1e6
    rho = steel/(1000*d)
    size_factor = min(1., math.sqrt(2/(1+d/250)))
    # Table 22.5.5.1(c): Taiwan coefficient 0.68; normal-weight, Nu = 0, Av = 0.
    vc = min(.68*size_factor*rho**(1/3)*math.sqrt(fc), .42*math.sqrt(fc))*1000*d/1000
    min_steel = .0018*1000*h
    # fs = 2/3 fy per 24.3.2.1; cc is clear cover to the nearest tension bar.
    crack_spacing = min(380*(280/(2*fy/3))-2.5*cover, 300*(280/(2*fy/3)))
    checks = {
        "positive_flexure": (moment <= capacity, "21.2.2; 22.2.2.4", moment, capacity, "kNm/m"),
        "one_way_shear": (shear <= .75*vc, "21.2.1; 22.5.5.1(c); 7.6.3.1", shear, .75*vc, "kN/m"),
        "minimum_flexural_steel": (steel >= min_steel, "7.6.1.1", steel, min_steel, "mm2/m"),
        "transverse_distribution_steel": (steel >= min_steel, "7.7.6.1; 24.4.3.2", steel, min_steel, "mm2/m"),
        "main_spacing": (spacing <= min(3*h, 450, crack_spacing), "7.7.2.3; 24.3.2", spacing, min(3*h, 450, crack_spacing), "mm"),
        "transverse_spacing": (spacing <= min(5*h, 450), "24.4.3.3", spacing, min(5*h, 450), "mm"),
        "clear_spacing": (spacing-bar["diameter_mm"] >= max(25, bar["diameter_mm"], 4*aggregate/3), "25.2.1", spacing-bar["diameter_mm"], max(25, bar["diameter_mm"], 4*aggregate/3), "mm"),
        "interior_cover": (cover >= 20, "20.5.1.3.1", cover, 20, "mm"),
    }
    return {"effective_depth_mm": d, "steel_mm2_m": steel, "minimum_steel_mm2_m": min_steel,
            "stress_block_a_mm": a, "neutral_axis_c_mm": c, "tension_strain": strain,
            "phi_flexure": .9, "phi_Mn_kNm_m": capacity, "phi_Vc_kN_m": .75*vc,
            "ideal_two_direction_grid_kg_m2": 2*bar["mass_kg_m"]*1000/spacing,
            "checks": {name: {"status": "PASS_SCOPED" if ok else "FAIL", "clause": clause,
                               "value": value, "limit": limit, "units": units}
                       for name, (ok, clause, value, limit, units) in checks.items()},
            "selected_checks_passed": all(item[0] for item in checks.values())}


def calculate(root: Path, verification: Path | None = None) -> dict:
    root = root.resolve()
    basis_path = root/"project/structural/design/landing-strip.yaml"
    basis = yaml.safe_load(basis_path.read_text())
    receipt_path = root/"project/structural/outputs/deliverables/model-adoption.json"
    receipt = json.loads(receipt_path.read_text())
    for name in ("project/structural/inputs/structural.ifc", "project/structural/inputs/analysis.yaml", "project/project.yaml"):
        if file_hash(root/name) != receipt["after_sha256"][name]:
            raise ValueError("Adopted input changed; review converter and local design: " + name)
    verification, model, ledger, summary = load_verification(root, receipt, verification)
    if not summary["diagnostic_checks_passed"]:
        raise ValueError("Parent whole-building diagnostics incomplete")
    source = root/"project/structural/inputs/structural.ifc"
    scheme = root/"project/architect/outputs/scheme.yaml"
    if model["source_ifc_sha256"] != file_hash(source) or model["architectural_scheme_sha256"] != file_hash(scheme):
        raise ValueError("Model source or architectural load authority changed")
    config = yaml.safe_load((root/"project/structural/inputs/analysis.yaml").read_text())
    _, objects, geometry, _, _, _ = read_geometry(source)  # IfcOpenShell independently measures solids.
    obj = objects[basis["source_name"]]
    if obj["guid"] != basis["source_guid"]:
        raise ValueError("Landing source identity changed")
    item = next(s for s in ledger["sources"] if s["source_guid"] == obj["guid"])
    polygon = Polygon(geometry[basis["source_name"]]["profile"])
    x0, x1 = obj["min"][0], obj["max"][0]
    y0, y1 = basis["strip_y_m"]
    band = box(x0, y0, x1, y1)
    if not polygon.covers(band) or not math.isclose(y1-y0, 1., abs_tol=1e-9):
        raise ValueError("Example requires a complete one-metre strip inside the source footprint")
    for name, flight in objects.items():
        if name.startswith("STF-1F-") and band.intersects(box(*flight["min"][:2], *flight["max"][:2])):
            raise ValueError("Selected band intersects a flight bearing region")
    np.testing.assert_allclose(obj["gross_m3"], item["measure"]["owned_volume_m3"], atol=1e-9)
    np.testing.assert_allclose(polygon.area, item["horizontal_loaded_area_m2"], atol=1e-9)
    supports = sorted(r["xyz_m"][0] for r in item["components"][0]["support_reactions"])
    if len(supports) != 2:
        raise ValueError("Review changed released-strip supports")
    loads = {}
    for component in item["components"]:
        np.testing.assert_allclose(sorted(r["xyz_m"][0] for r in component["support_reactions"]), supports)
        loads[component["case"]] = component["weight_kN"]/polygon.area
    h = obj["max"][2]-obj["min"][2]
    materials = model["materials"]
    np.testing.assert_allclose(loads["D_SELF"], h*materials["unit_weight_kN_m3"], atol=1e-9)
    np.testing.assert_allclose(loads["L_STAIRS"], config["loads"]["stairs_kN_m2"], atol=1e-9)
    span, start, end = supports[1]-supports[0], x0-supports[0], x1-supports[0]
    dead, live = loads["D_SELF"]+loads["D_SUPER"], loads["L_STAIRS"]
    # Table 5.3.1(a,b), selected direct indoor gravity subset; no global code envelope.
    cases = {"SERVICE": dead+live, "U1_1.4D": 1.4*dead, "U2_1.2D_1.6L": 1.2*dead+1.6*live}
    results = {name: solve_patch(span, start, end, q, materials["E_kN_m2"], h) for name, q in cases.items()}
    governing = max(results, key=lambda name: results[name]["peak"]["M_kNm"])
    demand = results[governing]
    fine = solve_patch(span, start, end, cases[governing], materials["E_kN_m2"], h, 8)
    np.testing.assert_allclose([fine["peak"]["M_kNm"], fine["midspan_vertical_mm"]],
                               [demand["peak"]["M_kNm"], demand["midspan_vertical_mm"]], rtol=1e-8, atol=1e-8)
    alternatives = []
    for option in basis["alternatives"]:
        check = section_check(materials["concrete_fc_MPa"], materials["rebar_fy_MPa"], h*1000,
                              basis["cover_mm"], basis["maximum_aggregate_mm"], basis["bars"][option["bar"]],
                              option["spacing_mm"], demand["peak"]["M_kNm"], demand["max_abs_shear_kN"])
        alternatives.append({**option, **check})
    selected = next(a for a in alternatives if all(a[k] == v for k, v in basis["selected"].items()))
    if not selected["selected_checks_passed"]:
        raise ValueError("Selected reinforcement fails scoped checks")
    input_paths = [basis_path, receipt_path, source, scheme, root/"project/structural/inputs/analysis.yaml",
                   *(verification/p for p in LANDING_EVIDENCE_FILES), verification/"manifest.json", Path(__file__)]
    return {"status": "SCOPED_GRAVITY_STRIP_DEMONSTRATION", "source_name": obj["name"],
            "source_guid": obj["guid"], "basis": basis, "materials": materials,
            "geometry": {"profile_xy_m": list(polygon.exterior.coords), "strip_y_m": [y0, y1],
                         "support_x_m": supports, "loaded_x_m": [x0, x1], "span_m": span,
                         "thickness_m": h, "top_z_m": obj["max"][2]},
            "loads_kN_m2": loads, "cases": results, "governing_combination": governing,
            "combination_clause": "Table 5.3.1(a,b), printed p. 5-1, indoor direct gravity only",
            "mesh_sensitivity": {"fine": fine, "passed": True}, "alternatives": alternatives,
            "selected": selected, "input_sha256": {p.relative_to(root).as_posix(): file_hash(p) for p in input_paths},
            "unperformed_checks": [{"scope": s, "status": "NOT_CHECKED"} for s in basis["not_checked"]],
            "full_landing_design_complete": False, "construction_release": "BLOCKED"}


def draw(result: dict, path: Path):
    """One original A3 article figure; deliberately leaves support details unresolved."""
    g, s = result["geometry"], result["selected"]
    bar_note = f"{s['bar']} @ {s['spacing_mm']}"
    demand = result["cases"][result["governing_combination"]]
    digest = result["input_sha256"]["project/structural/inputs/structural.ifc"]
    sheet = Sheet("RC-001", "Stair landing: loads to a reinforcement sketch", digest, "CASE STUDY", result["source_name"])
    sheet.text(14, 35, "LOCAL GRAVITY STRIP ONLY | no whole-landing, anchorage or seismic acceptance", 3.2, "#aa3a20")
    sheet.text(18, 49, "1  LOCATE THE STRIP / PLAN / 1:25 AT A3", 3.4)
    tr = lambda x, y: (30+(x-6.245)*40, 139-(y-9.67)*40)
    sheet.shape(Polygon(g["profile_xy_m"]), tr, "#eef3f4", "#365a69", guid=result["source_guid"])
    sheet.shape(box(*[g["loaded_x_m"][0], g["strip_y_m"][0], g["loaded_x_m"][1], g["strip_y_m"][1]]),
                tr, "#e1efe7", "#287457")
    for y in np.arange(g["strip_y_m"][0]+.1, g["strip_y_m"][1], s["spacing_mm"]/1000):
        sheet.line(*tr(6.5, y), *tr(9.12, y), "#ae3858", .55)
    for x in g["support_x_m"]:
        sheet.line(*tr(x, 9.65), *tr(x, 11.6), "#aa3a20", .3, "1,1")
    sheet.text(18, 152, "Green: y = 10.20..11.20 m; main bottom bars run along X.", 2.8)
    sheet.text(18, 159, "Slab top +2.00 m; h = 180 mm; footprint follows the source IFC.", 2.8)
    sheet.text(18, 166, "Band excludes flight bearings; adjacent plate action is not checked.", 2.6)
    sheet.text(18, 181, "2  RELEASED LOCAL MODEL / DIAGRAMMATIC", 3.4)
    sheet.line(30, 202, 155, 202, "#365a69", .7)
    for x in (30, 155):
        sheet.line(x, 202, x-3, 208); sheet.line(x, 202, x+3, 208); sheet.line(x-3, 208, x+3, 208)
    for x in range(37, 153, 10):
        sheet.line(x, 190, x, 200, "#365a69", .3)
        sheet.line(x, 200, x-1.2, 197, "#365a69", .3)
    sheet.text(30, 217, f"Support-line span {g['span_m']:.2f} m; loaded length 2.88 m", 2.8)
    sheet.text(30, 225, f"1.2D + 1.6L: q = {demand['q_kN_m']:.3f} kN/m", 2.8)
    sheet.text(18, 237, "Inherited nominal wall reaction lines x = 6.245 / 9.375 m.", 2.7)
    sheet.text(18, 244, "Pin/roller idealization; unloaded 0.125 m end zones.", 2.7)
    sheet.text(18, 252, "No new gravity is added to the whole-building model.", 2.7)
    sheet.text(218, 49, "3  SECTION AND SELECTED CHECKS", 3.4)
    sheet.rect(224, 61, 170, 22, "#eef3f4", "#365a69")
    sheet.line(234, 79, 384, 79, "#ae3858", .8)
    for x in range(240, 383, 12):
        sheet.rect(x, 76, 1.1, 1.1, "#287457", "#287457")
    sheet.text(224, 93, "Midspan section sketch; h 180 / cover 20 mm (not to scale)", 2.65)
    sheet.text(224, 101, f"Magenta: bottom main {bar_note}; green: transverse above.", 2.65)
    lines = [f"Concrete fc = 28 MPa; steel fy = 420 MPa (case assumption)",
             f"Effective depth d = {s['effective_depth_mm']:.2f} mm",
             f"Demand Mu = {demand['peak']['M_kNm']:.2f} kNm/m",
             f"Provided phi Mn = {s['phi_Mn_kNm_m']:.2f} kNm/m",
             f"As = {s['steel_mm2_m']:.2f} >= {s['minimum_steel_mm2_m']:.0f} mm2/m minimum",
             f"Vu = {demand['max_abs_shear_kN']:.2f} <= phi Vc = {s['phi_Vc_kN_m']:.2f} kN/m",
             "Selected gravity strength, minimum steel and spacing: PASS",
             "D10 @ 250 fails minimum steel; D13 @ 300 uses more steel."]
    for i, line in enumerate(lines): sheet.text(218, 114+i*8, line, 2.85)
    sheet.rect(218, 181, 181, 38, "#fff1e9", "#c67652")
    for i, line in enumerate(["SUPPORT / END DETAILS: HOLD", "Anchorage, continuity, integrity steel and cut lengths are unresolved.",
                              "Lines stop schematically; they are NOT proposed bar terminations.", f"{bar_note} also used for transverse distribution in this strip."]):
        sheet.text(223, 189+i*8, line, 2.5, "#943d26")
    sheet.text(218, 232, "Taiwan concrete code effective 2024-01-01, with 2024 errata.", 2.65)
    sheet.text(218, 240, "Tables 5.3.1 / 21.2.2 / 22.5.5.1; sections 7.6 / 7.7 / 24 / 25.", 2.65)
    sheet.text(218, 250, "Read landing-strip.md / .json for the exact scope, inputs and checks.", 2.65)
    sheet.text(18, 267, "SOURCE GUID: "+result["source_guid"]+" | Article illustration within A01; NOT a complete stair reinforcement sheet.", 2.8)
    sheet.write(path)
