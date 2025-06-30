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
		--sources 'file://example_video.mp4!loop' \
	- filter_license_plate_detection.filter.FilterLicensePlateDetection \
	- filter_crop.filter.FilterCrop \
		--detection_key license_plate_detection \
		--detection_class_field label \
		--detection_roi_field box \
		--output_prefix cropped_ \
		--mutate_original_frames false \
		--topic_mode main_only \
	- filter_optical_character_recognition.filter.FilterOpticalCharacterRecognition \
		--topic_pattern 'license_plate' \
		--ocr_engine easyocr \
		--forward_ocr_texts true \
	- filter_license_annotation_demo.filter.FilterLicenseAnnotationDemo \
		--cropped_topic_suffix license_plate \
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

	@if [ ! -f model.pth ]; then \
		echo "model not found, downloading model archive..."; \
		curl -L -o model.zip https://models.openfilter.io/license_plate_detection_model/v0.1.0.zip; \
		echo "Unzipping model archive to current directory..."; \
		unzip -o model.zip; \
		echo "Removing model.zip..."; \
		rm model.zip; \
	else \
		echo "model already exists, skipping download."; \
	fi

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

