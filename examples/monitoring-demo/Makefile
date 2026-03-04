MONITORING_DIR := ../../docker/monitoring
COMPOSE := docker compose -f $(MONITORING_DIR)/docker-compose.monitoring.yaml

.PHONY: help stack-up stack-down stack-health run verify verify-alerts verify-alerts-test \
       clean all build up down logs \
       pipelines-build pipelines-up pipelines-down pipelines-logs \
       pipelines-logs-p1 pipelines-logs-p2 pipelines-logs-p3 pipelines-logs-p4 \
       pipelines-verify pipelines-status \
       trigger-alert-gpu trigger-alert-camera trigger-alert-disk trigger-alerts \
       resolve-test-alert

help: ## Show available commands
	@echo "OpenFilter Monitoring Demo"
	@echo "========================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Quick start:  make all"

stack-up: ## Start the monitoring stack (Prometheus, Alertmanager, Grafana, OTEL Collector)
	@echo "Starting monitoring stack..."
	$(COMPOSE) up -d
	@echo "Waiting for services..."
	@sleep 10
	@$(MAKE) stack-health

stack-down: ## Stop and remove the monitoring stack
	@echo "Stopping monitoring stack..."
	$(COMPOSE) down

stack-health: ## Check health of all monitoring services
	@echo "Checking service health..."
	@curl -sf http://localhost:9090/-/healthy > /dev/null && echo "  Prometheus:   OK" || echo "  Prometheus:   FAILED"
	@curl -sf http://localhost:9093/-/healthy > /dev/null && echo "  Alertmanager: OK" || echo "  Alertmanager: FAILED"
	@curl -sf http://localhost:3000/api/health > /dev/null && echo "  Grafana:      OK (http://localhost:3000  admin/admin)" || echo "  Grafana:      FAILED"

run: ## Run a pipeline that exports metrics to the monitoring stack (120s)
	@echo "Running pipeline with OTLP export..."
	@echo "  Metrics will appear in Prometheus after ~30s"
	@echo "  Press Ctrl+C to stop early"
	python run_pipeline.py

run-bg: ## Run the pipeline in background (120s)
	@echo "Running pipeline in background..."
	python run_pipeline.py &
	@echo "Pipeline PID: $$!"
	@echo "Run 'make verify' after ~30s to check metrics"

run-console: ## Run pipeline with console exporter (no monitoring stack needed)
	python run_pipeline.py --exporter console --duration 30

verify: ## Verify metrics landed in Prometheus and check alert states
	python verify_metrics.py

verify-alerts: ## Verify Slack alerting pipeline is correctly configured
	python3 verify_alerts.py

verify-alerts-test: ## Verify alerts + send a test alert to Slack
	python3 verify_alerts.py --send-test-alert

resolve-test-alert: ## Resolve the manual TestAlert in Alertmanager
	python3 verify_alerts.py --resolve-test-alert

trigger-alert-gpu: ## Run pipeline to trigger GPUUnavailable alert (macOS)
	python3 trigger_alert.py --alert gpu

trigger-alert-camera: ## Run pipeline to trigger CameraDisconnected alert
	python3 trigger_alert.py --alert camera

trigger-alert-disk: ## Run pipeline to trigger DiskCriticalTest alert
	python3 trigger_alert.py --alert disk

trigger-alerts: ## Run pipelines to trigger all testable alerts
	python3 trigger_alert.py --alert all

all: stack-up run ## Start stack + run pipeline (full demo)

clean: stack-down ## Stop stack and clean up
	@echo "Done"

# --- Docker workflow ---

build: ## Build openfilter-local image from local source
	docker build -t openfilter-local:latest -f Dockerfile ../..

up: build ## Build image + start Docker pipeline with monitoring stack
	docker compose up -d

down: ## Stop all Docker services
	docker compose down

logs: ## Follow timing_filter logs (timing metadata proof)
	docker compose logs -f timing_filter

# --- Multi-pipeline workflow ---

PIPELINES_COMPOSE := docker compose -f docker-compose.pipelines.yaml

pipelines-build: ## Build openfilter-local image for pipelines
	docker build -t openfilter-local:latest -f Dockerfile ../..

pipelines-up: pipelines-build ## Build image + start all 4 pipelines with monitoring
	$(PIPELINES_COMPOSE) up -d
	@echo ""
	@echo "Pipelines started. Wait ~30s for metrics, then run: make pipelines-verify"
	@echo "  P1 transform-chain webvis:    http://localhost:8001"
	@echo "  P2 fan-out webvis:            http://localhost:8002"
	@echo "  P3 diamond webvis:            http://localhost:8003"
	@echo "  P4 diamond-same-class webvis: http://localhost:8004"
	@echo "  Prometheus:                   http://localhost:9090"

pipelines-down: ## Stop all pipeline services
	$(PIPELINES_COMPOSE) down

pipelines-logs: ## Follow logs for all pipeline services
	$(PIPELINES_COMPOSE) logs -f

pipelines-logs-p1: ## Follow logs for Pipeline 1 (transform-chain)
	$(PIPELINES_COMPOSE) logs -f p1_video_in p1_grayscale p1_resize p1_timing p1_webvis

pipelines-logs-p2: ## Follow logs for Pipeline 2 (fan-out)
	$(PIPELINES_COMPOSE) logs -f p2_video_in p2_grayscale p2_resize p2_timing_a p2_timing_b p2_webvis

pipelines-logs-p3: ## Follow logs for Pipeline 3 (diamond)
	$(PIPELINES_COMPOSE) logs -f p3_video_in p3_grayscale p3_stats p3_timing p3_webvis

pipelines-logs-p4: ## Follow logs for Pipeline 4 (diamond-same-class)
	$(PIPELINES_COMPOSE) logs -f p4_video_in p4_slow_b1 p4_slow_b2 p4_timing p4_webvis

pipelines-status: ## Show status of all pipeline containers
	$(PIPELINES_COMPOSE) ps

pipelines-verify: ## Verify all 3 pipeline_ids appear in Prometheus metrics
	python3 verify_pipelines.py
