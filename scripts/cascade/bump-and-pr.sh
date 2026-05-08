#!/usr/bin/env bash
# bump-and-pr.sh — Stage a consumer clone for an openfilter bump PR.
# Clones via PAT (GIT_ASKPASS), runs bump-strategy.sh against the clone,
# emits clone_dir / has_changes / commit_message / pr_title / pr_body via
# $GITHUB_OUTPUT for the open-mechanical-pr composite to consume. Does NOT
# push or open the PR — that's the composite's job.
# Args: $1 — consumer repo name (e.g. filter-frame-dedup).
# Required env: GH_BOT_USER_PAT, OF_VERSION. Optional: OF_TAG, GITHUB_OUTPUT.
# DT-145: https://plainsight-ai.atlassian.net/browse/DT-145
set -euo pipefail

REPO="${1:?usage: bump-and-pr.sh <consumer-repo>}"

: "${OF_VERSION:?OF_VERSION must be set (bare semver, e.g. 0.1.28)}"
: "${GH_BOT_USER_PAT:?GH_BOT_USER_PAT must be set}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUMP_STRATEGY="${SCRIPT_DIR}/bump-strategy.sh"

# Helper to set workflow outputs. Falls back to stdout when run outside
# Actions (e.g. `make` smoke tests).
set_output() {
  local key="$1"
  local value="$2"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    # Multi-line-safe via heredoc delimiter.
    {
      printf '%s<<__BUMP_AND_PR_EOF__\n' "${key}"
      printf '%s\n' "${value}"
      printf '__BUMP_AND_PR_EOF__\n'
    } >> "${GITHUB_OUTPUT}"
  else
    printf '%s=%s\n' "${key}" "${value}"
  fi
}

# CLONE_DIR survives past this script on success so the next workflow step
# can read it; ASKPASS is always temporary. Both go through the EXIT trap so
# a `git clone` failure can't leave the PAT-bearing askpass file behind.
TEMP_BASE="${RUNNER_TEMP:-/tmp}"
CLONE_DIR=$(mktemp -d "${TEMP_BASE}/cascade-${REPO}.XXXXXX")
ASKPASS=$(mktemp "${TEMP_BASE}/cascade-askpass.XXXXXX")
ONFAIL_CLEANUP=true

cleanup() {
  rm -f "${ASKPASS}"
  if [[ "${ONFAIL_CLEANUP}" == "true" ]]; then
    rm -rf "${CLONE_DIR}"
  fi
}
trap cleanup EXIT

echo "Cloning PlainsightAI/${REPO} → ${CLONE_DIR}"
# GIT_ASKPASS keeps the PAT out of subprocess argv (where ACTIONS_STEP_DEBUG
# would otherwise log it). x-access-token is GitHub's PAT username convention.
chmod 700 "${ASKPASS}"
cat > "${ASKPASS}" <<'ASKPASS_SH'
#!/usr/bin/env bash
case "$1" in
  Username*) printf 'x-access-token\n' ;;
  Password*) printf '%s\n' "${GH_BOT_USER_PAT}" ;;
esac
ASKPASS_SH
GIT_ASKPASS="${ASKPASS}" GIT_TERMINAL_PROMPT=0 \
  git clone --depth 1 "https://github.com/PlainsightAI/${REPO}.git" "${CLONE_DIR}"

echo "Running bump-strategy.sh against ${CLONE_DIR}"
(
  cd "${CLONE_DIR}"
  OF_VERSION="${OF_VERSION}" bash "${BUMP_STRATEGY}"
)

# `git status --porcelain` (not `git diff --quiet`) so a fresh untracked
# RELEASE.md created by bump-strategy still counts as a change.
HAS_CHANGES=false
if (cd "${CLONE_DIR}" && [[ -n "$(git status --porcelain)" ]]); then
  HAS_CHANGES=true
fi
echo "has_changes=${HAS_CHANGES}"

if [[ "${HAS_CHANGES}" != "true" ]]; then
  echo "No working-tree changes for ${REPO} — already on openfilter ${OF_VERSION}, skipping PR."
  set_output "has_changes" "false"
  set_output "clone_dir" "${CLONE_DIR}"
  ONFAIL_CLEANUP=false
  exit 0
fi

COMMIT_MSG="chore(deps): bump openfilter to ${OF_VERSION}"

PR_TITLE="${COMMIT_MSG}"

OF_TAG_REF="${OF_TAG:-v${OF_VERSION}}"
PR_BODY=$(cat <<EOF
Mechanical bump of \`openfilter\` to [\`${OF_TAG_REF}\`](https://github.com/PlainsightAI/openfilter/releases/tag/${OF_TAG_REF}).

Updates:
- \`pyproject.toml\` openfilter pin
- \`requirements*.txt\` openfilter pin (if present)
- \`RELEASE.md\` adds a \`### Changed\` entry

Auto-merge is enabled. PR will land once required status checks pass (including the \`dry-run-publish\` build verification, see [DT-146](https://plainsight-ai.atlassian.net/browse/DT-146)).

Cascaded from openfilter [\`${OF_TAG_REF}\`](https://github.com/PlainsightAI/openfilter/releases/tag/${OF_TAG_REF}). Tracking: [DT-145](https://plainsight-ai.atlassian.net/browse/DT-145).
EOF
)

set_output "has_changes" "true"
set_output "clone_dir" "${CLONE_DIR}"
set_output "commit_message" "${COMMIT_MSG}"
set_output "pr_title" "${PR_TITLE}"
set_output "pr_body" "${PR_BODY}"

echo "Prepared bump for ${REPO} → openfilter ${OF_VERSION}"
ONFAIL_CLEANUP=false
