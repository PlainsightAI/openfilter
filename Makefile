VERSION ?= $(shell cat VERSION)

GCP_PROJECT    := plainsightai-dev
CLOUDBUILD_SA  := cloudbuild-dev@$(GCP_PROJECT).iam.gserviceaccount.com
SINGLE_FILTER  ?=
FILTER_SUBSET  ?=

export VERSION

.PHONY: help
help:
	@grep -E '^[a-zA-Z_.-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'


.PHONY: build-wheel
build-wheel:  ## Build python wheel
	python -m build --wheel


.PHONY: test
test:  ## Run basic unit tests
	pytest -v --cov=tests -s tests --benchmark-disable -m "not slow"

.PHONY: bench
bench:  ## Run performance benchmarks
	pytest tests/test_benchmarks.py -v --benchmark-group-by=group -s --benchmark-max-time=0.5

.PHONY: test-integration
test-integration:  ## Run integration tests (requires a running docker daemon)
	pytest -v tests/integration/ --benchmark-disable -m slow
# ─── IPC perf waterfall (demo scaffolding) ───────────────────────────────
#
# The waterfall display runs the bench's pipeline_simulation scenarios
# at two git refs and renders a terminal before/after. The baseline ref
# is materialized as an ephemeral git worktree under /tmp and torn down
# after measurement.
#
#   make waterfall                                  # HEAD vs origin/main
#   make waterfall WATERFALL_ARGS="--frames 400"    # longer run
#   make waterfall WATERFALL_ARGS="--baseline-ref feat/perf-fixes"
#   make waterfall WATERFALL_ARGS="--pipeline 1080p_raw"
#   make waterfall.profile                          # py-spy flamegraph
#
# perf_waterfall.py declares its own deps (rich) via PEP 723, so uv
# resolves them into an ephemeral env — no pyproject changes needed.

WATERFALL_ARGS ?=

.PHONY: waterfall waterfall.profile

waterfall:  ## Render IPC perf waterfall (HEAD vs --baseline-ref, default origin/main)
	uv run scripts/perf_waterfall.py $(WATERFALL_ARGS)

waterfall.profile:  ## Attach py-spy to a 4K IPC reproducer and write /tmp/perf-waterfall.svg
	@command -v py-spy >/dev/null || { echo "py-spy not installed: uv tool install py-spy"; exit 1; }
	py-spy record -o /tmp/perf-waterfall.svg --rate 250 --subprocesses -- \
		uv run python scripts/profile_pipeline.py 4k_raw --frames 400 --no-filter-work
	@echo "wrote /tmp/perf-waterfall.svg"

.PHONY: test-all
test-all:  ## Run all unit tests
	$(MAKE) test
	$(MAKE) test-coverage


.PHONY: test-coverage
test-coverage:  ## Run unit tests and generate coverage report
	@mkdir -p Reports
	@pytest -v --cov=tests --junitxml=Reports/coverage.xml --cov-report=json:Reports/coverage.json --benchmark-disable -m "not slow"
	@jq -r '["File Name", "Statements", "Missing", "Coverage%"], (.files | to_entries[] | [.key, .value.summary.num_statements, .value.summary.missing_lines, .value.summary.percent_covered_display]) | @csv'  Reports/coverage.json >  Reports/coverage_report.csv
	@jq -r '["TOTAL", (.totals.num_statements // 0), (.totals.missing_lines // 0), (.totals.percent_covered_display // "0")] | @csv'  Reports/coverage.json >>  Reports/coverage_report.csv


.PHONY: clean
clean:  ## Delete all generated files and directories
	sudo rm -rf build/ cache/ dist/ filter_runtime.egg-info/ telemetry/ ipc_* 
	find . -name __pycache__ -type d -exec rm -rf {} +


.PHONY: install
install:  ## Install package with dev dependencies from PyPI
	pip install -e .[all,dev]

# ─── Cascade (DT-145) ────────────────────────────────────────────────────
# Cascade lives in .github/workflows/cascade-on-tag.yaml. The previous Cloud
# Build cascade (cloudbuild-cascade.yaml + scripts/build-filters.sh) was
# removed when DT-145 landed — see PROPOSAL.md for the rationale. Local
# smoke-test the discovery half via:
#
#   GH_TOKEN=$(gh auth token) OF_VERSION=$(cat VERSION | sed 's/^v//') \
#     ./scripts/cascade/discover.sh
#
# To trigger a live cascade, push a tag (or run the workflow manually with
# `gh workflow run cascade-on-tag.yaml -f single_filter=...`).

.PHONY: cloud.logs cloud.logs.build

cloud.logs: ## Tail logs for the most recent Cloud Build
	gcloud builds log --stream $$(gcloud builds list --project=$(GCP_PROJECT) --limit=1 --format='value(id)')

cloud.logs.build: ## Tail logs for a specific build (BUILD_ID=...)
	@test -n "$(BUILD_ID)" || { echo "Usage: make cloud.logs.build BUILD_ID=<id>"; exit 1; }
	gcloud builds log --stream $(BUILD_ID) --project=$(GCP_PROJECT)
