# Wall/frame interface method and verification scope

The structural role represents intersecting concrete, transfers forces and
carries the architectural layout and explicit loads into whole-building diagnostics. Adoption status and the exact solved identities
belong in the current-work record and dated response, not in this method document.

## Physical ownership and analytical representation

Columns own their gross concrete. Clear-span beam webs own the part below the
slab flange. Wall shells represent the remaining wall concrete, after openings
and those frame intersections. Floor self-weight excludes column/wall footprints.
The independent audit subtracts horizontal polygon unions in layers and compares
volume and all three first moments against actual shell sections and nodes; the
builder instead partitions intervals normal to each wall. IfcOpenShell separately
checks the physical IFC bounds, volumes, void subtraction and schema.

The west wall is x=6.12..6.37 m. At B2/B3 the column extends to x=6.30 m, leaving
a 0.07 m analytical strip at x=6.335 m. This strip is part of the monolithic
wall-column union, not a proposed separate 70 mm wall. The source 0.40 x 0.70 m
beam and 0.18 m slab give a 0.52 m web; its centre is 0.44 m below SSL. Using the full beam's 0.35 m centroid offset would miss the web/flange split. Source section guards reject
a changed frame section before reusing these case-specific properties.

Physical wall midplane extents are retained. Eccentric rigid contacts connect
abutting corners, owned wall strips, overlapping column/beam cross-sections and
column/floor regions. Contact groups have one unconstrained master and no chains,
duplicate slaves or fixed retained/constrained nodes. Groups on the diagnostic
base use direct fixity. The builder limits group dimensions; beam-depth groups
containing several column stations are explicit rigid joint zones.

This is an elastic frame/shell idealization, not a three-dimensional constitutive
model of the concrete union. Floor shells retain their membrane/bending
representation at the reference surface. Removing duplicated self-weight does
not establish every local slab/wall stiffness interaction or section-cut demand.
Rigid cross-sections suppress local deformation, including transverse Poisson
strain in the patch benchmark. Bond slip, panel-zone shear flexibility, cracking,
joint confinement and reinforcement remain unverified for design.

## Eccentric compatibility, signs and inertia

For offset r from master to slave, the small-rotation constraint is
u_slave = u_master + theta_master cross r, with equal rotations. Its 6 x 6
transformation T transfers forces by virtual work: F_master = T-transpose F_slave,
including r cross force. This uses the actual OpenSees `rigidLink beam` and
`Transformation` backend; the repository does not assemble a new global solver.

The raw slave residual q = element resisting force - external load - support
reaction is the joint action on that slave. The master receives -T-transpose q.
Numerical equilibrium reduces the residual to the master and clears the slave;
it does not pretend the unaccounted slave force is a solver error. Per-case joint
action CSVs retain both positions and all six force/couple components. Global
equilibrium still includes every position cross force term. Constraint
compatibility is checked separately, component by component.

Mass remains on actual nodes. Eccentric mass condensation follows the same
kinematics. The real-backend benchmark compares six eigenvalues against a
closed-form Euler-Bernoulli tip stiffness with transformed mass, checks eigenvector
compatibility and compares participation with OpenSees modalProperties. The
separate axial frame/wall patch tests nu=0 and 0.2 with its explicitly constrained
transverse strain; expected wall modulus is E/(1-nu squared), not E.

## Loads, repeatability and refinement

Stair gravity and mass use source-derived released strips. Receiving interpolation
must identify an existing owned wall cell and its actual midplane. Missing cells
or a point outside the receiving envelope fail; a hole is never bridged by a
fallback four-node rectangle. Stairs have no global stiffness in this diagnostic.

The 100 kN X/Y cases retain their diagnostic height fractions but use uniform net
source-floor area instead of mesh-dependent nodal mass. They are not code wind
or earthquake actions. Full force and position moments must remain unchanged
between the 0.75 and 0.50 m meshes. Pressure/patch integration uses orthogonal
regions and bilinear first-moment transfer.

Node/contact coordinates retain the precision of the receiving stations.
The independent 9.80665 kN patch-at-(3.0,7.8) regression checks load first moments;
all 19 mesh resultants are checked within an absolute 1e-7 tolerance.
Actual verification failures and fixes are recorded in the execution evidence.

Whole-building verification uses nominal, exact repeat, finer mesh, higher
synthetic equipment and a deeper diagnostic base. It checks finite response,
global force/moment equilibrium, reduced nodal equilibrium, joint compatibility,
mass, service superposition, modes and eigenpair recovery. The 5% global
displacement/first-three-period refinement screen is a project verification
criterion, not a Taiwan code limit or proof of local force convergence.

## Requirements and limits

Selected **建築物混凝土結構設計規範** 6.3.1.1/6.3.1.3 and 6.9.1-6.9.5
inform consistent assumptions, section changes, suitable FE methods, result
verification and drawing-to-analysis consistency. The 2023-08-10 revision is
effective 2024-01-01, with 2024-02-19 errata. Clause 6.9.3 concerns separate
inelastic combination analyses; this model is linear. Clause 6.9.5's 10% dimension
criterion is not this project's mesh tolerance. No construction drawing check or
full code compliance is claimed. Exact locators and access limits are recorded
in `sources.yaml`, `h03_c_reviews`.

The next design basis must select current code actions/combinations, effective
stiffness and second-order treatment before member design. Signed frame/shell
forces, section cuts, diaphragm/collector actions and local joint demand require
review. Synthetic lift/roof assumptions, diagnostic fixed bases and gross elastic
periods cannot establish foundations, equipment anchorage, priced quantities or
construction feasibility.
