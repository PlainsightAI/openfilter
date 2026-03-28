#!/usr/bin/env bash
# build-filters.sh — Clone, build, and optionally push all downstream filter images.
# Called from cloudbuild-cascade.yaml step 4.
#
# Required env vars (passed by Cloud Build):
#   GITHUB_TOKEN, GAR_REGION, GAR_PROJECT, GAR_REPO, DOCKERHUB_ORG, DRY_RUN
# Optional: WORKSPACE (defaults to /workspace for Cloud Build)
#           DOCKERHUB_USERNAME, DOCKERHUB_TOKEN (for public-repo pushes)
#           SINGLE_FILTER (limit to one filter for testing)
#           FILTER_SUBSET (comma-separated list of filters to build)
#           MAX_PARALLEL (concurrent builds, default 4)
#           FAIL_IS_ERROR (exit 1 on filter failures, default true)
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
OF_VERSION=$(cat "${WORKSPACE}/openfilter_version")
MAX_PARALLEL="${MAX_PARALLEL:-4}"

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "============================================"
  echo "DRY RUN MODE - builds will NOT be pushed"
  echo "============================================"
fi
echo "Building filters for openfilter ${OF_VERSION}"

# Pinned tool versions (bump as needed)
DOCKER_VERSION="${DOCKER_VERSION:-27.5.1}"
BUILDX_VERSION="${BUILDX_VERSION:-0.21.1}"

# Install Docker CLI + buildx plugin if not already present (cloud-sdk image does not ship them)
if ! command -v docker &>/dev/null; then
  curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" \
    | tar xz -C /usr/local/bin --strip-components=1 docker/docker
fi
if ! docker buildx version &>/dev/null; then
  mkdir -p /usr/local/lib/docker/cli-plugins
  curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-buildx \
    "https://github.com/docker/buildx/releases/download/v${BUILDX_VERSION}/buildx-v${BUILDX_VERSION}.linux-amd64"
  chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
fi
docker version --format 'Docker CLI {{.Client.Version}}'
docker buildx version

# Registry auth is only needed for pushes (non-dry-run).
if [[ "${DRY_RUN}" != "true" ]]; then
  # GAR auth — the cloud-sdk image does not inherit Docker credentials from prior steps' images.
  gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin "https://${GAR_REGION}-docker.pkg.dev"

  # DockerHub auth (needed for public-repo pushes)
  if [[ -n "${DOCKERHUB_TOKEN:-}" && -n "${DOCKERHUB_USERNAME:-}" ]]; then
    echo "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin
  fi

  # Issue 2 fix: replace the credential-file approach with a raw access token.
  # The previous fallback generated {"type":"authorized_user","token":"ya29.xxx"}
  # which is invalid — google-auth's authorized_user type requires client_id,
  # client_secret, and refresh_token (not a raw access token). In Cloud Build
  # there is no ADC file, so the fallback always ran and always failed.
  # The token is passed as --build-arg GAR_TOKEN to filter_base builds.
  # NOTE: Dockerfile.filter_base in filter-runtime must be updated to declare
  #   ONBUILD ARG GAR_TOKEN
  # and replace the --mount=type=secret pip call with:
  #   --extra-index-url https://oauth2accesstoken:${GAR_TOKEN}@us-west1-python.pkg.dev/plainsightai-prod/python/simple
  # Done once here to avoid concurrent gcloud calls from parallel workers.
  GAR_ACCESS_TOKEN=$(gcloud auth print-access-token)
fi

# Issue 1 fix: always destroy and recreate the buildx builder AFTER docker login.
# The docker-container driver bakes the Docker config (including credentials) into
# the BuildKit container at creation time. A pre-existing builder created before
# docker login (e.g. cloudbuild-cascade.yaml Step 3) would NOT have GAR or
# DockerHub credentials — it would get 401 on every push. Recreating here ensures
# the builder inherits the freshly-written config.json with both registries.
if [[ "${DRY_RUN}" != "true" ]]; then
  docker buildx rm multiarch 2>/dev/null || true
  docker buildx create --name multiarch --driver docker-container --use
else
  # Dry-run: no push, no registry credentials needed — reuse if present.
  docker buildx inspect multiarch &>/dev/null || \
    docker buildx create --name multiarch --driver docker-container --use
  docker buildx use multiarch
fi
docker buildx inspect --bootstrap

# Extract PAT from secret (may be JSON {"password":"ghp_..."} or bare token)
GH_PAT=$(python3 -c "
import json, sys
raw = '''${GITHUB_TOKEN}'''
try:
    data = json.loads(raw)
    print(data.get('password', raw))
except (json.JSONDecodeError, TypeError):
    print(raw)
")
echo "GitHub token: sha256:$(echo -n "${GH_PAT}" | sha256sum | cut -c1-12)..."

# Configure git credential helper scoped to github.com only
git config --global credential.https://github.com.helper "!f() { echo \"username=x-access-token\"; echo \"password=${GH_PAT}\"; }; f"

# Validate Python 3.11+ (required for tomllib) and install packaging
python3 -c "import tomllib" 2>/dev/null || {
  echo "ERROR: Python 3.11+ required for tomllib (constraint checking)"
  python3 --version
  exit 1
}
# Install uv if not present (fast, no system deps needed)
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Create a lightweight venv for packaging dependency
VENV="${WORKSPACE}/.venv"
uv venv --quiet "${VENV}"
uv pip install --quiet --python "${VENV}/bin/python" packaging
# Use the venv python for constraint checks
PYTHON="${VENV}/bin/python"

# Fetch repo visibility from GitHub API (one paginated call for all
# filter-* repos). Builds a lookup file: "repo_name visibility" per line.
# Retries up to 3 times; falls back to hardcoded list if all fail.
VISIBILITY_FILE="${WORKSPACE}/results/repo_visibility.txt"
for ATTEMPT in 1 2 3; do
  echo "Fetching repo visibility from GitHub API (attempt ${ATTEMPT}/3)..."
  NEXT_URL="https://api.github.com/orgs/PlainsightAI/repos?per_page=100"
  > "${VISIBILITY_FILE}"
  FETCH_OK=true
  while [[ -n "${NEXT_URL}" ]]; do
    RESPONSE=$(curl -sS --fail-with-body --http1.1 \
      -H "Authorization: token ${GH_PAT}" \
      -H "Accept: application/vnd.github+json" \
      -D /tmp/gh_headers \
      "${NEXT_URL}") || { FETCH_OK=false; break; }
    echo "${RESPONSE}" | "${PYTHON}" -c "import json,sys; [print(r['name'],r.get('visibility','internal')) for r in json.load(sys.stdin)]" >> "${VISIBILITY_FILE}" || { FETCH_OK=false; break; }
    # Follow pagination Link header
    NEXT_URL=$(grep -oi '<[^>]*>; rel="next"' /tmp/gh_headers | sed 's/<\(.*\)>; rel="next"/\1/' || true)
  done
  if [[ "${FETCH_OK}" == "true" ]] && [[ -s "${VISIBILITY_FILE}" ]]; then
    echo "Fetched visibility for $(wc -l < "${VISIBILITY_FILE}") repos"
    break
  fi
  echo "WARNING: GitHub API fetch failed (attempt ${ATTEMPT})"
  sleep 5
done
if [[ ! -s "${VISIBILITY_FILE}" ]]; then
  echo "WARNING: GitHub API unavailable, falling back to hardcoded filter list"
  cat > "${VISIBILITY_FILE}" <<'FALLBACK'
filter-json-transform internal
filter-frame-selector internal
FALLBACK
fi

# Auto-discover filter-* repos from the visibility API response.
# DockerHub image name: openfilter-${repo#filter-} (enforced convention).
# Build type is detected from repo contents after cloning.
# Visibility is looked up from the API response above.
#
# Sparse exclude list for repos that should never be rebuilt here:
#   -old suffix  - superseded by newer version
#   -template    - cookiecutter templates, not buildable
FILTER_REPOS=$(awk '{print $1}' "${VISIBILITY_FILE}" | grep '^filter-' | sort)
TOTAL_REPOS=$(wc -l < "${VISIBILITY_FILE}")
FILTER_COUNT=$(echo "${FILTER_REPOS}" | wc -w)
echo "Discovered ${TOTAL_REPOS} repos (${FILTER_COUNT} filters)"

# Optional: limit to a single filter (takes precedence) or a subset
if [[ -n "${SINGLE_FILTER:-}" ]]; then
  if echo "${FILTER_REPOS}" | grep -Fqx "${SINGLE_FILTER}"; then
    echo "Single-filter mode: ${SINGLE_FILTER}"
    FILTER_REPOS="${SINGLE_FILTER}"
  else
    echo "WARNING: Filter '${SINGLE_FILTER}' not found in discovered repos, ignoring"
  fi
elif [[ -n "${FILTER_SUBSET:-}" ]]; then
  echo "Subset mode: ${FILTER_SUBSET}"
  SUBSET_LIST=""
  SUBSET_MISSING=""
  IFS=',' read -ra SUBSET_ITEMS <<< "${FILTER_SUBSET}"
  for ITEM in "${SUBSET_ITEMS[@]}"; do
    ITEM=$(echo "${ITEM}" | xargs)  # trim whitespace
    if [[ -z "${ITEM}" ]]; then continue; fi
    if echo "${FILTER_REPOS}" | tr ' ' '\n' | grep -Fqx "${ITEM}"; then
      SUBSET_LIST="${SUBSET_LIST:+${SUBSET_LIST} }${ITEM}"
    else
      SUBSET_MISSING="${SUBSET_MISSING:+${SUBSET_MISSING}, }${ITEM}"
    fi
  done
  if [[ -n "${SUBSET_MISSING}" ]]; then
    echo "WARNING: Filter(s) not found in discovered repos: ${SUBSET_MISSING}"
  fi
  if [[ -n "${SUBSET_LIST}" ]]; then
    FILTER_REPOS="${SUBSET_LIST}"
  else
    echo "ERROR: No filters from subset found in discovered repos, aborting"
    echo "Available filters:"
    echo "${FILTER_REPOS}" | tr ' ' '\n' | sed 's/^/  /'
    exit 1
  fi
fi

# Apply exclude list
ELIGIBLE_REPOS=""
for REPO in ${FILTER_REPOS}; do
  case "${REPO}" in
    *-old|filter-template|\
    filter-mocktext|filter-timescaledb|filter-pytorch-model|\
    filter-florence|filter-pytorch|filter-facedetector|\
    filter-nov-pilot|filter-tracking-reid)
      # Issue 3 fix (Fix A): explicitly exclude repos where templatize was never
      # run. Their Dockerfiles still contain {{REPO_NAME_KEBABCASE}} in FROM lines,
      # which BuildKit rejects as "invalid reference format". These repos will be
      # re-enabled once their templatize scripts have been run and merged.
      echo "Excluding ${REPO} (matches exclude pattern or unrendered template)"
      continue ;;
  esac
  ELIGIBLE_REPOS="${ELIGIBLE_REPOS:+${ELIGIBLE_REPOS} }${REPO}"
done
FILTER_REPOS="${ELIGIBLE_REPOS}"
echo "Eligible filters: $(echo "${FILTER_REPOS}" | wc -w)"

# ============================================================
# Phase 1: Parallel clone
# ============================================================
echo ""
echo "============================================"
echo "Phase 1: Cloning filter repos (parallel)"
echo "============================================"
CLONE_PIDS=()
for REPO in ${FILTER_REPOS}; do
  (
    cd "${WORKSPACE}/filters"
    rm -rf "${REPO}"
    if [[ -n "${GIT_SSH_COMMAND:-}" ]]; then
      git clone --depth 1 "git@github.com:PlainsightAI/${REPO}.git" "${REPO}" 2>&1
    else
      git clone --depth 1 "https://github.com/PlainsightAI/${REPO}.git" "${REPO}" 2>&1
    fi
    echo "Cloned ${REPO}"
  ) &
  CLONE_PIDS+=($!)
done
# Wait for all clones, note failures
CLONE_FAILED=""
for i in "${!CLONE_PIDS[@]}"; do
  REPO=$(echo "${FILTER_REPOS}" | tr ' ' '\n' | sed -n "$((i+1))p")
  if ! wait "${CLONE_PIDS[$i]}"; then
    echo "WARNING: Failed to clone ${REPO}"
    CLONE_FAILED="${CLONE_FAILED:+${CLONE_FAILED} }${REPO}"
    echo "${REPO}: FAILED (clone)" >> "${WORKSPACE}/results/summary.txt"
  fi
done

# ============================================================
# Phase 2: Pre-flight checks (fast, sequential — mostly stat/grep)
# ============================================================
echo ""
echo "============================================"
echo "Phase 2: Pre-flight checks"
echo "============================================"
BUILD_LIST=""
for REPO in ${FILTER_REPOS}; do
  # Skip repos that failed to clone
  if echo "${CLONE_FAILED}" | tr ' ' '\n' | grep -qx "${REPO}" 2>/dev/null; then
    continue
  fi

  FILTER_DIR="${WORKSPACE}/filters/${REPO}"
  if [[ ! -d "${FILTER_DIR}" ]]; then
    echo "${REPO}: FAILED (clone directory missing)" >> "${WORKSPACE}/results/summary.txt"
    continue
  fi
  cd "${FILTER_DIR}"

  # Skip repos with their own Cloud Build pipeline
  if [[ -f cloudbuild.yaml ]]; then
    echo "  ${REPO}: skip (own cloudbuild.yaml)"
    echo "${REPO}: SKIPPED (own cloudbuild)" >> "${WORKSPACE}/results/summary.txt"
    continue
  fi

  # Skip repos without a Dockerfile
  if [[ ! -f Dockerfile ]]; then
    echo "  ${REPO}: skip (no Dockerfile)"
    echo "${REPO}: SKIPPED (no Dockerfile)" >> "${WORKSPACE}/results/summary.txt"
    continue
  fi

  # Issue 3 fix (Fix C): skip repos with unrendered Jinja template placeholders.
  # {{REPO_NAME_KEBABCASE}} in a FROM line causes BuildKit "invalid reference format"
  # immediately. This check catches any future repo that skips templatize, beyond
  # the explicit exclude list above.
  if grep -q '{{' Dockerfile 2>/dev/null; then
    echo "  ${REPO}: skip (unresolved template placeholders in Dockerfile)"
    echo "${REPO}: SKIPPED (unrendered template)" >> "${WORKSPACE}/results/summary.txt"
    continue
  fi

  # Skip repos without a version
  FILTER_VERSION=""
  if [[ -f VERSION ]]; then
    FILTER_VERSION=$(tr -d '[:space:]' < VERSION | sed 's/^v//')
  fi
  if [[ -z "${FILTER_VERSION}" ]]; then
    echo "  ${REPO}: skip (no VERSION)"
    echo "${REPO}: SKIPPED (no VERSION)" >> "${WORKSPACE}/results/summary.txt"
    continue
  fi

  # Constraint check
  export OF_VERSION
  COMPAT_RESULT=$("${PYTHON}" "${WORKSPACE}/check_constraint.py" 2>/dev/null || echo "error:python-failed")

  if [[ "${COMPAT_RESULT}" == "none" ]]; then
    echo "  ${REPO}: skip (no openfilter dep)"
    echo "${REPO}: SKIPPED (no openfilter dep)" >> "${WORKSPACE}/results/summary.txt"
    continue
  elif [[ "${COMPAT_RESULT}" == error:* ]]; then
    ERROR_MSG=${COMPAT_RESULT#error:}
    echo "  ${REPO}: FAILED (constraint: ${ERROR_MSG})"
    echo "${REPO}: FAILED (constraint check error: ${ERROR_MSG})" >> "${WORKSPACE}/results/summary.txt"
    continue
  elif [[ "${COMPAT_RESULT}" == skip:* ]]; then
    CONSTRAINT=${COMPAT_RESULT#skip:}
    echo "  ${REPO}: skip (constraint ${CONSTRAINT})"
    echo "${REPO}: SKIPPED (constraint: ${CONSTRAINT})" >> "${WORKSPACE}/results/summary.txt"
    continue
  fi

  echo "  ${REPO}: eligible (${FILTER_VERSION}, ${COMPAT_RESULT})"
  BUILD_LIST="${BUILD_LIST:+${BUILD_LIST} }${REPO}"
done

BUILD_COUNT=$(echo "${BUILD_LIST}" | wc -w)
echo "Eligible for build: ${BUILD_COUNT} filters"

if [[ ${BUILD_COUNT} -eq 0 ]]; then
  echo "No filters to build"
else
  # ============================================================
  # Phase 3: Parallel builds
  # ============================================================
  echo ""
  echo "============================================"
  echo "Phase 3: Building filters (${MAX_PARALLEL} parallel)"
  echo "============================================"

  # build_one_filter <repo>
  # Runs in a subshell. Writes result to summary file. Cleans up clone after.
  build_one_filter() {
    local REPO="$1"
    local FILTER_DIR="${WORKSPACE}/filters/${REPO}"
    local IMAGE="openfilter-${REPO#filter-}"
    local VISIBILITY
    VISIBILITY=$(grep "^${REPO} " "${VISIBILITY_FILE}" | awk '{print $2}')
    VISIBILITY=${VISIBILITY:-internal}

    cd "${FILTER_DIR}"

    local FILTER_VERSION
    FILTER_VERSION=$(tr -d '[:space:]' < VERSION | sed 's/^v//')

    # Detect build type
    local BUILD_TYPE="standard"
    if grep -qE 'FROM.*filter_base' Dockerfile 2>/dev/null; then
      BUILD_TYPE="filter_base"
    fi

    # Determine push targets
    local GAR_IMAGE="${GAR_REGION}-docker.pkg.dev/${GAR_PROJECT}/${GAR_REPO}/${REPO}"
    local DOCKERHUB_IMAGE="${DOCKERHUB_ORG}/${IMAGE}"

    local TAGS="-t ${GAR_IMAGE}:${FILTER_VERSION} -t ${GAR_IMAGE}:latest"
    TAGS="${TAGS} -t ${GAR_IMAGE}:${FILTER_VERSION}-of${OF_VERSION}"
    if [[ "${VISIBILITY}" == "public" ]]; then
      TAGS="${TAGS} -t ${DOCKERHUB_IMAGE}:${FILTER_VERSION} -t ${DOCKERHUB_IMAGE}:latest"
    fi

    # Build args
    local BUILD_ARGS=""
    local BUILD_SECRETS=""
    if [[ "${BUILD_TYPE}" == "filter_base" ]]; then
      local RBV
      RBV=$(cat RESOURCE_BUNDLE_VERSION 2>/dev/null | tr -d '[:space:]' || echo "latest")
      BUILD_ARGS="--build-arg RESOURCE_BUNDLE_VERSION=${RBV}"
      # Issue 2 fix: pass the GAR access token as a build arg instead of a
      # credential file. The credential-file approach always fell through to
      # an invalid authorized_user JSON in Cloud Build. Dockerfile.filter_base
      # must be updated to use ARG GAR_TOKEN and inline the token in the pip
      # index URL (see the GAR_ACCESS_TOKEN comment block above for details).
      if [[ -n "${GAR_ACCESS_TOKEN:-}" ]]; then
        BUILD_ARGS="${BUILD_ARGS} --build-arg GAR_TOKEN=${GAR_ACCESS_TOKEN}"
      fi
    fi

    # Push and cache flags
    local PUSH_FLAG="--push"
    local CACHE_FROM="--cache-from type=registry,ref=${GAR_IMAGE}:buildcache"
    local CACHE_TO="--cache-to type=registry,ref=${GAR_IMAGE}:buildcache"
    local PLATFORMS="linux/amd64,linux/arm64"
    if [[ "${DRY_RUN}" == "true" ]]; then
      PUSH_FLAG=""
      CACHE_FROM=""
      CACHE_TO=""
      PLATFORMS="linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
    fi

    # Refresh GAR auth before build (tokens expire after 1 hour)
    if [[ "${DRY_RUN}" != "true" ]]; then
      gcloud auth print-access-token \
        | docker login -u oauth2accesstoken --password-stdin "https://${GAR_REGION}-docker.pkg.dev" 2>/dev/null
    fi

    local LOG_FILE="${WORKSPACE}/results/${REPO}.log"
    echo "[${REPO}] Building ${BUILD_TYPE} ${FILTER_VERSION} (${VISIBILITY})"
    docker buildx build \
      --platform "${PLATFORMS}" \
      ${CACHE_FROM} \
      ${BUILD_SECRETS} \
      ${CACHE_TO} \
      ${BUILD_ARGS} \
      ${TAGS} \
      ${PUSH_FLAG} \
      . > "${LOG_FILE}" 2>&1

    if [[ "${DRY_RUN}" == "true" ]]; then
      echo "${REPO}: SUCCESS/DRY-RUN (${FILTER_VERSION})" >> "${WORKSPACE}/results/summary.txt"
      echo "[${REPO}] Dry-run build succeeded"
    else
      echo "${REPO}: SUCCESS (${FILTER_VERSION})" >> "${WORKSPACE}/results/summary.txt"
      echo "[${REPO}] Built and pushed ${FILTER_VERSION}"
    fi

    # Clean up clone to free disk
    rm -rf "${FILTER_DIR}"
  }
  export -f build_one_filter
  export WORKSPACE VISIBILITY_FILE OF_VERSION GAR_REGION GAR_PROJECT GAR_REPO
  export DOCKERHUB_ORG DRY_RUN PYTHON GAR_ACCESS_TOKEN

  # Run builds in parallel, capping concurrency
  ACTIVE_PIDS=()
  ACTIVE_REPOS=()
  for REPO in ${BUILD_LIST}; do
    # If at max concurrency, wait for one to finish
    while [[ ${#ACTIVE_PIDS[@]} -ge ${MAX_PARALLEL} ]]; do
      # Wait for any one child
      DONE=false
      for i in "${!ACTIVE_PIDS[@]}"; do
        if ! kill -0 "${ACTIVE_PIDS[$i]}" 2>/dev/null; then
          wait "${ACTIVE_PIDS[$i]}" || {
            R="${ACTIVE_REPOS[$i]}"
            if ! grep -q "^${R}:" "${WORKSPACE}/results/summary.txt" 2>/dev/null; then
              echo "${R}: FAILED (see ${WORKSPACE}/results/${R}.log)" >> "${WORKSPACE}/results/summary.txt"
            fi
          }
          unset 'ACTIVE_PIDS[i]' 'ACTIVE_REPOS[i]'
          # Re-pack arrays
          ACTIVE_PIDS=("${ACTIVE_PIDS[@]}")
          ACTIVE_REPOS=("${ACTIVE_REPOS[@]}")
          DONE=true
          break
        fi
      done
      if [[ "${DONE}" != "true" ]]; then
        sleep 1
      fi
    done

    build_one_filter "${REPO}" &
    ACTIVE_PIDS+=($!)
    ACTIVE_REPOS+=("${REPO}")
  done

  # Wait for remaining builds
  for i in "${!ACTIVE_PIDS[@]}"; do
    wait "${ACTIVE_PIDS[$i]}" || {
      R="${ACTIVE_REPOS[$i]}"
      if ! grep -q "^${R}:" "${WORKSPACE}/results/summary.txt" 2>/dev/null; then
        echo "${R}: FAILED (see error above)" >> "${WORKSPACE}/results/summary.txt"
      fi
    }
  done
fi

# Clean up any remaining clones
rm -rf "${WORKSPACE}/filters"

echo ""
echo "============================================"
echo "Build Summary"
echo "============================================"
cat "${WORKSPACE}/results/summary.txt" 2>/dev/null || echo "No results recorded"

FAIL_COUNT=$(grep -c ': FAILED' "${WORKSPACE}/results/summary.txt" 2>/dev/null || true)
FAIL_COUNT=${FAIL_COUNT:-0}
SUCCESS_COUNT=$(grep -c ': SUCCESS' "${WORKSPACE}/results/summary.txt" 2>/dev/null || true)
SUCCESS_COUNT=${SUCCESS_COUNT:-0}
if [[ "${DRY_RUN}" == "true" ]]; then
  echo "DRY RUN complete: ${SUCCESS_COUNT} built (not pushed), ${FAIL_COUNT} failed"
else
  echo "Results: ${SUCCESS_COUNT} succeeded, ${FAIL_COUNT} failed"
fi

# Dump the last 30 lines of each failed build's log
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo ""
  echo "============================================"
  echo "Failed build logs"
  echo "============================================"
  grep ': FAILED' "${WORKSPACE}/results/summary.txt" | while IFS=: read -r REPO _; do
    LOG="${WORKSPACE}/results/${REPO}.log"
    if [[ -f "${LOG}" ]]; then
      echo "--- ${REPO} (last 30 lines) ---"
      tail -30 "${LOG}"
      echo ""
    fi
  done

  FAIL_IS_ERROR="${FAIL_IS_ERROR:-true}"
  if [[ "${FAIL_IS_ERROR}" == "true" ]]; then
    echo "ERROR: ${FAIL_COUNT} filter(s) failed to build"
    exit 1
  else
    echo "WARNING: ${FAIL_COUNT} filter(s) failed to build (non-fatal)"
  fi
fi
