# OpenFilter Observability Demo Makefile

.PHONY: help setup test run run-telemetry run-openlineage run-otel-only clean

help: ## Show this help message
	@echo "OpenFilter Observability Demo"
	@echo "============================"
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and create sample video
	@echo "🔧 Setting up observability demo..."
	pip install -r requirements.txt
	python create_sample_video.py
	@echo "✅ Setup complete!"

test: ## Run all tests
	@echo "🧪 Running tests..."
	python test_demo.py

run: ## Run basic demo (no observability)
	@echo "🚀 Running basic demo..."
	python app.py --input file://sample_video.mp4!loop --fps 10

run-telemetry: ## Run demo with OpenTelemetry enabled
	@echo "📊 Running demo with OpenTelemetry..."
	TELEMETRY_EXPORTER_ENABLED=true TELEMETRY_EXPORTER_TYPE=console python app.py --input file://sample_video.mp4!loop --fps 10

run-openlineage: ## Run demo with OpenLineage enabled
	@echo "📈 Running demo with OpenLineage..."
	TELEMETRY_EXPORTER_ENABLED=true \
	OPENLINEAGE_URL=https://oleander.dev \
	OPENLINEAGE_API_KEY=test_key \
	OF_SAFE_METRICS=frames_processed,frames_with_detections,detections_per_frame,detection_confidence \
	python app.py --input file://sample_video.mp4!loop --fps 10

run-otel-only: ## Run OTEL-only demo (no OpenLineage)
	@echo "☁️  Running OTEL-only demo..."
	@echo "⚠️  Make sure to configure OTEL_EXPORTER_OTLP_ENDPOINT in config_otel_only.env"
	TELEMETRY_EXPORTER_ENABLED=true \
	TELEMETRY_EXPORTER_TYPE=otlp \
	OF_SAFE_METRICS_FILE=safe_metrics_otel.yaml \
	python app_otel_only.py

run-full: ## Run demo with full observability stack
	@echo "🎯 Running demo with full observability stack..."
	TELEMETRY_EXPORTER_ENABLED=true \
	TELEMETRY_EXPORTER_TYPE=otlp \
	TELEMETRY_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
	OPENLINEAGE_URL=https://oleander.dev \
	OPENLINEAGE_API_KEY=test_key \
	OF_SAFE_METRICS_FILE=safe_metrics.yaml \
	python app.py --input file://sample_video.mp4!loop --fps 10

run-yaml-allowlist: ## Run demo with YAML allowlist
	@echo "📋 Running demo with YAML allowlist..."
	TELEMETRY_EXPORTER_ENABLED=true \
	OPENLINEAGE_URL=https://oleander.dev \
	OPENLINEAGE_API_KEY=test_key \
	OF_SAFE_METRICS_FILE=safe_metrics.yaml \
	python app.py --input file://sample_video.mp4!loop --fps 10

run-restrictive: ## Run demo with restrictive allowlist (testing security)
	@echo "🔒 Running demo with restrictive allowlist..."
	TELEMETRY_EXPORTER_ENABLED=true \
	OPENLINEAGE_URL=https://oleander.dev \
	OPENLINEAGE_API_KEY=test_key \
	OF_SAFE_METRICS_FILE=safe_metrics_restrictive.yaml \
	python app.py --input file://sample_video.mp4!loop --fps 10

clean: ## Clean up generated files
	@echo "🧹 Cleaning up..."
	rm -f sample_video.mp4
	rm -rf output/
	@echo "✅ Cleanup complete!"

demo: setup test ## Setup and test the demo
	@echo "🎉 Demo is ready to run!"
	@echo ""
	@echo "Try these commands:"
	@echo "  make run                 # Basic demo"
	@echo "  make run-telemetry       # With OpenTelemetry"
	@echo "  make run-openlineage     # With OpenLineage"
	@echo "  make run-yaml-allowlist  # With YAML allowlist"
	@echo "  make run-restrictive     # With restrictive allowlist"
	@echo "  make run-full            # Full observability stack" 