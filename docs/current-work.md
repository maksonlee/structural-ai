# Article handoff

The article is maintained only in WordPress:
[Use AI, IFC, and OpenSees to Simulate a Building Design Workflow](https://www.maksonlee.com/ai-ifc-opensees-building-design-workflow/).
Post 4630 was published with the owner's authorization on 2026-09-13 UTC
(2026-09-14 Taipei). Anonymous page and API checks confirm publication and open
comments; desktop and mobile screenshots show readable layouts. The reader review
covered prose, excerpt, figures, captions, links and
internal/private content; the GitHub availability sentence now uses present tense.

Use English, short practical explanations and three principal figures. The author
has civil engineering education and no industry practice experience. Present a
simulation with explicit limits and a casual invitation to comment about mistakes.
Keep article text, editorial history and style-review records in WordPress.

Current figure attachments are 4635 (IFC overview), 4628 (structural interface)
and 4629 (landing reinforcement). The architectural plan, 4627, is linked in the
text. Local originals are in `article-images/` and identified by the drawing
manifest. The companion repository is
[structural-ai](https://github.com/maksonlee/structural-ai). Match the article's
file-availability wording to the repository's actual public availability.

The [README](../README.md) provides the scope and reading path. Current engineering
evidence is indexed in [structural outputs](../project/structural/outputs/current.md);
full design remains unfinished. [Development instructions](development.md) cover
reproduction, including `--verification` for a newly generated analysis run.
The article/file consistency review passed 83 tests (zero skipped), source/output
identity checks and online image comparisons. Default and explicit retained-run
landing calculations reproduce the reviewed numbers and SVG. Fresh-run selection
has isolated fixture coverage; the whole-building analysis was not rerun.

The [public-payload review](publishing.md) found no confirmed privacy issue and
added the embedded PDF font notice. Inspect actual staged files before each push.
The article and companion files are public. No publication task remains; future
reader corrections should be made in WordPress and reconciled with affected
companion files. Project-wide licence selection remains open. Do not recreate a
local article copy or accumulate a diary of edits here.

Git is initialized on `main`; `origin` targets the companion repository above.
Use Git status and remote tracking to determine the current commit/push state.
