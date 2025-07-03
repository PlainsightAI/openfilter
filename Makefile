VERSION ?= $(shell cat VERSION)

export VERSION

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'


.PHONY: build-wheel
build-wheel:  ## Build python wheel
	python -m build --wheel


.PHONY: test
test:  ## Run basic unit tests
	pytest -v --cov=tests -s tests

.PHONY: test-all
test-all:  ## Run all unit tests
	$(MAKE) test
	$(MAKE) test-coverage


.PHONY: test-coverage
test-coverage:  ## Run unit tests and generate coverage report
	@mkdir -p Reports
	@pytest -v --cov=tests --junitxml=Reports/coverage.xml --cov-report=json:Reports/coverage.json
	@jq -r '["File Name", "Statements", "Missing", "Coverage%"], (.files | to_entries[] | [.key, .value.summary.num_statements, .value.summary.missing_lines, .value.summary.percent_covered_display]) | @csv'  Reports/coverage.json >  Reports/coverage_report.csv
	@jq -r '["TOTAL", (.totals.num_statements // 0), (.totals.missing_lines // 0), (.totals.percent_covered_display // "0")] | @csv'  Reports/coverage.json >>  Reports/coverage_report.csv


.PHONY: clean
clean:  ## Delete all generated files and directories
	sudo rm -rf build/ cache/ dist/ filter_runtime.egg-info/ telemetry/ ipc_*
	find . -name __pycache__ -type d -exec rm -rf {} +


.PHONY: install
install:  ## Install package with dev dependencies from PyPI
	pip install -e .[all,dev]
