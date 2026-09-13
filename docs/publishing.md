# Release requirements

The article lives in WordPress; its location is in [the handoff](current-work.md).
The companion repository is
[maksonlee/structural-ai](https://github.com/maksonlee/structural-ai).
Referencing it in the article does not authorize a push. Article publication,
repository release and licence selection are separate actions.

## Notices and dependencies

No project-wide licence has been selected. Preserve
[the imported notice](../LICENSES/imported-code-MIT.txt) and
[dependency boundaries](../THIRD_PARTY_NOTICES.md). The imported MIT notice does
not license all new code, models, documentation or dependencies; public visibility
does not supply a licence.

OpenSees/OpenSeesPy have upstream use and redistribution conditions, including
commercial licensing requirements. Dependencies are installed separately and are
not bundled or relicensed here. Review intended redistribution against the
upstream terms recorded in [the source register](sources.yaml).

## Files and evidence

Keep credentials, private project files, machine identifiers and raw conversations
out of public files and Git history. Cite regulatory texts and vendor manuals;
do not bundle third-party documents without redistribution rights.

Retain tested versions, reproduction commands, reviewed outputs and source hashes.
Raw runs remain ignored; preserve relevant failures and report missing historical
evidence honestly. Original article figures remain with their source records.
Earlier execution records may name former files; they describe their actual runs.

Public-payload review on 2026-09-14 (Taipei): Git's ignore rules select 125 files,
approximately 2.76 MB, including the DejaVu notice for embedded PDF font subsets.
Text, PDF/PNG metadata and IFC headers showed no confirmed credentials, private
host identifiers or machine paths. No solver binaries or third-party manuals are
included; `.venv/` and raw runs remain excluded. This is a scoped inspection, not
a guarantee for future additions. The initial audit preceded Git initialization.
First-push preparation also checked all 125 staged files against their working
bytes; an isolated staged checkout passed 83 tests and scoped input validation.
CSV line endings are preserved for existing output hashes. Original font-licence
and imported-source whitespace is retained intentionally.

After initializing Git and selecting files, inspect `git diff --cached --stat`
and run `.venv/bin/python scripts/review_public_files.py --tracked`
(use the host wrapper where required). Do not force-add ignored environments or
raw runs. Public visibility does not select a project-wide licence; existing
imported-code and font notices retain their respective scopes.

All outputs must identify simulated assumptions and incomplete checks. Releasing
an introductory study does not establish full structural design, professional
approval or permission to construct. See [scope](../README.md#scope) and
[verification limits](validation.md).
