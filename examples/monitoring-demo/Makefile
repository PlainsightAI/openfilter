MONITORING_DIR := ../../docker/monitoring
COMPOSE := docker compose -f $(MONITORING_DIR)/docker-compose.monitoring.yaml

.PHONY: help stack-up stack-down stack-health run verify clean all

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

all: stack-up run ## Start stack + run pipeline (full demo)

clean: stack-down ## Stop stack and clean up
	@echo "Done"
