# Architectural input, structural calculation and coordination

This stage takes the architectural candidate through a structural interface
correction, whole-building verification and controlled adoption review. The
physical main frame and candidate core remain unchanged. Five verified variants,
ordinary CLI reproduction and four reviewed sheets now support the scoped
diagnostic analysis. The [structural response](../structural/outputs/deliverables/structural-review.md)
and [effort record](effort.csv) preserve results and limits; a completed
solver process alone is insufficient.

| Work product | Attributable Taiwan evidence | A01 implementation and decisions | Limit and improvement opportunity |
|---|---|---|---|
| Architectural revision and structural response | NTU 2022 interview sections 2-3 describe interpreting architectural drawings, structural alternatives and drawing responsibilities. | Simulated structural role preserves the candidate, resolves wall/frame interfaces and returns source-linked review sheets. AI assists source research, implementation and review. | No external architect or practitioner acceptance. Complete route, rated-product and WC/MEP coordination is still needed. |
| Analysis assumptions and checks | Current official concrete-code 6.3/6.9 requires rational, consistent modelling and purpose-appropriate verification. | Ownership partition, explicit eccentric contacts, corrected web centroid, actual OpenSees tests and whole-building variants. | Gross elastic diagnostics do not establish code actions, cracked response or RC capacity. Automation should expose assumptions and review gates. |
| Connection/detail coordination | The same practitioner account discusses interface questions and the division of calculation/drafting work. Structural regulations 375-2/375-3 address modelling, force transfer and construction feasibility. | Contact mapping and force pairs are inspectable; two structural interface sheets accompany the architectural core review. | No bars, development/laps or congestion checks are complete. Joint forces are analysis output, not a reinforcement detail. |
| Quantities and revision control | Earlier registered tool/firm evidence documents existing CAD/BIM, analysis and detailing automation; those claims retain their original scope. | Correct duplicate concrete accounting and trace downstream loads, mass, reactions and drawings. | The corrected 4.06848 m3 is duplicated accounting removed, not physical savings. Full rebar/formwork quantities and prices are absent. |

Sources actually reviewed on 2026-09-13:

- Ministry of the Interior / NLMA, **建築物混凝土結構設計規範**, revision
  2023-08-10, effective 2024-01-01, errata 2024-02-19. Selected clauses
  6.3.1.1, 6.3.1.3 and 6.9.1-6.9.5, printed 6-4/6-5/6-18, inform this
  verification method. [Official edition listing](https://www.nlma.gov.tw/ch/legislation/regsearch/6874),
  [current PDF](https://www.nlma.gov.tw/uploads/files/011d9249cac7d6c5547786aa348e352a.pdf),
  [errata page 1](https://www.nlma.gov.tw/uploads/files/40e4370d2726960efcc41074b2d99f53.pdf).
  Selected text was read; main-PDF screenshot requests timed out. No full code
  review, member check or figure-based verification is claimed.
- Ministry of the Interior, **建築技術規則建築構造編**, Articles 375-2/375-3,
  [NLMA consolidated text](https://www.nlma.gov.tw/ch/legislation/regsearch/6174)
  and [MOJ Article 375-3](https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=D0070116&flno=375-3).
  Retrieved MOJ text displays a 2026-05-29 cutoff; individual amendment dates
  are not established. MOJ Article 375-2 retrieval failed; NLMA text was read.
  These provisions do not approve the selected software or A01 joint assumptions.
- Huang Zi-Huan / 黃子桓, interview with Yang Xun-Hong / 楊巽閎 of Jian-Ju / 建巨,
  NTU Du Feng issue 173 (2022), [sections 2-3](https://www.ntuce-newsletter.tw/archives/11896).
  This is one published practice account, not a nationwide SOP, interview
  conducted by this project or current review-trigger authority.
- OpenSeesPy upstream [rigidLink](https://openseespydoc.readthedocs.io/en/latest/src/rigidLink.html)
  and [Transformation](https://openseespydoc.readthedocs.io/en/latest/src/TransformationMethod.html)
  documentation, undated, displayed version 3.5.1.3. The command and constraint
  restrictions were reviewed and tested against installed OpenSees 3.8.0.
  This is tool-method evidence, not Taiwanese practice or physical-joint approval.

The comparison credits analysis/result-processing and local detailing automation
already documented in the source register. No ETABS run, numerical equivalence,
industry timing, savings percentage or national adoption of OpenSees is asserted.

Actual checks and rework are traceable in the
[execution record](../structural/outputs/deliverables/execution-record.json).
The reader follows a coordination cycle within this project; technical run
identifiers are not additional design stages. Process elapsed
times belong in the effort CSV, separated into generation, solver waiting,
verification and rework. Active setup, research, development, debugging and design
labour remain unmeasured, as does industry effort; unknown is not zero. Nested
command times must not be added together as labour or project duration.

The article explains the wider code/design/drawing workflow while identifying
unfinished member/joint reinforcement, foundations, costing and construction
review. Completing every later engineering stage is not required for the
introductory article; no later gate is closed by this iteration.
