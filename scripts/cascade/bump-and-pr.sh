#!/usr/bin/env bash
# bump-and-pr.sh — Prepare a single consumer's clone for a mechanical
# openfilter bump PR.
#
# Per the DT-145 design (https://plainsight-ai.atlassian.net/browse/DT-145):
#   1. Clone the consumer's default branch into a temp dir using
#      ${GH_BOT_USER_PAT} for HTTPS auth.
#   2. Run scripts/cascade/bump-strategy.sh against the clone, mutating
#      VERSION dependency pins / RELEASE.md in place.
#   3. Emit the clone path + commit/PR text via $GITHUB_OUTPUT so the
#      workflow's next step can hand it to the open-mechanical-pr@main
#      composite action (which performs supersede-stale, push, gh pr create,
#      and gh pr merge --auto).
#
# This script does NOT push or open a PR itself — that's the composite
# action's job. It also does NOT call the composite action directly (bash
# can't invoke a composite action mid-script); it just stages the clone.
#
# Required env:
#   GH_BOT_USER_PAT   plainsight-bot PAT for HTTPS clone
#   OF_VERSION        bare semver (e.g. 0.1.28) of the new openfilter release
#   GITHUB_OUTPUT     written to by GitHub Actions runners; if unset (e.g.
#                     local dev) outputs go to stdout in KEY=VALUE form
# Optional:
#   OF_TAG            the tag name (e.g. v0.1.28); used in PR body links
#
# Args:
#   $1 — consumer repo name (e.g. filter-frame-selector)
#
# Cleans up the temp dir on exit only on failure — on success the clone has
# to survive past this script so the open-mechanical-pr step can read it.
# The Actions runner reaps the dir at job-end either way.
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

# Make a fresh tempdir under $RUNNER_TEMP when available so the next workflow
# step can read it via the matrix shard's filesystem. Outside Actions, fall
# back to /tmp.
TEMP_BASE="${RUNNER_TEMP:-/tmp}"
CLONE_DIR=$(mktemp -d "${TEMP_BASE}/cascade-${REPO}.XXXXXX")
ONFAIL_CLEANUP=true

cleanup() {
  if [[ "${ONFAIL_CLEANUP}" == "true" ]]; then
    rm -rf "${CLONE_DIR}"
  fi
}
trap cleanup EXIT

echo "Cloning PlainsightAI/${REPO} → ${CLONE_DIR}"
# Authenticate via GIT_ASKPASS rather than embedding the PAT in the clone
# URL — that way the PAT never appears in any subprocess argv that an
# ACTIONS_STEP_DEBUG=true runner would log. x-access-token is the standard
# PAT username for GitHub HTTPS auth.
ASKPASS=$(mktemp "${TEMP_BASE}/cascade-askpass.XXXXXX")
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
rm -f "${ASKPASS}"

echo "Running bump-strategy.sh against ${CLONE_DIR}"
(
  cd "${CLONE_DIR}"
  OF_VERSION="${OF_VERSION}" bash "${BUMP_STRATEGY}"
)

# Detect whether the bump strategy produced any working-tree changes.
# Idempotent re-runs (consumer already on the new version) yield no diff —
# in that case we skip the PR step entirely so we don't churn empty PRs.
#
# We use `git status --porcelain` rather than `git diff --quiet` because the
# bump strategy can create a brand-new RELEASE.md when the consumer has
# none yet; that file is *untracked* and `git diff --quiet` only inspects
# the index/working-tree of *tracked* files, so it would return clean and
# silently drop the bump.
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

# Build commit and PR text. Kept short and uniform across consumers — these
# are mechanical bump PRs, not feature PRs. The Jira reference in the body
# follows the convention from CLAUDE.md (Jira links over PR numbers).
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
