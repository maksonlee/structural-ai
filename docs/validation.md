# Verification and its limits

The case includes actual OpenSees verification for diagnostic analysis and a
scoped landing reinforcement illustration. It does not establish complete
building code compliance or construction acceptance.

The tests cover source authority, IFC regeneration and GUID preservation, known
OpenSees answers for frames/shells/offsets/mass, released stair transfer,
eccentric constraints, wall/frame ownership and load first moments. The building
verification additionally checks finite results, global force and position-moment
equilibrium, reduced nodal equilibrium, mass, modes, repeatability and mesh/load/base
sensitivity. Exact values and execution evidence are in the
[structural report](../project/structural/outputs/deliverables/structural-review.md).

The [landing example](../project/structural/outputs/deliverables/landing-strip.md)
checks asymmetric-patch statics, signed local forces, elastic deflection and
selected code arithmetic. Its real-backend tests use no solver skip or fallback.
These checks do not validate complete landing plate action or anchorage.

Actual failures and their fixes remain in execution evidence. Skipped or
unperformed checks are never reported as passed. Software verification, local
member checks, article readiness, full design and professional approval are
separate states.

## Diagnostic analysis method

Use the whole-building verifier in [development](development.md), which selects
the adopted adapter and executes five variants with 19 static cases and 12 modes
each. Actual commands, elapsed process times, logs and source hashes are recorded;
no custom stiffness solver or substituted reference result is used.

The [released-strip basis](../project/structural/design/stair-load-method.md),
[interface method](wall-interface-method.md) and
[reviewed results](../project/structural/outputs/deliverables/structural-review.md)
define the scope. Force and position moments must be consistent between meshes
so load-location changes are not mistaken for stiffness sensitivity. Diagnostic
cases do not provide a complete code action/combination envelope.

## Independent known solutions

`tests/test_opensees.py` exercises the production adapter's `build` function with
the real backend. Mechanics use kN, m and s; rotation is radians.

* A 4 m cantilever with unequal Iy and Iz is oriented along global X, Y and Z.
  Under a tip force, axial extension is PL/(EA); transverse tip displacement is
  PL³/(3EI). Both local bending axes and signed local end shears are checked.
  Tip torque produces TL/(GJ). G=E/[2(1+nu)]. These follow by integrating
  axial strain, Euler-Bernoulli curvature and Saint-Venant twist, respectively.
* A -0.35 m global Z offset at both ends adds moment eP at the member centroid
  under nodal axial loading. The reference node's axial displacement is
  PL/(EA)+Pe²L/(EIy). Global moment balance includes the nodal positions.
* A cantilever with a single transverse tip mass and massless rotation has
  lambda=(3EI/L³)/m. A tiny two-free-DOF LAPACK eigenproblem checks this value
  and 100% directional participation. Whole-building eigenanalysis uses ARPACK.
* A rectangular shell in horizontal and vertical planes under constant in-plane
  traction has axial extension PL/(Ebt), free Poisson contraction and N11=P/b.
  These tests verify orientation and native membrane-resultant ordering/sign.
* An all-edge simply supported square shell under uniform pressure is compared
  with the independently evaluated Navier series:
  w(center)=16qa⁴/(pi⁶D) sum[sin(m*pi/2)sin(n*pi/2)/(mn(m²+n²)²)],
  for positive odd m,n, D=Et³/[12(1-nu²)]. Summing through 79 and using
  t/a=0.005 makes thin-plate theory appropriate. The 16x16 error must be below
  2% and lower than the 8x8 error. This is an analytical plate check, not a
  calibration against inherited A01 displacements.

Frame tests use relative errors near 1e-8; shell patch tests use 1e-8. These are
numerical tolerances for these simple exact solutions, not Taiwan code limits.
Skipped mechanics tests mean NOT VERIFIED. Import or native solver failures
remain failures; no fallback exists.

## Whole-model checks

Every static case exports displacements, all restrained-node reactions, local frame
end actions and shell Gauss-point section resultants, retaining source GUIDs.
Global moments are sum(M+r cross F) about the model origin, including all
support positions and applied nodal couples. Independently assembled sums of
element global resisting forces minus loads and support reactions check every
nodal DOF. The diagnostic tolerance is 1e-7 times total applied force, with a
model-position length scale for moments. Results must be finite.

Modes export all nodal vectors and native `modalProperties`. Translational
effective masses are independently recomputed as (phi' M r)²/(phi' M phi), using
only free-DOF diagonal nodal masses, and compared with native output. Normalized
mass orthogonality must have maximum error below 1e-6. `check_modes.py` reloads
every saved eigenvector and solves K*u=lambda*M*phi using OpenSees statics; the
relative displacement difference must be below 1e-7. No second solver is claimed.

`check_analysis.py` checks service superposition, the weight/mass ledger, and
repeated analysis. A separate 0.50 m mesh build preserves the source/settings
and records its mesh override. Compare gravity/lateral maximum displacement and
the first three periods against the adopted 0.75 m mesh with a 5% screening
tolerance chosen before the sensitivity run. This is global diagnostic
sensitivity only. Peak local shell/connection forces, contact load distribution,
cracked stiffness and foundation sensitivity require later engineering work.

## Result conventions and boundaries

`elasticBeamColumn` outputs local node-I and node-J resisting actions in the
order N,Vy,Vz,T,My,Mz; they are **end actions**, not a continuous signed moment
diagram. Recover section-cut design conventions explicitly before using them.
The adapter projects `local_y` normal to the member axis and passes x cross y
as `vecxz`; both offsets are global vectors. The wall/frame model includes explicit rigid contact/joint zones described in
the interface method. Frames have zero distributed mass because the case supplies
all mass nodally. Shell section density is also zero to prevent double counting.

For these rectangular shells, local 1 follows node 1 to 2; local 2 lies in the
plane toward node 4 and local 3 is their cross product. Floors have +Z normals;
walls have +X or -Y normals. `stresses` returns four groups of eight **section
resultants**, not concrete stresses: N11,N22,N12 (kN/m), M11,M22,M12 (kNm/m),
Q1,Q2 (kN/m). Values retain native OpenSees bending/shear signs; no reinforcement
design sign conversion or through-thickness stress recovery is asserted.
The model JSON `drilling_penalty` is unused by ShellMITC4; its internal
formulation controls drilling stiffness. It must not be reported as a user-set
OpenSees stiffness parameter.

`audit_ifc.py` independently tessellates all scoped physical objects with
IfcOpenShell, compares gross bounds/volumes to the subset reader, checks Boolean
void subtraction, and executes available EXPRESS rules. A completed audit command
does not mean zero schema findings. Neither schema nor geometry checks prove a
reinforced load path or stair/equipment compliance.

Upstream references actually reviewed 2026-09-13: [frame arguments](https://openseespydoc.readthedocs.io/en/latest/src/elasticBeamColumn.html),
[global offsets and axes](https://openseespydoc.readthedocs.io/en/latest/src/LinearTransf.html),
[ShellMITC4](https://openseespydoc.readthedocs.io/en/latest/src/ShellMITC4.html),
[v3.8.0 shell response implementation](https://github.com/OpenSees/OpenSees/blob/v3.8.0/SRC/element/shell/ShellMITC4.cpp),
[modal properties](https://openseespydoc.readthedocs.io/en/latest/src/modalProperties.html),
[eigenproblem and ARPACK limitations](https://opensees.github.io/OpenSeesDocumentation/user/manual/analysis/eigen.html),
[IfcOpenShell geometry](https://docs.ifcopenshell.org/ifcopenshell-python/geometry_processing.html)
and [validation API](https://docs.ifcopenshell.org/autoapi/ifcopenshell/validate/index.html).

## Presentation changes

For presentation/path changes, check references and YAML, protect numerical
inputs/results, repeat the affected generators, compare non-text SVG geometry
and verify hash provenance. Run the applicable repository tests and full suite;
do not rerun the whole building solely for changed captions.
