#!/usr/bin/env bash
# build-filters.sh — Clone, build, and optionally push all downstream filter images.
# Called from cloudbuild-cascade.yaml step 4.
#
# Required env vars (passed by Cloud Build):
#   GITHUB_TOKEN, GAR_REGION, GAR_PROJECT, GAR_REPO, DOCKERHUB_ORG, DRY_RUN
# Optional: WORKSPACE (defaults to /workspace for Cloud Build)
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
OF_VERSION=$(cat "${WORKSPACE}/openfilter_version")

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "============================================"
  echo "DRY RUN MODE - builds will NOT be pushed"
  echo "============================================"
fi
echo "Building filters for openfilter ${OF_VERSION}"

# Install Docker CLI + buildx plugin if not already present (cloud-sdk image does not ship them)
if ! command -v docker &>/dev/null; then
  curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
    | tar xz -C /usr/local/bin --strip-components=1 docker/docker
fi
if ! docker buildx version &>/dev/null; then
  mkdir -p /usr/local/lib/docker/cli-plugins
  curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-buildx \
    https://github.com/docker/buildx/releases/download/v0.21.1/buildx-v0.21.1.linux-amd64
  chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
fi
docker version --format 'Docker CLI {{.Client.Version}}'
docker buildx version

# GAR auth must be configured in this step; Docker credentials
# from prior steps are not persisted across Cloud Build containers.
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin "https://${GAR_REGION}-docker.pkg.dev"

# Ensure buildx builder exists (reuse if present from a prior step or local env)
if docker buildx inspect multiarch &>/dev/null; then
  docker buildx use multiarch
else
  docker buildx create --name multiarch --driver docker-container --use
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
echo "GitHub token: ${#GH_PAT} chars, prefix=${GH_PAT:0:4}..."

# Configure git credential helper scoped to github.com only
git config --global credential.https://github.com.helper "!f() { echo \"username=x-access-token\"; echo \"password=${GH_PAT}\"; }; f"

# Validate Python 3.11+ (required for tomllib) and install packaging
python3 -c "import tomllib" 2>/dev/null || {
  echo "ERROR: Python 3.11+ required for tomllib (constraint checking)"
  python3 --version
  exit 1
}
# Create a lightweight venv for packaging dependency
VENV="${WORKSPACE}/.venv"
if command -v uv &>/dev/null; then
  uv venv --quiet "${VENV}"
  uv pip install --quiet --python "${VENV}/bin/python" packaging
else
  python3 -m venv "${VENV}"
  "${VENV}/bin/pip" install --quiet packaging
fi
# Use the venv python for constraint checks
PYTHON="${VENV}/bin/python"

# Fetch repo visibility from GitHub API (one paginated call for all
# filter-* repos). Builds a lookup file: "repo_name visibility" per line.
# Retries up to 3 times; fails the build if it never succeeds.
VISIBILITY_FILE=${WORKSPACE}/results/repo_visibility.txt
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

for REPO in ${FILTER_REPOS}; do
  # Sparse exclude list: suffix-anchored or exact matches only
  SKIP_REPO=false
  case "${REPO}" in
    *-old) SKIP_REPO=true ;;
    filter-template) SKIP_REPO=true ;;
  esac
  if [[ "${SKIP_REPO}" == "true" ]]; then
    echo "Excluding ${REPO} (matches exclude pattern)"
    continue
  fi

  IMAGE="openfilter-${REPO#filter-}"
  VISIBILITY=$(grep "^${REPO} " "${VISIBILITY_FILE}" | awk '{print $2}')
  VISIBILITY=${VISIBILITY:-internal}

  echo ""
  echo "============================================"
  echo "Processing: ${REPO}"
  echo "============================================"

  # Run each filter build in a subshell for error isolation.
  (
    set -euo pipefail

    # Clone the filter repo (token provided via credential helper, not in URL)
    cd ${WORKSPACE}/filters
    if [[ -d "${REPO}" ]]; then
      rm -rf "${REPO}"
    fi

    if [[ -n "${GIT_SSH_COMMAND:-}" ]]; then
      git clone --depth 1 "git@github.com:PlainsightAI/${REPO}.git" "${REPO}"
    else
      git clone --depth 1 "https://github.com/PlainsightAI/${REPO}.git" "${REPO}"
    fi
    cd "${REPO}"

    # --- Auto-detect: skip repos with their own Cloud Build pipeline ---
    if [[ -f cloudbuild.yaml ]]; then
      echo "Skipping ${REPO} - has own cloudbuild.yaml"
      echo "${REPO}: SKIPPED (own cloudbuild)" >> ${WORKSPACE}/results/summary.txt
      touch "${WORKSPACE}/results/.skip_${REPO}"
      exit 0
    fi

    # --- Auto-detect: skip repos without a Dockerfile ---
    if [[ ! -f Dockerfile ]]; then
      echo "Skipping ${REPO} - no Dockerfile"
      echo "${REPO}: SKIPPED (no Dockerfile)" >> ${WORKSPACE}/results/summary.txt
      touch "${WORKSPACE}/results/.skip_${REPO}"
      exit 0
    fi

    # --- Auto-detect: skip repos without a version ---
    FILTER_VERSION=""
    if [[ -f VERSION ]]; then
      FILTER_VERSION=$(tr -d '[:space:]' < VERSION | sed 's/^v//')
    fi
    if [[ -z "${FILTER_VERSION}" ]]; then
      echo "Skipping ${REPO} - no VERSION file"
      echo "${REPO}: SKIPPED (no VERSION)" >> ${WORKSPACE}/results/summary.txt
      touch "${WORKSPACE}/results/.skip_${REPO}"
      exit 0
    fi
    echo "Filter version: ${FILTER_VERSION}"

    # --- Constraint check: skip repos without openfilter dep or incompatible ---
    export OF_VERSION
    COMPAT_RESULT=$("${PYTHON}" "${WORKSPACE}/check_constraint.py" 2>/dev/null || echo "error:python-failed")
    echo "Constraint check: ${COMPAT_RESULT}"

    if [[ "${COMPAT_RESULT}" == "none" ]]; then
      echo "Skipping ${REPO} - no openfilter dependency"
      echo "${REPO}: SKIPPED (no openfilter dep)" >> ${WORKSPACE}/results/summary.txt
      touch "${WORKSPACE}/results/.skip_${REPO}"
      exit 0
    elif [[ "${COMPAT_RESULT}" == error:* ]]; then
      ERROR_MSG=${COMPAT_RESULT#error:}
      echo "ERROR: Constraint check failed for ${REPO}: ${ERROR_MSG}"
      echo "${REPO}: FAILED (constraint check error: ${ERROR_MSG})" >> ${WORKSPACE}/results/summary.txt
      exit 1
    elif [[ "${COMPAT_RESULT}" == skip:* ]]; then
      CONSTRAINT=${COMPAT_RESULT#skip:}
      echo "Constraint ${CONSTRAINT} does not allow ${OF_VERSION}, skipping"
      echo "${REPO}: SKIPPED (constraint: ${CONSTRAINT})" >> ${WORKSPACE}/results/summary.txt
      touch "${WORKSPACE}/results/.skip_${REPO}"
      exit 0
    fi

    # --- Auto-detect build type from Dockerfile ---
    # filter_base: Dockerfile references the filter_base GAR image
    # standard: everything else
    BUILD_TYPE="standard"
    if grep -q 'filter_base' Dockerfile 2>/dev/null; then
      BUILD_TYPE="filter_base"
    fi
    echo "Build type: ${BUILD_TYPE}"

    # Determine push targets based on GitHub API visibility lookup
    GAR_IMAGE="${GAR_REGION}-docker.pkg.dev/${GAR_PROJECT}/${GAR_REPO}/${REPO}"
    DOCKERHUB_IMAGE="${DOCKERHUB_ORG}/${IMAGE}"

    TAGS="-t ${GAR_IMAGE}:${FILTER_VERSION} -t ${GAR_IMAGE}:latest"
    TAGS="${TAGS} -t ${GAR_IMAGE}:${FILTER_VERSION}-of${OF_VERSION}"
    if [[ "${VISIBILITY}" == "public" ]]; then
      echo "Public repo - pushing to DockerHub + GAR"
      TAGS="${TAGS} -t ${DOCKERHUB_IMAGE}:${FILTER_VERSION} -t ${DOCKERHUB_IMAGE}:latest"
    else
      echo "Internal repo - pushing to GAR only"
    fi

    echo "Building ${REPO}:${FILTER_VERSION}"

    # Build args based on detected type
    BUILD_ARGS=""
    BUILD_SECRETS=""
    if [[ "${BUILD_TYPE}" == "filter_base" ]]; then
      RBV=$(cat RESOURCE_BUNDLE_VERSION 2>/dev/null | tr -d '[:space:]' || echo "latest")
      BUILD_ARGS="--build-arg RESOURCE_BUNDLE_VERSION=${RBV}"
      # filter_base ONBUILD mounts secret id=google_credentials for GAR PyPI auth.
      # Generate a short-lived ADC JSON from the current gcloud credentials.
      CRED_FILE="${WORKSPACE}/google_credentials.json"
      gcloud auth application-default print-access-token &>/dev/null && \
        cp "$(gcloud info --format='value(config.paths.global_config_dir)')/application_default_credentials.json" "${CRED_FILE}" 2>/dev/null || \
        python3 -c "
import json, subprocess, sys
token = subprocess.check_output(['gcloud','auth','print-access-token'], text=True).strip()
json.dump({'type':'authorized_user','token':token}, sys.stdout)
" > "${CRED_FILE}"
      BUILD_SECRETS="--secret id=google_credentials,src=${CRED_FILE}"
    fi

    # Refresh GAR auth before build (tokens expire after 1 hour)
    GAR_TOKEN=$(gcloud auth print-access-token)
    echo "${GAR_TOKEN}" | docker login -u oauth2accesstoken --password-stdin "https://${GAR_REGION}-docker.pkg.dev"

    # Build (and push unless dry-run) with registry-based cache
    PUSH_FLAG="--push"
    CACHE_TO="--cache-to type=registry,ref=${GAR_IMAGE}:buildcache"
    PLATFORMS="linux/amd64,linux/arm64"
    if [[ "${DRY_RUN}" == "true" ]]; then
      PUSH_FLAG=""
      CACHE_TO=""
      # Native arch only for dry-run — much faster
      PLATFORMS="linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
    fi
    docker buildx build \
      --platform "${PLATFORMS}" \
      --cache-from type=registry,ref=${GAR_IMAGE}:buildcache \
      ${BUILD_SECRETS} \
      ${CACHE_TO} \
      ${BUILD_ARGS} \
      ${TAGS} \
      ${PUSH_FLAG} \
      .

    if [[ "${DRY_RUN}" == "true" ]]; then
      echo "${REPO}: SUCCESS/DRY-RUN (${FILTER_VERSION})" >> ${WORKSPACE}/results/summary.txt
      echo "Dry-run build succeeded for ${REPO}:${FILTER_VERSION} (not pushed)"
    else
      echo "${REPO}: SUCCESS (${FILTER_VERSION})" >> ${WORKSPACE}/results/summary.txt
      echo "Successfully built and pushed ${REPO}:${FILTER_VERSION}"
    fi
  )
  EXIT_CODE=$?
  if [[ -f "${WORKSPACE}/results/.skip_${REPO}" ]]; then
    # Skip was requested (constraint mismatch or missing VERSION)
    rm -f "${WORKSPACE}/results/.skip_${REPO}"
    continue
  elif [[ ${EXIT_CODE} -ne 0 ]]; then
    # Only write if subshell didn't already record a result
    if ! grep -q "^${REPO}:" ${WORKSPACE}/results/summary.txt 2>/dev/null; then
      echo "${REPO}: FAILED (see error above)" >> ${WORKSPACE}/results/summary.txt || echo "WARNING: Could not write summary for ${REPO}" >&2
    fi
  fi
done

echo ""
echo "============================================"
echo "Build Summary"
echo "============================================"
cat ${WORKSPACE}/results/summary.txt 2>/dev/null || echo "No results recorded"

# Fail the step if any filter builds failed
FAIL_COUNT=$(grep -c ': FAILED' "${WORKSPACE}/results/summary.txt" 2>/dev/null || true)
FAIL_COUNT=${FAIL_COUNT:-0}
SUCCESS_COUNT=$(grep -c ': SUCCESS' "${WORKSPACE}/results/summary.txt" 2>/dev/null || true)
SUCCESS_COUNT=${SUCCESS_COUNT:-0}
if [[ "${DRY_RUN}" == "true" ]]; then
  echo "DRY RUN complete: ${SUCCESS_COUNT} built (not pushed), ${FAIL_COUNT} failed"
else
  echo "Results: ${SUCCESS_COUNT} succeeded, ${FAIL_COUNT} failed"
fi
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo "ERROR: ${FAIL_COUNT} filter(s) failed to build"
  exit 1
fi
