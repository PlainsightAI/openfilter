#!/usr/bin/env bash
# bump-strategy.sh — Apply the openfilter mechanical bump to a consumer
# repo's working tree. Run from the consumer clone's root (CWD).
#
# Per the DT-145 design (https://plainsight-ai.atlassian.net/browse/DT-145):
#   1. Update the openfilter pin in pyproject.toml ([project.dependencies]
#      and [project.optional-dependencies.*] groups).
#   2. Update the openfilter pin in any requirements*.txt files.
#   3. Append a `### Changed` entry to RELEASE.md mentioning the new version,
#      creating the section under the most-recent release header if missing.
#
# Notably we do NOT touch the consumer's own VERSION file — bumping their
# release version is the consumer's own create-release flow's job, fired
# automatically when the bump PR merges.
#
# Required env:
#   OF_VERSION  bare semver (e.g. 0.1.28)
#
# Required tooling:
#   python3 with `tomllib` (>= 3.11) and `packaging` (pip install packaging).
#
# Idempotent: re-running on a clone that's already on OF_VERSION leaves the
# working tree unchanged. The caller (bump-and-pr.sh) detects that case via
# `git status --porcelain` and skips the PR.
set -euo pipefail

: "${OF_VERSION:?OF_VERSION must be set (bare semver, e.g. 0.1.28)}"

# ─── Shared bump helper (sourced by both python3 invocations) ─────────────
# We dump a small helper module to a tempdir and add it to PYTHONPATH so the
# pyproject/requirements rewrites can share the rewrite logic without copying
# 30 lines of code into two heredocs.
BUMP_HELPER_DIR=$(mktemp -d)
trap 'rm -rf "${BUMP_HELPER_DIR}"' EXIT
cat > "${BUMP_HELPER_DIR}/_bump.py" <<'HELPER'
"""Shared rewrite primitive for bump-strategy.sh.

`rewrite_requirement(old, of_version)` takes a PEP 508 requirement string
(e.g. `openfilter[gpu]>=0.1.10,<2 ; python_version<"4"`) and returns the
same string with each lower-bound clause (`==`, `>=`, `~=`) bumped to
`of_version`. Upper-bound clauses (`<`, `<=`, `!=`) are preserved verbatim,
as is the original clause order, surrounding whitespace, and any marker.
"""
from __future__ import annotations

from packaging.requirements import Requirement
from packaging.specifiers import Specifier


_BUMPABLE_OPS = ("==", ">=", "~=")


def _specifier_span(text: str, req: Requirement) -> tuple[int, int]:
    """Locate the substring of `text` containing the specifier clauses.

    Format: `<name>[<extras>] <specifier> [; <marker>]`. We skip past the
    name + optional `[extras]` (matching brackets to handle nested commas)
    and stop at the marker delimiter ';' or end of string.
    """
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
    if ";" in text[spec_start:]:
        spec_end = spec_start + text[spec_start:].index(";")
    else:
        spec_end = len(text)
    return spec_start, spec_end


def rewrite_requirement(old: str, of_version: str) -> str:
    req = Requirement(old)
    if not req.specifier:
        return old

    spec_start, spec_end = _specifier_span(old, req)
    spec_text = old[spec_start:spec_end]

    # Walk comma-separated clauses, preserving order and per-clause
    # whitespace. Rewrite only the version of each lower-bound clause.
    new_clauses: list[str] = []
    bumped = False
    for raw in spec_text.split(","):
        stripped = raw.strip()
        if not stripped:
            new_clauses.append(raw)
            continue
        s = Specifier(stripped)
        if s.operator in _BUMPABLE_OPS:
            leading = raw[: len(raw) - len(raw.lstrip())]
            trailing = raw[len(raw.rstrip()) :]
            new_clauses.append(f"{leading}{s.operator}{of_version}{trailing}")
            bumped = True
        else:
            new_clauses.append(raw)

    if not bumped:
        return old

    return old[:spec_start] + ",".join(new_clauses) + old[spec_end:]
HELPER
export PYTHONPATH="${BUMP_HELPER_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

# ─── 1. pyproject.toml ────────────────────────────────────────────────────
# Parse with tomllib + packaging.Requirement to identify exactly which
# openfilter dep strings live in [project.dependencies] and
# [project.optional-dependencies.*]. We then do a literal text replacement of
# those exact strings in the source — comments, ordering, and layout are
# preserved (which would not be true if we round-tripped through tomli_w).
if [[ -f pyproject.toml ]]; then
  python3 <<'PY'
import os
import sys
import tomllib

from packaging.requirements import Requirement

from _bump import rewrite_requirement


of_version = os.environ["OF_VERSION"]
path = "pyproject.toml"

with open(path, "rb") as f:
    data = tomllib.load(f)

project = data.get("project") or {}
declared: list[str] = []
for dep in project.get("dependencies") or []:
    if Requirement(dep).name == "openfilter":
        declared.append(dep)
for group in (project.get("optional-dependencies") or {}).values():
    for dep in group:
        if Requirement(dep).name == "openfilter":
            declared.append(dep)

if not declared:
    print("pyproject.toml: no openfilter dependency line matched", file=sys.stderr)
    sys.exit(0)

with open(path, "r", encoding="utf-8") as f:
    text = f.read()

new_text = text
total = 0
for old in dict.fromkeys(declared):
    new = rewrite_requirement(old, of_version)
    if new == old:
        continue
    for q in ('"', "'"):
        needle = f"{q}{old}{q}"
        if needle in new_text:
            count = new_text.count(needle)
            new_text = new_text.replace(needle, f"{q}{new}{q}")
            total += count

if total == 0:
    print(f"pyproject.toml: openfilter already at {of_version}")
elif new_text != text:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"pyproject.toml: rewrote {total} openfilter pin(s) → {of_version}")
PY
fi

# ─── 2. requirements*.txt ─────────────────────────────────────────────────
# Same parser-based approach as pyproject. Each line is fed to
# packaging.Requirement; if it parses and names openfilter we rewrite it,
# preserving leading whitespace and any trailing `# comment`. Lines that
# aren't valid PEP 508 requirements (e.g. `-r other.txt`, VCS URLs,
# `--index-url ...`) are left untouched.
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
    # Split off a trailing `# comment` so we can re-attach it intact.
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
    trailing_ws_len = len(body) - len(body.rstrip()) - leading_ws_len
    if trailing_ws_len < 0:
        trailing_ws_len = 0
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

# ─── 3. RELEASE.md ────────────────────────────────────────────────────────
# Append `- Bump openfilter to ${OF_VERSION}` to the `### Changed` section
# of the topmost release entry in RELEASE.md. If the topmost release entry
# has no `### Changed` section, create one immediately after its `## ...`
# header. If RELEASE.md doesn't exist, create a minimal one with a single
# entry.
#
# The most-recent release entry is the FIRST `## v...` header we encounter
# top-to-bottom (release notes are usually reverse-chronological).
python3 <<'PY'
import os
import sys

of_version = os.environ["OF_VERSION"]
path = "RELEASE.md"
bullet = f"- Bump openfilter to {of_version}"

if not os.path.exists(path):
    content = (
        "# Changelog\n"
        "\n"
        f"## (unreleased)\n"
        "\n"
        "### Changed\n"
        "\n"
        f"{bullet}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"{path}: created with bump entry")
    sys.exit(0)

with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Idempotency: don't append the same bullet twice.
if bullet in text:
    print(f"{path}: bump entry already present")
    sys.exit(0)

lines = text.splitlines(keepends=True)

# Locate the first `## ...` header (the topmost release entry).
release_header_idx = None
for i, line in enumerate(lines):
    if line.startswith("## "):
        release_header_idx = i
        break

if release_header_idx is None:
    # No release header at all — append a fresh entry block at the end.
    suffix = ""
    if not text.endswith("\n"):
        suffix = "\n"
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

# Find the end of the topmost release entry (the next `## ` header or EOF).
next_release_idx = len(lines)
for j in range(release_header_idx + 1, len(lines)):
    if lines[j].startswith("## "):
        next_release_idx = j
        break

block = lines[release_header_idx:next_release_idx]

# Find an existing `### Changed` subsection within the block.
changed_subsection_idx = None  # index *within* `block`
for k, line in enumerate(block):
    if line.rstrip() == "### Changed":
        changed_subsection_idx = k
        break

if changed_subsection_idx is not None:
    # Insert at the end of the `### Changed` subsection — that is, just
    # before the next `### ` subsection header inside the block, or at the
    # block's end. Skip trailing blank lines so the bullet snuggles up to
    # the existing list rather than being separated by blanks.
    insertion_idx = len(block)
    for m in range(changed_subsection_idx + 1, len(block)):
        if block[m].startswith("### "):
            insertion_idx = m
            break
    # Trim trailing blank lines from the slice we'd append into.
    while insertion_idx > changed_subsection_idx + 1 and block[insertion_idx - 1].strip() == "":
        insertion_idx -= 1
    block.insert(insertion_idx, f"{bullet}\n")
    # Make sure we still have a blank line separating from the next subsection
    # (or end of block) so the markdown parses cleanly.
    if insertion_idx + 1 < len(block) and block[insertion_idx + 1].strip() != "":
        block.insert(insertion_idx + 1, "\n")
    print(f"{path}: appended bump entry to existing ### Changed section")
else:
    # No `### Changed` subsection in the topmost release block. Create one
    # immediately after the release header (and any blank line trailing it).
    insert_at = 1
    while insert_at < len(block) and block[insert_at].strip() == "":
        insert_at += 1
    new_subsection = [
        "### Changed\n",
        "\n",
        f"{bullet}\n",
        "\n",
    ]
    block[insert_at:insert_at] = new_subsection
    print(f"{path}: created ### Changed section with bump entry")

new_lines = lines[:release_header_idx] + block + lines[next_release_idx:]
with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
PY
