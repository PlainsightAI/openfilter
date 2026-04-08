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

# ─── Cloud Build (manual) ────────────────────────────────────────────────

.PHONY: cloud.cascade cloud.cascade.live cloud.logs cloud.logs.build

cloud.cascade: ## Submit cascade build (dry-run; SINGLE_FILTER=x or FILTER_SUBSET=x,y)
	gcloud builds submit \
		--config=cloudbuild-cascade.yaml \
		--project=$(GCP_PROJECT) \
		--service-account=projects/$(GCP_PROJECT)/serviceAccounts/$(CLOUDBUILD_SA) \
		--substitutions=TAG_NAME=$(VERSION),_DRY_RUN=true,_SINGLE_FILTER=$(SINGLE_FILTER),_FILTER_SUBSET=$(FILTER_SUBSET) \
		.

cloud.cascade.live: ## Submit cascade build (LIVE — pushes images)
	@echo "WARNING: This will push images to GAR and DockerHub."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	gcloud builds submit \
		--config=cloudbuild-cascade.yaml \
		--project=$(GCP_PROJECT) \
		--service-account=projects/$(GCP_PROJECT)/serviceAccounts/$(CLOUDBUILD_SA) \
		--substitutions=TAG_NAME=$(VERSION),_DRY_RUN=false \
		.

cloud.cascade.local: ## Run cascade build-filters script locally (dry-run)
	@WORKSPACE=$$(mktemp -d) && \
	echo "Workspace: $$WORKSPACE" && \
	mkdir -p "$$WORKSPACE/filters" "$$WORKSPACE/results" && \
	echo "$(subst v,,$(VERSION))" > "$$WORKSPACE/openfilter_version" && \
	cp scripts/check_constraint.py "$$WORKSPACE/check_constraint.py" && \
	GH_TOKEN=$$(gcloud secrets versions access latest --secret=github-token --project=$(GCP_PROJECT) 2>/dev/null || echo '{}') && \
	env \
		WORKSPACE="$$WORKSPACE" \
		DRY_RUN=true \
		GAR_REGION=us-west1 \
		GAR_PROJECT=plainsightai-prod \
		GAR_REPO=oci \
		DOCKERHUB_ORG=plainsightai \
		GITHUB_TOKEN="$$GH_TOKEN" \
		SINGLE_FILTER="$(SINGLE_FILTER)" \
		FILTER_SUBSET="$(FILTER_SUBSET)" \
		bash scripts/build-filters.sh; \
	EXIT=$$?; rm -rf "$$WORKSPACE"; exit $$EXIT

cloud.logs: ## Tail logs for the most recent Cloud Build
	gcloud builds log --stream $$(gcloud builds list --project=$(GCP_PROJECT) --limit=1 --format='value(id)')

cloud.logs.build: ## Tail logs for a specific build (BUILD_ID=...)
	@test -n "$(BUILD_ID)" || { echo "Usage: make cloud.logs.build BUILD_ID=<id>"; exit 1; }
	gcloud builds log --stream $(BUILD_ID) --project=$(GCP_PROJECT)
