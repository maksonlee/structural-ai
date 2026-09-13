# Attribution and dependency boundaries

Imported A01 Python converter/reader/adapter code retains the notice in
[the imported-code MIT notice](LICENSES/imported-code-MIT.txt); its mapping and
changes are in `docs/provenance/import-map.json`. Imported source headers retain
their original filename reference, resolved by that mapping. No original
third-party copyright notice is removed.

The installed runtime dependencies are NumPy, Shapely and PyYAML. Optional dependencies
are OpenSeesPy and IfcOpenShell. They are not bundled or relicensed by this repository.
Review their actual installed versions, licenses and transitive dependencies before
redistribution; pyproject version ranges are not an audited software bill of materials.

OpenSees/OpenSeesPy are source-available research tools with upstream use/redistribution
conditions, including commercial licensing requirements. Do not describe them as covered
by a project MIT license. The optional dependency is not a claim of unrestricted use.

Official sources:
- https://opensees.github.io/OpenSeesDocumentation/developer/license.html
- https://openseespydoc.readthedocs.io/en/latest/
- https://docs.ifcopenshell.org/
- https://numpy.org/
- https://shapely.readthedocs.io/
- https://pyyaml.org/

Regulatory texts and vendor manuals are cited, not redistributed. No proprietary
engineering software or real project files are included in this simulated example.

The reviewed architectural, structural and landing-strip PDF drawings embed subsets
of DejaVu Sans. The complete [upstream font notice](LICENSES/DejaVu-fonts.txt) is
retained from the DejaVu 2.37 release; its source, hash and affected PDFs are recorded
in [the source register](docs/sources.yaml). Font rights remain with their respective
owners. This notice does not license the project's drawings or code.
