# ---------------------------------
# Repo-specific variables
# ---------------------------------

VERSION ?= $(shell cat VERSION)
export VERSION

# ---------------------------------
# Local pipeline definition
# ---------------------------------
PIPELINE := \
	- VideoIn \
		--sources 'file://hello.mov!loop' \
	- filter_optical_character_recognition.filter.FilterOpticalCharacterRecognition \
		--ocr_engine easyocr \
		--forward_ocr_texts true \
	- Webvis

# ---------------------------------
# Targets
# ---------------------------------

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install:  ## Install package with dev dependencies
	pip install -e .[dev] \
		--extra-index-url https://python.openfilter.io/simple

.PHONY: run
run: # Open the browser and run the filters
	( sleep 3 && xdg-open http://localhost:8000 >/dev/null 2>&1 & )
	openfilter run $(PIPELINE)

.PHONY: test
test:  ## Run unit tests
	pytest -vv -s tests/ --junitxml=results/pytest-results.xml

.PHONY: test-coverage
test-coverage:  ## Run unit tests and generate coverage report
	@mkdir -p Reports
	@pytest -vv --cov=tests --junitxml=Reports/coverage.xml --cov-report=json:Reports/coverage.json -s tests/
	@jq -r '["File Name", "Statements", "Missing", "Coverage%"], (.files | to_entries[] | [.key, .value.summary.num_statements, .value.summary.missing_lines, .value.summary.percent_covered_display]) | @csv'  Reports/coverage.json >  Reports/coverage_report.csv
	@jq -r '["TOTAL", (.totals.num_statements // 0), (.totals.missing_lines // 0), (.totals.percent_covered_display // "0")] | @csv'  Reports/coverage.json >>  Reports/coverage_report.csv

.PHONY: build-wheel
build-wheel:  ## Build python wheel
	python -m pip install setuptools build wheel twine setuptools-scm --index-url https://pypi.org/simple --extra-index-url https://python.openfilter.io/simple
	python -m build --wheel

.PHONY: clean
clean:  ## Delete all generated files and directories
	sudo rm -rf build/ cache/ dist/ *.egg-info/ telemetry/
	find . -name __pycache__ -type d -exec rm -rf {} +

