#!/usr/bin/env python3
"""Generate README.pypi.md from README.md.

PyPI's README renderer does not run Mermaid (it would show the raw fenced block), so the
PyPI long description replaces every Mermaid diagram with a short pointer to the rendered
diagram on GitHub. README.md stays the canonical source. The replacement matches the
```mermaid fence rather than the diagram's contents, so editing the diagram in README.md
never requires touching this script. All links in README.md are absolute, so they already
render on PyPI unchanged.

Usage:
    python scripts/make_pypi_readme.py          # regenerate README.pypi.md
    python scripts/make_pypi_readme.py --check   # verify README.pypi.md is up to date (CI)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "README.md"
TARGET = ROOT / "README.pypi.md"

GENERATED_HEADER = (
    "<!-- Generated from README.md by scripts/make_pypi_readme.py. Do not edit directly. -->\n\n"
)

# Match any ```mermaid ... ``` fenced block. Keyed on the fence, not the diagram body,
# so the diagram can change freely without updating this script.
MERMAID_FENCE = re.compile(r"```mermaid\n.*?\n```", re.DOTALL)
DIAGRAM_POINTER = (
    "> **Pipeline diagram:** rendered on the "
    "[GitHub README](https://github.com/PlainsightAI/openfilter#readme)."
)


def render() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    converted, count = MERMAID_FENCE.subn(DIAGRAM_POINTER, source)
    if count == 0:
        raise SystemExit(
            "make_pypi_readme: no ```mermaid block found in README.md. If the diagram was "
            "removed for good, drop this PyPI conversion (script, Makefile targets, CI job, "
            "and the pyproject readme pointer); otherwise check the fence language tag."
        )
    return GENERATED_HEADER + converted


def main(argv: list[str]) -> int:
    rendered = render()
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != rendered:
            print(
                "README.pypi.md is out of date. Run: python scripts/make_pypi_readme.py",
                file=sys.stderr,
            )
            return 1
        print("README.pypi.md is up to date.")
        return 0
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
