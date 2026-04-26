#!/usr/bin/env bash
# bump-strategy.sh — Apply the openfilter mechanical bump to a consumer
# repo's working tree. Run from the consumer clone's root (CWD).
#
# Per the DT-145 design (cascade-dispatch-bumps/PROPOSAL.md §"Bump strategy"):
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
# Idempotent: re-running on a clone that's already on OF_VERSION leaves the
# working tree unchanged. The caller (bump-and-pr.sh) uses `git diff` to
# detect that case and skips the PR.
set -euo pipefail

: "${OF_VERSION:?OF_VERSION must be set (bare semver, e.g. 0.1.28)}"

# ─── 1. pyproject.toml ────────────────────────────────────────────────────
# Use Python (tomllib for parse, plain text rewrite for stable formatting —
# tomli_w would lose comments / ordering). The dependency line shape we
# rewrite is the PEP 508 form: `openfilter==X.Y.Z`, `openfilter>=X.Y.Z,<2`,
# `openfilter~=X.Y`, etc. We only swap the version specifier, leaving the
# operator and any trailing extras/markers intact, so consumers that pinned
# `openfilter[gpu]>=0.1.10` will become `openfilter[gpu]>=0.1.28` not
# `openfilter==0.1.28`.
if [[ -f pyproject.toml ]]; then
  python3 <<'PY'
import os
import re
import sys

of_version = os.environ["OF_VERSION"]
path = "pyproject.toml"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Match a quoted PEP 508 requirement string for openfilter inside a TOML
# array (i.e. inside [project.dependencies] or an optional-dependencies
# group). We rewrite ONLY the version specifier (the bit after the operator),
# preserving extras, the operator itself, and any environment markers.
#
# Examples handled:
#   "openfilter==0.1.27"             → "openfilter==0.1.28"
#   "openfilter>=0.1.10,<2"          → "openfilter>=0.1.28,<2"
#   "openfilter[gpu]~=0.1.27"        → "openfilter[gpu]~=0.1.28"
#   "openfilter ; python_version<4"  → unchanged (no version specifier)
pattern = re.compile(
    r'''(["'])
        (openfilter(?:\[[^\]]+\])?)   # name + optional extras
        \s*
        (==|~=|>=|<=|>|<|!=)          # operator
        \s*
        ([0-9][^,;"'\s]*)             # version
        ([^"']*)                      # tail (additional clauses, markers)
        \1''',
    re.VERBOSE,
)

def replace(match: "re.Match[str]") -> str:
    quote, name, op, _old_version, tail = match.groups()
    return f"{quote}{name}{op}{of_version}{tail}{quote}"

new_text, n = pattern.subn(replace, text)
if n == 0:
    # No openfilter pin to update — bump-strategy is a no-op on this file.
    # Discovery should already have filtered this case out, but be lenient.
    print("pyproject.toml: no openfilter dependency line matched", file=sys.stderr)
elif new_text != text:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"pyproject.toml: rewrote {n} openfilter pin(s) → {of_version}")
else:
    print(f"pyproject.toml: openfilter already at {of_version}")
PY
fi

# ─── 2. requirements*.txt ─────────────────────────────────────────────────
# Same shape rewrite as pyproject, but on plain pip requirements files.
# Glob non-fatal — many filter repos use only pyproject.
shopt -s nullglob
REQ_FILES=( requirements*.txt )
shopt -u nullglob

for REQ in "${REQ_FILES[@]}"; do
  python3 - "${REQ}" <<'PY'
import os
import re
import sys

path = sys.argv[1]
of_version = os.environ["OF_VERSION"]

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Match a requirement line for openfilter (start of line, after optional
# whitespace, before optional `#` comment / env markers). We rewrite the
# version specifier in place.
pattern = re.compile(
    r'''^(\s*)
        (openfilter(?:\[[^\]]+\])?)
        \s*
        (==|~=|>=|<=|>|<|!=)
        \s*
        ([0-9][^\s;#]*)
        (.*)$''',
    re.VERBOSE,
)

changed = 0
for i, line in enumerate(lines):
    m = pattern.match(line)
    if not m:
        continue
    indent, name, op, _old, tail = m.groups()
    new_line = f"{indent}{name}{op}{of_version}{tail}\n"
    if new_line != line:
        lines[i] = new_line
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
import re
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
    if re.match(r"^## ", line):
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
    if re.match(r"^## ", lines[j]):
        next_release_idx = j
        break

block = lines[release_header_idx:next_release_idx]

# Find an existing `### Changed` subsection within the block.
changed_subsection_idx = None  # index *within* `block`
for k, line in enumerate(block):
    if re.match(r"^### Changed\s*$", line):
        changed_subsection_idx = k
        break

if changed_subsection_idx is not None:
    # Insert at the end of the `### Changed` subsection — that is, just
    # before the next `### ` subsection header inside the block, or at the
    # block's end. Skip trailing blank lines so the bullet snuggles up to
    # the existing list rather than being separated by blanks.
    insertion_idx = len(block)
    for m in range(changed_subsection_idx + 1, len(block)):
        if re.match(r"^### ", block[m]):
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
