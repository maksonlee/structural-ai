# Raw calculation evidence

Read `../current.md` for the article's reports and drawings.
This directory contains generated models, actual solver results, command logs,
checksums and verification records for the same building.
Ignored raw files will not accompany a source-only Git checkout. Regenerate the
required analysis evidence using [the development guide](../../../../docs/development.md).

The whole-building verification and the local landing calculation are separate
computations. Presentation checks may also be recorded here; they are not new
building designs. Use the manifests to distinguish solving from drawing or file
checks. Never report an editorial change as a fresh solver execution.

Create fresh run directories for computations; do not overwrite completed
evidence or silently discard failed checks. Raw-run identifiers are technical
metadata, not part of the article's project-stage naming.
