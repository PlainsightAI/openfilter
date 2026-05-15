#!/usr/bin/env bash
# bump-strategy.sh — Bump the openfilter pin in a consumer clone:
# pyproject.toml ([project.dependencies] + [project.optional-dependencies.*]),
# requirements*.txt, and a `### Changed` bullet in RELEASE.md. Run from the
# clone root. Idempotent. Required env: OF_VERSION (bare semver). Required
# tooling: python3 with tomlkit + packaging.
# DT-145: https://plainsight-ai.atlassian.net/browse/DT-145
set -euo pipefail

: "${OF_VERSION:?OF_VERSION must be set (bare semver, e.g. 0.1.28)}"

# Shared rewrite primitive on PYTHONPATH so both pyproject and requirements
# rewriters call the same logic.
BUMP_HELPER_DIR=$(mktemp -d)
trap 'rm -rf "${BUMP_HELPER_DIR}"' EXIT
cat > "${BUMP_HELPER_DIR}/_bump.py" <<'HELPER'
"""rewrite_requirement: bump ==/>=/~= clauses in a PEP 508 requirement,
and widen `<` / `<=` upper bounds that would otherwise exclude OF_VERSION.

Lower-bound clauses (==, >=, ~=) go to OF_VERSION. Upper-bound clauses
(<, <=) are widened to admit OF_VERSION when they currently exclude it;
otherwise they stay verbatim. != exclusions, `>` lower bounds, clause
order, surrounding whitespace, and any environment marker are preserved
verbatim regardless.

Widening rule for the new upper bound:
    * target.major == 0 (pre-1.0 / unstable): `<target.major>.<target.minor + 1>.0`
      (e.g. 0.2.0 -> 0.3.0). Matches the org's existing "track next minor"
      pin pattern for 0.X filters.
    * target.major >= 1: `<target.major + 1>.0.0` (e.g. 1.0.0 -> 2.0.0).
      Standard SemVer "track next major" for post-1.0 filters.
"""
from __future__ import annotations

from packaging.requirements import Requirement
from packaging.specifiers import Specifier
from packaging.version import Version

_BUMPABLE_OPS = ("==", ">=", "~=")
_UPPER_BOUND_OPS = ("<", "<=")


def _specifier_span(text: str, req: Requirement) -> tuple[int, int]:
    """Locate the specifier substring inside `<name>[<extras>] <spec> [; <marker>]`."""
    i = 0
    while i < len(text) and text[i].isspace():
        i += 1
    i += len(req.name)
    while i < len(text) and text[i].isspace():
        i += 1
    if i < len(text) and text[i] == "[":
        depth = 1
        i += 1
        while i < len(text) and depth > 0:
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
            i += 1
    spec_start = i
    spec_end = (
        spec_start + text[spec_start:].index(";")
        if ";" in text[spec_start:]
        else len(text)
    )
    return spec_start, spec_end


def next_upper_bound(target: Version) -> str:
    """Compute the widened upper bound to admit `target` and a reasonable
    forward range. See module docstring for the rule.
    """
    if target.major == 0:
        return f"0.{target.minor + 1}.0"
    return f"{target.major + 1}.0.0"


def rewrite_requirement(old: str, of_version: str) -> str:
    req = Requirement(old)
    if not req.specifier:
        return old
    target = Version(of_version)
    spec_start, spec_end = _specifier_span(old, req)
    spec_text = old[spec_start:spec_end]
    new_clauses: list[str] = []
    bumped = False
    for raw in spec_text.split(","):
        stripped = raw.strip()
        if not stripped:
            new_clauses.append(raw)
            continue
        s = Specifier(stripped)
        leading = raw[: len(raw) - len(raw.lstrip())]
        trailing = raw[len(raw.rstrip()) :]
        if s.operator in _BUMPABLE_OPS:
            new_clauses.append(f"{leading}{s.operator}{of_version}{trailing}")
            bumped = True
            continue
        if s.operator in _UPPER_BOUND_OPS:
            bound = Version(s.version)
            needs_widen = (
                (s.operator == "<" and target >= bound)
                or (s.operator == "<=" and target > bound)
            )
            if needs_widen:
                new_clauses.append(
                    f"{leading}<{next_upper_bound(target)}{trailing}"
                )
                bumped = True
                continue
        new_clauses.append(raw)
    if not bumped:
        return old
    return old[:spec_start] + ",".join(new_clauses) + old[spec_end:]
HELPER
export PYTHONPATH="${BUMP_HELPER_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

# 1. pyproject.toml — tomlkit round-trips comments and layout, so we mutate
#    individual array items in place rather than literal-replacing strings.
if [[ -f pyproject.toml ]]; then
  python3 <<'PY'
import os
import sys

import tomlkit
from packaging.requirements import InvalidRequirement, Requirement

from _bump import rewrite_requirement


of_version = os.environ["OF_VERSION"]
path = "pyproject.toml"

with open(path, "r", encoding="utf-8") as f:
    doc = tomlkit.parse(f.read())

project = doc.get("project")
if project is None:
    print("pyproject.toml: no [project] table — nothing to bump", file=sys.stderr)
    sys.exit(0)


def bump_array(arr) -> int:
    """In-place rewrite of openfilter entries; returns count of changed items."""
    if arr is None:
        return 0
    n = 0
    for i in range(len(arr)):
        s = str(arr[i])
        try:
            req = Requirement(s)
        except InvalidRequirement:
            continue
        if req.name != "openfilter":
            continue
        new = rewrite_requirement(s, of_version)
        if new != s:
            arr[i] = new
            n += 1
    return n


total = bump_array(project.get("dependencies"))
for group in (project.get("optional-dependencies") or {}).values():
    total += bump_array(group)

if total == 0:
    print(f"pyproject.toml: openfilter already at {of_version}")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(doc))
    print(f"pyproject.toml: rewrote {total} openfilter pin(s) → {of_version}")
PY
fi

# 2. requirements*.txt — packaging.Requirement per line; non-PEP-508 lines
#    (-r other.txt, VCS URLs, --index-url) are left alone.
shopt -s nullglob
REQ_FILES=( requirements*.txt )
shopt -u nullglob

for REQ in "${REQ_FILES[@]}"; do
  python3 - "${REQ}" <<'PY'
import os
import sys

from packaging.requirements import InvalidRequirement, Requirement

from _bump import rewrite_requirement


path = sys.argv[1]
of_version = os.environ["OF_VERSION"]

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

changed = 0
for i, line in enumerate(lines):
    stripped = line.rstrip("\n")
    comment_at = stripped.find("#")
    if comment_at == -1:
        body, comment = stripped, ""
    else:
        body, comment = stripped[:comment_at], stripped[comment_at:]

    leading_ws_len = len(body) - len(body.lstrip())
    body_stripped = body.strip()
    if not body_stripped:
        continue
    try:
        req = Requirement(body_stripped)
    except InvalidRequirement:
        continue
    if req.name != "openfilter":
        continue
    new_body_stripped = rewrite_requirement(body_stripped, of_version)
    if new_body_stripped == body_stripped:
        continue
    trailing_ws_len = len(body) - len(body.rstrip())
    lines[i] = (
        body[:leading_ws_len]
        + new_body_stripped
        + (body[len(body) - trailing_ws_len :] if trailing_ws_len else "")
        + comment
        + "\n"
    )
    changed += 1

if changed:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"{path}: rewrote {changed} openfilter pin(s) → {of_version}")
PY
done

# 3. RELEASE.md — append `- Bump openfilter to ${OF_VERSION}` under the
#    topmost `## ` block's `### Changed` subsection, creating either as
#    needed. Idempotency check is line-anchored so 0.1.9 doesn't match 0.1.99.
python3 <<'PY'
import os
import sys

of_version = os.environ["OF_VERSION"]
path = "RELEASE.md"
bullet = f"- Bump openfilter to {of_version}"

if not os.path.exists(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "# Changelog\n"
            "\n"
            "## (unreleased)\n"
            "\n"
            "### Changed\n"
            "\n"
            f"{bullet}\n"
        )
    print(f"{path}: created with bump entry")
    sys.exit(0)

with open(path, "r", encoding="utf-8") as f:
    text = f.read()

if any(line.rstrip() == bullet for line in text.splitlines()):
    print(f"{path}: bump entry already present")
    sys.exit(0)

lines = text.splitlines(keepends=True)

release_header_idx = next(
    (i for i, line in enumerate(lines) if line.startswith("## ")),
    None,
)

if release_header_idx is None:
    suffix = "" if text.endswith("\n") else "\n"
    suffix += (
        "\n"
        "## (unreleased)\n"
        "\n"
        "### Changed\n"
        "\n"
        f"{bullet}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + suffix)
    print(f"{path}: appended new release block with bump entry")
    sys.exit(0)

next_release_idx = next(
    (j for j in range(release_header_idx + 1, len(lines)) if lines[j].startswith("## ")),
    len(lines),
)
block = lines[release_header_idx:next_release_idx]

changed_idx = next(
    (k for k, line in enumerate(block) if line.rstrip() == "### Changed"),
    None,
)

if changed_idx is not None:
    insertion_idx = next(
        (m for m in range(changed_idx + 1, len(block)) if block[m].startswith("### ")),
        len(block),
    )
    while insertion_idx > changed_idx + 1 and block[insertion_idx - 1].strip() == "":
        insertion_idx -= 1
    block.insert(insertion_idx, f"{bullet}\n")
    if insertion_idx + 1 < len(block) and block[insertion_idx + 1].strip() != "":
        block.insert(insertion_idx + 1, "\n")
    print(f"{path}: appended bump entry to existing ### Changed section")
else:
    insert_at = 1
    while insert_at < len(block) and block[insert_at].strip() == "":
        insert_at += 1
    block[insert_at:insert_at] = [
        "### Changed\n",
        "\n",
        f"{bullet}\n",
        "\n",
    ]
    print(f"{path}: created ### Changed section with bump entry")

new_lines = lines[:release_header_idx] + block + lines[next_release_idx:]
with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
PY
