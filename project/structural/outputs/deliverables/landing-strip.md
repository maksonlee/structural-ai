# RC-001: landing strip, calculation to drawing

**Scoped article example, 2026-09-13.** [PDF](RC-001-landing-strip.pdf),
[vector sheet](RC-001-landing-strip.svg), [calculation and coverage](landing-strip.json).
This is one strip of the existing A01 building, not a complete landing design.

## Inputs and load path

The building's IFC element `STL-1F-MID`, GUID
`3WBnbFw6v18ePpRsZLm4Gj`, has an L-shaped 4.6831 m2 footprint and is 180 mm thick.
The chosen strip is x=6.37..9.25, y=10.20..11.20 m, top z=2.00 m. IfcOpenShell
independently measures its volume; the strip lies wholly inside the footprint
and outside both first-floor flight bounding/bearing regions.

The verified whole-building stair-transfer ledger supplies gravity intensities
and nominal reaction lines x=6.245/9.375 m. Use that same **released local strip**
idealization: pin/roller, span 3.13 m, distributed load over 2.88 m and unloaded
0.125 m elastic end zones. These nominal lines are not the owned-wall mesh
midplanes; the existing building transfer separately preserves eccentric forces.
No global model, source geometry or existing load is changed or counted twice.
No global frame-end force is presented as a complete slab/beam section demand.

| Input | Value | Authority |
|---|---:|---|
| Concrete / steel strength | 28 / 420 MPa | Existing analysis.yaml; synthetic case materials |
| Elastic modulus / concrete unit weight | 25 GPa / 24 kN/m3 | Existing analysis.yaml |
| Self-weight | 4.320 kN/m2 | IFC thickness x unit weight; agrees with retained ledger |
| Finish allowance | 1.500 kN/m2 | Architectural scheme through retained ledger |
| Stair live load | 2.941995 kN/m2 | Existing private-office assumption; global action envelope open |
| Clear cover / maximum aggregate | 20 / 20 mm | New synthetic indoor exposure/detailing assumptions |
| D10 diameter / area | 9.53 mm / 71.33 mm2 | Attributed bar-size table; not a nominal 10 mm circle |

Only new selections are stored in [landing-strip.yaml](../../design/landing-strip.yaml).
Receipt and manifest checks reject changed geometry, configuration, architect
scheme or numerical evidence before reusing this calculation. D10 uses the
existing case fy=420 MPa; supplier grade certification has not been obtained.

## Calculation and selected checks

Use direct indoor gravity combinations 1.4D and 1.2D+1.6L from Table 5.3.1(a,b).
The latter governs: q=11.691192 kN/m, each reaction=16.83531648 kN,
Mu=14.22584243 kNm/m at midspan x=7.81 m. For an independently integrated
symmetric patch, Mu=q*l*(2L-l)/8. Real OpenSees 3.8.0 reproduces that value;
positive section bending is sagging. The 2D element local-force order is
Ni, Vyi, Mzi, Nj, Vyj, Mzj; internal left moment is minus Mzi.

For selected D10@200 in each direction: As=356.65 mm2/m; bottom main-bar
d=155.235 mm; a=As*fy/(0.85*fc*b)=6.293824 mm; beta1=0.85;
epsilon_t=0.059895. This exceeds the permitted fy420 tension-control threshold
0.002+0.003; phi=0.90. Thus phi*Mn=20.50356 kNm/m.

| Check | Result / limit | Current code locator, printed page | Coverage |
|---|---|---|---|
| Positive flexure | 14.22584 <= 20.50356 kNm/m | 21.2.2, 22.2.2.1/.4; 21-2/3, 22-2/3 | PASS_SCOPED |
| Minimum main / transverse steel | 356.65 >= 324 mm2/m | 7.6.1.1, 7.7.6.1, 24.4.3.2; 7-4/8, 24-9 | PASS_SCOPED |
| One-way shear | 16.83532 <= 55.27851 kN/m | Table 21.2.1; 22.5.5.1(c)/.1/.3; 7.6.3.1; 21-1, 22-8/9, 7-4 | PASS_SCOPED |
| Main / transverse maximum spacing | 200 <= 300 / 450 mm | 7.7.2.3, Table 24.3.2, 24.3.2.1, 24.4.3.3; 7-6, 24-7/9 | PASS_SCOPED |
| Clear spacing | 190.47 >= 26.67 mm | 25.2.1; 25-1 | PASS_SCOPED |
| Indoor cover | 20 >= 20 mm | Table 20.5.1.3.1; 20-14; errata PDF p.14 | PASS_SCOPED |

Shear uses the Taiwan **0.68** coefficient, normal-weight lambda=1, Nu=0,
rho=As/(b*d), lambda_s=min(1,sqrt(2/(1+d/250))), phi=0.75 and the 0.42*sqrt(fc)
cap. The full support reaction bounds this strip's shear demand. Vu<phi*Vc,
so 7.6.3.1 does not trigger minimum shear reinforcement for this solid slab.
Crack-control spacing uses the permitted fs=2fy/3 estimate, not a completed
cracked/long-term serviceability analysis. All reported capacities require
the assumed reinforcement to be developed; anchorage remains unresolved.

| Trial grid, both directions | Steel per direction, mm2/m | Ideal grid mass, kg/m2 | Selected checks |
|---|---:|---:|---|
| D10@250 | 285.32 | 4.48 | FAIL minimum steel despite adequate flexure |
| D10@200 | 356.65 | 5.60 | PASS_SCOPED; selected |
| D13@300 | 422.33 | 6.63 | PASS_SCOPED |

Mass is an infinite-grid quantity index without laps, anchorage, waste, edge
rounding or prices. Selection is not a minimum-cost or buildability verdict.
Drawing endpoints are schematic: no hook, embedment or fabrication length is
invented. Whole-landing plate action, adjacent flight loads, negative moments,
continuity, seismic effects, anchorage, integrity steel, fire resistance and full
serviceability are **NOT_CHECKED**. The existing global released model omits stair
stiffness; this local example does not resolve that limitation.

## Sources and Taiwan comparison

The Ministry of the Interior's **建築物混凝土結構設計規範** was amended
2023-08-10, effective 2024-01-01, with 2024-02-19 errata. The official listing,
selected clauses above and relevant cover errata were reviewed on 2026-09-13.
[Official listing](https://www.nlma.gov.tw/ch/legislation/regsearch/6874),
[code PDF](https://www.nlma.gov.tw/uploads/files/011d9249cac7d6c5547786aa348e352a.pdf),
[errata](https://www.nlma.gov.tw/uploads/files/40e4370d2726960efcc41074b2d99f53.pdf).

Huang Zi-Huan's 2022 NTU interview with Yang Xun-Hong describes the architectural
input, analysis, calculation/drawing and review sequence, including drafting
roles: [sections 2-3](https://www.ntuce-newsletter.tw/archives/11896). It is one
attributed practitioner account. Taipei Civil Engineers Association Information
Committee's undated [104 reinforcement notes](https://sites.google.com/view/rcbim/%E5%9C%96%E8%A1%A8%E8%88%87%E6%A8%A1%E5%9E%8B/rc01-%E4%B8%80%E8%88%AC%E8%AA%AA%E6%98%8E/104-%E9%8B%BC%E7%AD%8B)
show grade/size/detail information as a drawing work product. Their sample D10
grade default differs from our synthetic fy420 assumption and is not imported.
Supplier [祺峰鋼鐵 size table](https://www.cf168.com.tw/specifications.php), undated,
supports dimensions and theoretical unit mass only; both pages accessed 2026-09-13.

AI assisted the source review, scoped model, option comparison and consistent
annotations. OpenSees performed the numerical solve. Existing ETABS/local
detailing automation remains credited in [the comparison](../../../comparison/README.md).
This is not a paired software comparison, measured labour saving or professional
approval. Full source metadata remains in [the register](../../../../docs/sources.yaml).

## Execution and reproduction

Ubuntu Linux x86_64, isolated `.venv`, Python 3.14.4; OpenSeesPy and
openseespylinux 3.8.0.0, engine 3.8.0; IfcOpenShell 0.8.5. No new dependency.
Use repository-root commands, under the documented host resource wrapper:

```sh
.venv/bin/python scripts/design_landing_strip.py --output project/structural/outputs/runs/landing-example
.venv/bin/python -m unittest discover -s tests -p test_landing_detail.py -v
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m structural_ai validate --project project
```

Choose an unused output directory. The script reads the retained adopted
verification via its receipt; SVG and JSON are reproducible without Chromium or
an AI account. Optional PDF printing follows [development](../../../../docs/development.md).
The exact executed arguments, return codes, versions, input/output hashes,
stdout/stderr, reproduction and review outcomes are in
[landing-article-execution.json](landing-article-execution.json) and its task run.

Final verification: **74 tests passed, zero skipped**, in 17.911 s; project
validation passed. Three local gravity cases and the refined governing case
returned zero. Maximum signed force/moment residual is 4.04e-12 kN/kNm;
refinement changes Mu by 3.86e-13 kNm and midspan displacement by 1.56e-14 mm.
Gross elastic service displacement is -0.89435 mm, not a complete deflection
acceptance check. JSON and SVG reproduce byte-for-byte; the SVG used for the
visually reviewed one-page PDF/PNG matches the final generation exactly.

Preserved failures: the first narrow suite caught a mistyped independent shear
answer (58.60195 versus independently recomputed 58.60245958 kN); only that test
value changed. The first full suite found the checklist referenced the reviewed
JSON before its copy step; promotion order was corrected. No solver failure,
fallback, altered engineering assumption or relaxed tolerance was hidden.
