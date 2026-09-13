# Article handoff

The article is maintained only in
[WordPress draft 4630](https://www.maksonlee.com/wp-admin/post.php?post=4630&action=edit)
(site login required), titled **Use AI, IFC, and OpenSees to Simulate a Building
Design Workflow**. Last checked on 2026-09-13 UTC: draft, comments open.

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
Next editorial step: update the article's availability wording once companion
files are public. WordPress publication and project-wide licence selection remain
separate decisions. Do not recreate a local article copy or accumulate a diary
of edits here.

Git is initialized on `main`; `origin` targets the companion repository above.
Use Git status and remote tracking to determine the current commit/push state.
