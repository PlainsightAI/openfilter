#!/usr/bin/env bash
# discover.sh — List PlainsightAI/filter-* repos eligible to receive an
# openfilter ${OF_VERSION} bump PR. Eligible repo names → stdout (one per
# line); skip-reason diagnostics → stderr. Eligibility checks, in body
# order (cheapest first):
#   1. `filter-*` name and not on the static exclude list
#   2. No `.github/no-cascade-openfilter` opt-out marker
#   3. Has a VERSION file at the default branch tip
#   4. Declares an `openfilter` PEP 621 dependency whose constraint allows
#      ${OF_VERSION} (delegated to scripts/cascade/check_constraint.py)
# Required env: OF_VERSION (bare semver), GH_TOKEN (plainsight-bot PAT).
# Optional env: SINGLE_FILTER (precedes), FILTER_SUBSET (comma-separated).
# Note: SINGLE_FILTER not-found hard-exits — behavior change vs build-filters.sh,
# which warned and fell through to all filters.
# DT-145: https://plainsight-ai.atlassian.net/browse/DT-145
set -euo pipefail

: "${OF_VERSION:?OF_VERSION must be set (bare semver, e.g. 0.1.28)}"
: "${GH_TOKEN:?GH_TOKEN must be set (plainsight-bot PAT)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_CONSTRAINT_PY="${SCRIPT_DIR}/check_constraint.py"

# Excludes: *-old (superseded), filter-template (cookiecutter source), and
# the named repos which still hold unrendered Jinja placeholders from a
# pre-templatize fork. Re-enable individually as each gets templatized.
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

# Phase 1: list candidates. --limit 1000 over-fetches against the ~150-repo
# org so we don't have to paginate manually.
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

# Phase 3: per-repo eligibility checks. fetch_file fetches a file via the
# Contents API (3 calls per repo, no clone). Returns 0 with body on stdout,
# 1 silently on 404, 1 with a `::warning::` annotation on transient errors.
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

  # 2. Opt-out marker.
  if fetch_file "${REPO}" ".github/no-cascade-openfilter" >/dev/null; then
    echo "  ${REPO}: skip (.github/no-cascade-openfilter marker present)" >&2
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  # 3. VERSION sanity check (presence only — the bump PR doesn't touch it).
  if ! fetch_file "${REPO}" "VERSION" >/dev/null; then
    echo "  ${REPO}: skip (no VERSION file)" >&2
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  # 4. Constraint compatibility — check_constraint.py reads pyproject from CWD.
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
    none:poetry-format)
      echo "  ${REPO}: skip (uses Poetry [tool.poetry.dependencies] — cascade reads PEP 621 [project.dependencies] only)" >&2
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
