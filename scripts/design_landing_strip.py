"""Reproduce the article's scoped existing-landing calculation and SVG; no AI required."""
import argparse
from pathlib import Path

from structural_ai.landing_detail import calculate, draw
from structural_ai.provenance import write_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory under project/structural/outputs/runs")
    parser.add_argument("--verification", type=Path,
                        help="Completed H03-C verification run; default uses the adopted retained receipt")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root/"project/structural/outputs/runs"):
        parser.error("Use the project's ignored runs directory")
    output.mkdir(parents=True, exist_ok=False)
    result = calculate(root, verification=args.verification)
    write_json(output/"landing-strip.json", result)
    draw(result, output/"RC-001-landing-strip.svg")
    print("Output:", output.relative_to(root))
    print("OpenSees", result["cases"]["SERVICE"]["version"], ": 3 gravity cases + refined governing case; selected checks passed")
    print("Scope: one existing landing strip. Full stair design and construction release remain incomplete.")
