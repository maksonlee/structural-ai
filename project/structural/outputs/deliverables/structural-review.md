# Structural calculation and coordination review

This simulated office has verified **gross elastic diagnostic analysis** and
coordinated review drawings. Full code design, all-member RC, foundations and
construction approval remain incomplete.

## Architect input and structural interpretation

The architect supplies [the core/portal proposal](../../../architect/outputs/architectural-review.pdf).
The structural scheme has 36 columns and 51 main beams, B2/C2, orthogonal
continuous beam lines, a rear 7.50 m bay and a shared stair/lift wall.

The review identifies 10 wall/column and 21 wall/beam-web intersections.
Columns own shared concrete first, then clear-span webs, then remaining wall
strips. Explicit eccentric six-DOF contacts preserve force and moment transfer.
The beam web centre is 0.44 m below structural floor level.

One coordination iteration corrected 4.06848 m3 / 97.64352 kN of duplicated
concrete accounting while retaining the architectural geometry. This is not
physical concrete saved. The remaining 70 mm analytical strip belongs to a
monolithic wall/column union, not a proposed separate thin wall.

[The structural drawings](structural-drawings.pdf) show those interfaces.
[The method](../../../../docs/wall-interface-method.md) and
[drawing manifest](drawing-manifest.json) provide supporting detail.

## Actual diagnostic results

| Variant | Gravity kN | Vertical maximum mm | X100 mm | Y100 mm | First period s |
|---|---:|---:|---:|---:|---:|
| Nominal / repeat | 11878.4091 | 3.048439 | 0.119382 | 0.070572 | 0.182024 |
| 0.50 m mesh | 11878.4091 | 3.074157 | 0.119796 | 0.070485 | 0.182257 |
| Higher synthetic equipment | 11902.7023 | 3.049893 | 0.119382 | 0.070572 | 0.182294 |
| Deeper fixed base | 11960.1586 | 3.066550 | 0.124595 | 0.073640 | 0.186603 |

Five variants each completed 19 static cases and 12 modes through real OpenSees.
Checks include finite response, complete force/moment balance with position terms,
reduced nodal equilibrium, contact compatibility, mass, superposition, modal
properties and eigenpair recovery. IFC schema, geometry and mapping were checked
separately: candidate/extended models have 164/183 products and 17 voids each,
with no schema findings in the recorded audit.

Nominal force/moment residual maxima are 7.96e-8 kN / 2.23e-6 kNm.
Mesh vertical/X/Y response changes are +0.844/+0.347/-0.122 percent.
Twelve modes capture 93.39% X and 81.73% Y free translational mass; code modal
sufficiency is not established. Read the [variant table](analysis-variants.csv),
[numerical checks](analysis-checks.json) and [support reactions](support-reactions.csv).

The results were reproduced through the ordinary CLI with 109 identical nominal
files. [Execution evidence](execution-record.json) preserves actual commands,
versions, checks, failed attempts and their corrections. Recorded solver runs
remain the source of these figures; editorial changes are not new analysis.

## From analysis to reinforcement

[The landing example](landing-strip.md) uses one strip of this building to show
gravity demand, selected Taiwan code checks, bar alternatives and a
[reinforcement sketch](RC-001-landing-strip.pdf). This local illustration does
not complete the full landing, stair, support anchorage or building design.

## Reproduction and boundaries

Tested environment: Ubuntu/Linux x86_64, Python 3.14.4, OpenSeesPy/Linux 3.8.0.0
(engine 3.8.0), IfcOpenShell 0.8.5, NumPy 2.5.3, Shapely 2.1.2 and PyYAML 6.0.3.
[Development instructions](../../../../docs/development.md) give reproducible commands;
use each build's actual emitted path when solving. The
[model receipt](model-adoption.json) binds input identity to verification.

The [Taiwan comparison](../../../comparison/workflow-example.md) separates
selected official requirements, an attributed practitioner account, vendor
features and simulated case assumptions. No ETABS equivalence or measured
productivity saving is claimed.

The 100 kN cases are calibration, not code wind/seismic. Fixed bases are not
foundation design. Gross elastic joints omit cracking, bond slip and local shear
flexibility; released stair transfer omits stair bracing. Complete egress,
code actions, RC/foundations, pricing and construction acceptance remain open.
