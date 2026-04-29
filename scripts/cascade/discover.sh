#!/usr/bin/env bash
# discover.sh — Walk PlainsightAI org for filter-* repos eligible to receive
# an openfilter bump PR for ${OF_VERSION}.
#
# Eligibility rules (port of build-filters.sh:200-211 + new marker / constraint
# checks per the DT-145 design — https://plainsight-ai.atlassian.net/browse/DT-145):
#   1. Repo name matches `filter-*`
#   2. Not on the static exclude list (templates, retired *-old repos,
#      pre-templatize stubs that were never rendered)
#   3. Has a VERSION file at the default branch tip
#   4. Does NOT have a `.github/no-cascade-openfilter` marker file
#   5. Declares an `openfilter` dependency in pyproject.toml AND its
#      declared version constraint allows ${OF_VERSION}
#      (delegated to scripts/cascade/check_constraint.py)
#
# Eligible repo names (one per line) → stdout.
# Skip-reason diagnostics → stderr.
#
# Required env vars:
#   OF_VERSION  — bare semver (no `v` prefix) of the new openfilter release
#   GH_TOKEN    — plainsight-bot PAT with org-level read (set by the workflow
#                 from secrets.GH_BOT_USER_PAT); consumed implicitly by `gh`
# Optional env vars:
#   SINGLE_FILTER  — restrict cascade to a single repo (takes precedence)
#   FILTER_SUBSET  — comma-separated subset of repos to consider
#
# DT-145: https://plainsight-ai.atlassian.net/browse/DT-145
set -euo pipefail

: "${OF_VERSION:?OF_VERSION must be set (bare semver, e.g. 0.1.28)}"
: "${GH_TOKEN:?GH_TOKEN must be set (plainsight-bot PAT)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_CONSTRAINT_PY="${SCRIPT_DIR}/check_constraint.py"

# ─── Static exclude list ──────────────────────────────────────────────────
# Lifted verbatim from build-filters.sh:200-211. The three categories are:
#   - *-old           superseded repos kept for archaeology
#   - filter-template cookiecutter source, never directly buildable
#   - the named repos contain unrendered Jinja placeholders (e.g.
#     {{REPO_NAME_KEBABCASE}}) in their Dockerfile — they were forked from
#     the template before templatize ran. Re-enable as those repos get fixed.
is_excluded() {
  case "$1" in
    *-old|filter-template|\
    filter-mocktext|filter-timescaledb|filter-pytorch-model|\
    filter-florence|filter-pytorch|filter-facedetector|\
    filter-nov-pilot|filter-tracking-reid)
      return 0 ;;
  esac
  return 1
}

# ─── Phase 1: list candidates ─────────────────────────────────────────────
# `gh repo list` already paginates and respects PAT scope. --no-archived
# drops dormant repos automatically. We over-fetch (limit 1000) rather than
# loop manually — the org has ~150 repos as of this writing.
echo "Discovering filter-* repos in PlainsightAI org…" >&2
ALL_FILTER_REPOS=$(
  gh repo list PlainsightAI \
    --limit 1000 \
    --no-archived \
    --json name \
    --jq '.[] | select(.name | startswith("filter-")) | .name' \
    | sort -u
)

if [[ -z "${ALL_FILTER_REPOS}" ]]; then
  echo "ERROR: discovery returned zero filter-* repos — check GH_TOKEN scope" >&2
  exit 1
fi

TOTAL=$(echo "${ALL_FILTER_REPOS}" | wc -l | tr -d ' ')
echo "Discovered ${TOTAL} filter-* repos" >&2

# ─── Phase 2: apply SINGLE_FILTER / FILTER_SUBSET selectors ───────────────
CANDIDATES="${ALL_FILTER_REPOS}"
if [[ -n "${SINGLE_FILTER:-}" ]]; then
  if echo "${ALL_FILTER_REPOS}" | grep -Fqx "${SINGLE_FILTER}"; then
    echo "Single-filter mode: ${SINGLE_FILTER}" >&2
    CANDIDATES="${SINGLE_FILTER}"
  else
    echo "ERROR: SINGLE_FILTER='${SINGLE_FILTER}' not found among discovered repos" >&2
    exit 1
  fi
elif [[ -n "${FILTER_SUBSET:-}" ]]; then
  echo "Subset mode: ${FILTER_SUBSET}" >&2
  SUBSET_LIST=""
  SUBSET_MISSING=""
  IFS=',' read -ra SUBSET_ITEMS <<< "${FILTER_SUBSET}"
  for ITEM in "${SUBSET_ITEMS[@]}"; do
    ITEM=$(echo "${ITEM}" | xargs)
    [[ -z "${ITEM}" ]] && continue
    if echo "${ALL_FILTER_REPOS}" | grep -Fqx "${ITEM}"; then
      SUBSET_LIST="${SUBSET_LIST}${SUBSET_LIST:+$'\n'}${ITEM}"
    else
      SUBSET_MISSING="${SUBSET_MISSING:+${SUBSET_MISSING}, }${ITEM}"
    fi
  done
  if [[ -n "${SUBSET_MISSING}" ]]; then
    echo "WARNING: subset entries not found in org: ${SUBSET_MISSING}" >&2
  fi
  if [[ -z "${SUBSET_LIST}" ]]; then
    echo "ERROR: no FILTER_SUBSET entries match discovered repos" >&2
    exit 1
  fi
  CANDIDATES="${SUBSET_LIST}"
fi

# ─── Phase 3: per-repo eligibility checks ─────────────────────────────────
# We use `gh api /repos/.../contents/...` per file rather than cloning each
# repo. This is N HTTPS requests per consumer (roughly 3) instead of a full
# clone, which scales much better across ~50 filter-* repos.
#
# fetch_file <repo> <path>
#   Echoes the file contents to stdout when the file exists at the default
#   branch tip and returns 0; on 404 it returns 1 silently; on any other
#   error (rate-limit, transient 5xx, network) it surfaces a step-level
#   `::warning::` so the failure is visible in the Actions UI summary,
#   then returns 1 — same as 404 — so the per-consumer loop continues.
#   We rely on `gh api`'s exit code (0 on 2xx, non-zero otherwise) and its
#   stderr ("HTTP 404: ..." etc.) for status discrimination, rather than
#   parsing `--include`-merged headers out of stdout.
fetch_file() {
  local repo="$1"
  local path="$2"
  local body err
  err=$(mktemp)
  if body=$(gh api \
              -H "Accept: application/vnd.github.raw" \
              "/repos/PlainsightAI/${repo}/contents/${path}" \
              2>"${err}"); then
    rm -f "${err}"
    printf '%s' "${body}"
    return 0
  fi
  # Non-zero exit. Determine whether it's a clean 404 (silent skip) or
  # something the operator should see.
  if grep -q 'HTTP 404' "${err}"; then
    rm -f "${err}"
    return 1
  fi
  echo "::warning::transient error fetching ${repo}/${path}: $(tr '\n' ' ' < "${err}")" >&2
  rm -f "${err}"
  return 1
}

ELIGIBLE_COUNT=0
SKIPPED_COUNT=0

while IFS= read -r REPO; do
  [[ -z "${REPO}" ]] && continue

  # 1. Static exclude list
  if is_excluded "${REPO}"; then
    echo "  ${REPO}: skip (exclude list)" >&2
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  # 2. Opt-out marker — universal opt-out primitive per the proposal.
  if fetch_file "${REPO}" ".github/no-cascade-openfilter" >/dev/null; then
    echo "  ${REPO}: skip (.github/no-cascade-openfilter marker present)" >&2
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  # 3. Must have a VERSION file (consumer's own release version — the bump
  #    PR mutates pyproject.toml/requirements but does NOT touch this file;
  #    its presence is just a sanity check that the consumer is on the
  #    standard release flow).
  if ! fetch_file "${REPO}" "VERSION" >/dev/null; then
    echo "  ${REPO}: skip (no VERSION file)" >&2
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  # 4. Constraint compatibility — fetch pyproject.toml, run
  #    check_constraint.py against it. The script reads from CWD, so we
  #    materialise the file in a per-repo tempdir.
  PYPROJECT=$(fetch_file "${REPO}" "pyproject.toml") || PYPROJECT=""
  if [[ -z "${PYPROJECT}" ]]; then
    echo "  ${REPO}: skip (no pyproject.toml)" >&2
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  TMPDIR_REPO=$(mktemp -d)
  printf '%s' "${PYPROJECT}" > "${TMPDIR_REPO}/pyproject.toml"
  PY_ERR=$(mktemp)
  COMPAT=$(cd "${TMPDIR_REPO}" && OF_VERSION="${OF_VERSION}" python3 "${CHECK_CONSTRAINT_PY}" 2>"${PY_ERR}") \
    || COMPAT="error:python-failed"
  if [[ "${COMPAT}" == "error:python-failed" && -s "${PY_ERR}" ]]; then
    echo "::warning::check_constraint.py crashed for ${REPO}: $(tr '\n' ' ' < "${PY_ERR}")" >&2
  fi
  rm -f "${PY_ERR}"
  rm -rf "${TMPDIR_REPO}"

  case "${COMPAT}" in
    none)
      echo "  ${REPO}: skip (no openfilter dep)" >&2
      SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
      continue ;;
    ok:*)
      # Eligible.
      ;;
    skip:*)
      CONSTRAINT="${COMPAT#skip:}"
      echo "  ${REPO}: skip (constraint ${CONSTRAINT} excludes ${OF_VERSION})" >&2
      SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
      continue ;;
    error:*)
      ERR="${COMPAT#error:}"
      echo "  ${REPO}: skip (constraint check error: ${ERR})" >&2
      SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
      continue ;;
    *)
      echo "  ${REPO}: skip (unrecognised check_constraint output: ${COMPAT})" >&2
      SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
      continue ;;
  esac

  # All gates passed.
  echo "${REPO}"
  ELIGIBLE_COUNT=$((ELIGIBLE_COUNT + 1))
done <<< "${CANDIDATES}"

echo "" >&2
echo "Discovery complete: ${ELIGIBLE_COUNT} eligible, ${SKIPPED_COUNT} skipped" >&2
