# Case design decisions

These are the choices needed to understand and reproduce the article's building.

| Topic | Adopted choice and reason | Remaining work |
|---|---|---|
| Building | Simulated three-storey RC office, about 18 x 12 m, no basement, Taipei Datong/Jianming | Actual surveyed/site inputs do not exist |
| Frame | Regular grid, B2/C2 columns, orthogonal continuous main beams and rear 7.50 m bay | Final member/system checks |
| Core | Shared stair/elevator wall; real slab/opening voids; portal clear of B2 | Complete egress, products and equipment coordination |
| Authority | Architect requirements/core specification and the adopted structural IFC have named owners in project.yaml | Any changed input requires coordinated downstream review |
| Structural model | Gross elastic frames/shells and explicit eccentric wall/frame contacts | Cracking, seismic/wind criteria and final joint design |
| Concrete ownership | Count shared column/web/wall concrete once while retaining physical geometry | No physical saving is implied |
| Diagnostic loads | Gravity, modal and 100 kN X/Y calibration, plus stated sensitivities | Calibration is not code earthquake/wind |
| Foundations | -1.80 m fixed base is a diagnostic assumption | Ground basis and foundation design |
| Landing example | One-metre strip of STL-1F-MID using source geometry and the released load ledger | Whole-landing, flights, continuity and anchorage |
| Reinforcement illustration | Synthetic indoor cover 20 mm, aggregate 20 mm; existing fc28/fy420; D10@200 selected | Supplier grade, detailing and serviceability |
| Cost/construction | Compare quantities and identify placement/interface constraints | No priced saving or contractor acceptance |

The landing's D10@250 option fails minimum steel; D13@300 passes the selected
checks with more steel area. These are scoped alternatives, not a lowest-cost
or complete construction solution.

The article follows requirements -> proposal -> structural interpretation ->
calculation -> coordination -> a drawing example. Filenames describe these work
products. Readers need no development history or internal revision codes.
The actual numerical results, sources and unfinished scope stay identifiable.

The article can be complete while engineering gates remain open. Its text is
maintained in WordPress, with the owner-authorized original figures uploaded
alongside the draft. The repository contains the companion engineering files.
WordPress publication, public repository release and project-wide licensing
remain separate decisions.
