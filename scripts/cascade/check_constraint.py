"""Check openfilter version constraint compatibility.

Reads OF_VERSION from env, scans pyproject.toml for openfilter dependency.
Outputs: none | none:poetry-format | ok:<spec> | widen:<spec> | skip:<spec> | error:<msg>

`none:poetry-format` is emitted when no openfilter dep was found in PEP 621
[project.dependencies] / [project.optional-dependencies] but one IS present
under Poetry's [tool.poetry.dependencies] (or dev-dependencies). The cascade
only knows how to rewrite PEP 621 pins, so Poetry consumers are still
skipped — but the operator gets a distinguishable diagnostic instead of a
silent "no openfilter dep" line.

`widen:<spec>` means OF_VERSION is outside the current constraint, BUT the
only blocking clauses are upper bounds (`<` / `<=`) that bump-strategy.sh
can safely widen. `skip:<spec>` is reserved for blocks the cascade refuses
to rewrite automatically: lower-bound exclusions (would be a downgrade) and
explicit `!=` exclusions (deliberate gating). Splitting `widen` from `skip`
lets the cascade discover this filter as eligible while keeping a hard
boundary against silent semantic regressions.

When openfilter appears in MULTIPLE PEP 621 tables (e.g. [project.dependencies]
AND [project.optional-dependencies.gpu]), all matching specifiers are
intersected before the eligibility decision. Otherwise a `>=0.1.10,<2` in
the base + `>=0.2,<2` in an optional extra would treat 0.1.30 as eligible
and then bump-strategy.sh would rewrite the optional pin into something
the optional specifier rejects.
"""
import sys, os, tomllib

from packaging.requirements import Requirement
from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version


def _is_widenable_block(combined: SpecifierSet, target: Version) -> bool:
    """True when every clause that excludes `target` is a widenable upper bound.

    Widenable: `<X` or `<=X` — bump-strategy.sh's rewriter handles these
    in place.

    Not widenable: `>=X` / `>X` lower bounds (widening would be a downgrade),
    `!=X` exclusions (deliberate gating), and `==X` / `~=X` pins (the
    rewriter can bump these in place, but if they're still excluding
    target after intersection it means another clause makes the situation
    unsalvageable; operator should inspect).
    """
    for s in combined:
        if target in SpecifierSet(str(s)):
            continue
        if s.operator in ("<", "<="):
            continue
        return False
    return True


try:
    if not os.path.exists("pyproject.toml"):
        print("none")
        sys.exit(0)
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = list(data.get("project", {}).get("dependencies", []))
    for g in data.get("project", {}).get("optional-dependencies", {}).values():
        deps.extend(g)
    matched_specifiers = []
    for d in deps:
        r = Requirement(d)
        if r.name == "openfilter":
            matched_specifiers.append(r.specifier)
    if not matched_specifiers:
        # Fallback: Poetry's [tool.poetry.dependencies] table. We can't
        # bump these (the cascade only rewrites PEP 621 pins), but emit a
        # distinguishable result so the operator sees WHY we skipped.
        poetry_tbl = data.get("tool", {}).get("poetry", {})
        poetry_deps = {}
        if isinstance(poetry_tbl, dict):
            poetry_deps.update(poetry_tbl.get("dependencies", {}) or {})
            poetry_deps.update(poetry_tbl.get("dev-dependencies", {}) or {})
        if "openfilter" in poetry_deps:
            print("none:poetry-format")
            sys.exit(0)
        print("none")
        sys.exit(0)
    # Intersect all matching specifiers. SpecifierSet supports `&` for
    # intersection (returns a new SpecifierSet covering both constraints).
    combined = SpecifierSet()
    for spec in matched_specifiers:
        combined &= spec
    if not combined:
        print("ok:")
        sys.exit(0)
    v_str = os.environ.get("OF_VERSION", "")
    if not v_str:
        print("error:OF_VERSION not set")
        sys.exit(0)
    v = Version(v_str)
    spec_str = str(combined)
    if v in combined:
        print("ok:" + spec_str)
    elif _is_widenable_block(combined, v):
        print("widen:" + spec_str)
    else:
        print("skip:" + spec_str)
except Exception as e:
    print("error:" + str(e))
