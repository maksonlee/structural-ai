# Reports, results and drawings

Start with [the structural review](structural-review.md),
[structural drawings](structural-drawings.pdf), and the
[landing reinforcement example](landing-strip.md).

| File | Contents |
|---|---|
| `wall-column-detail.svg`, `beam-wall-detail.svg` | Editable vectors of the two structural review sheets |
| `analysis-variants.csv` | Concise diagnostic results |
| `analysis-checks.json` | Detailed numerical verification |
| `support-reactions.csv` | Positioned unfactored reactions; not foundation design loads |
| `reaction-sources.json` | Origin and hashes of the reaction table |
| `model-adoption.json`, `drawing-manifest.json` | Source and output identities |
| `execution-record.json`, `landing-article-execution.json` | Actual commands, tests, reproduction and failure evidence |

Execution records preserve hashes from the actual runs; current reader-file
identities are in `drawing-manifest.json`. Caption and path changes are explained
in [the presentation record](../../../../docs/provenance/presentation.json).
The model receipt's historical `exact_reproduction_record` raw path was removed;
its surviving evidence is the `reproduction` object in `execution-record.json`.
The article does not require readers to follow internal revision IDs or development history.
No complete RC, foundation, pricing or construction-release package is claimed.
