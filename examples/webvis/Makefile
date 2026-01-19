# Webvis Example Makefile

# Default values
VIDEO_INPUT ?= ./data/sample-video-with-timestamp.mp4
WEBVIS_PORT ?= 8000
RTSP_URL ?= rtsp://localhost:8554/stream0

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

.PHONY: help install add-timestamp run run-rtsp docker-start docker-stop rtsp-start rtsp-stop rtsp-status clean

help: ## Show this help message
	@echo "Webvis Example - Available Commands"
	@echo "===================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "Environment Variables:"
	@echo "  VIDEO_INPUT    Path to input video (default: ./data/sample-video-with-timestamp.mp4)"
	@echo "  WEBVIS_PORT    Webvis port (default: 8000)"
	@echo "  RTSP_URL       RTSP stream URL (default: rtsp://localhost:8554/stream0)"
	@echo ""

install: ## Install dependencies
	@echo "$(GREEN)Installing dependencies...$(NC)"
	@if command -v pyenv >/dev/null 2>&1; then \
		echo "$(YELLOW)Activating openfilter pyenv environment...$(NC)"; \
		eval "$$(pyenv init -)" && pyenv activate openfilter; \
	fi
	@pip install -r requirements.txt
	@echo "$(GREEN)Dependencies installed!$(NC)"

add-timestamp: ## Add timestamp overlay to video
	@echo "$(GREEN)Adding timestamp to video...$(NC)"
	@mkdir -p data
	@python add_timestamp.py
	@echo "$(GREEN)Video with timestamp created: $(VIDEO_INPUT)$(NC)"

run: ## Run Python example with local video files
	@echo "$(GREEN)Running webvis example with local video files...$(NC)"
	@python filter_usage.py --input $(VIDEO_INPUT) --port $(WEBVIS_PORT)

run-multi: ## Run Python example with multi-stream mode
	@echo "$(GREEN)Running webvis example with multi-stream mode...$(NC)"
	@python filter_usage.py --input $(VIDEO_INPUT) --port $(WEBVIS_PORT) --multi-stream

run-rtsp: ## Run Python example with RTSP streams
	@echo "$(GREEN)Running webvis example with RTSP streams...$(NC)"
	@python filter_usage.py --mode rtsp --rtsp-url $(RTSP_URL) --port $(WEBVIS_PORT)

cli: ## Run OpenFilter CLI with local video files
	@echo "$(GREEN)Running OpenFilter CLI with local video files...$(NC)"
	@echo "$(YELLOW)Command:$(NC)"
	@echo "  openfilter run \\"
	@echo "    - VideoIn \\"
	@echo "      --sources file://$(VIDEO_INPUT)!loop \\"
	@echo "      --outputs tcp://* \\"
	@echo "    - Webvis \\"
	@echo "      --sources tcp://localhost \\"
	@echo "      --port $(WEBVIS_PORT)"
	@openfilter run \
		- VideoIn \
			--sources file://$(VIDEO_INPUT)!loop \
			--outputs tcp://* \
		- Webvis \
			--sources tcp://localhost \
			--port $(WEBVIS_PORT)

cli-multi: ## Run OpenFilter CLI with multi-stream mode
	@echo "$(GREEN)Running OpenFilter CLI with multi-stream mode...$(NC)"
	@echo "$(YELLOW)Command:$(NC)"
	@echo "  openfilter run \\"
	@echo "    - VideoIn \\"
	@echo "      --sources 'file://$(VIDEO_INPUT)!loop,file://$(VIDEO_INPUT)!loop;stream2,file://$(VIDEO_INPUT)!loop;stream3' \\"
	@echo "      --outputs tcp://* \\"
	@echo "    - Webvis \\"
	@echo "      --sources 'tcp://localhost;main,tcp://localhost;stream2,tcp://localhost;stream3' \\"
	@echo "      --port $(WEBVIS_PORT)"
	@openfilter run \
		- VideoIn \
			--sources 'file://$(VIDEO_INPUT)!loop,file://$(VIDEO_INPUT)!loop;stream2,file://$(VIDEO_INPUT)!loop;stream3' \
			--outputs tcp://* \
		- Webvis \
			--sources 'tcp://localhost;main,tcp://localhost;stream2,tcp://localhost;stream3' \
			--port $(WEBVIS_PORT)

cli-rtsp: ## Run OpenFilter CLI with RTSP streams
	@echo "$(GREEN)Running OpenFilter CLI with RTSP streams...$(NC)"
	@echo "$(YELLOW)Command:$(NC)"
	@echo "  openfilter run \\"
	@echo "    - VideoIn \\"
	@echo "      --sources $(RTSP_URL) \\"
	@echo "      --outputs tcp://* \\"
	@echo "    - Webvis \\"
	@echo "      --sources tcp://localhost \\"
	@echo "      --port $(WEBVIS_PORT)"
	@openfilter run \
		- VideoIn \
			--sources $(RTSP_URL) \
			--outputs tcp://* \
		- Webvis \
			--sources tcp://localhost \
			--port $(WEBVIS_PORT)

docker-start: ## Start Docker Compose services (video mode)
	@echo "$(GREEN)Starting Docker Compose services (video mode)...$(NC)"
	@docker-compose -f docker-compose.video.yaml up -d
	@echo "$(GREEN)Docker services started!$(NC)"
	@echo "$(YELLOW)Webvis available at: http://localhost:$(WEBVIS_PORT)$(NC)"
	@echo "$(YELLOW)Use 'make docker-stop' to stop services$(NC)"

docker-start-rtsp: ## Start Docker Compose with RTSP streamer
	@echo "$(GREEN)Starting Docker Compose with RTSP streamer...$(NC)"
	@docker-compose -f docker-compose.rtsp.yaml up -d
	@echo "$(GREEN)Docker services with RTSP started!$(NC)"
	@echo "$(YELLOW)Webvis available at: http://localhost:$(WEBVIS_PORT)$(NC)"
	@echo "$(YELLOW)RTSP stream available at: rtsp://localhost:8554/stream0$(NC)"
	@echo "$(YELLOW)RTSP Web interface: http://localhost:8888$(NC)"
	@echo "$(YELLOW)Use 'make docker-stop' to stop services$(NC)"

docker-start-multi: ## Start Docker Compose with multi-stream webvis
	@echo "$(GREEN)Starting Docker Compose with multi-stream webvis...$(NC)"
	@docker-compose -f docker-compose.multi.yaml up -d
	@echo "$(GREEN)Docker services with multi-stream started!$(NC)"
	@echo "$(YELLOW)Webvis available at: http://localhost:$(WEBVIS_PORT)$(NC)"
	@echo "$(YELLOW)Multi-stream endpoints:$(NC)"
	@echo "$(YELLOW)  - Stream 1: http://localhost:$(WEBVIS_PORT)/stream1$(NC)"
	@echo "$(YELLOW)  - Stream 2: http://localhost:$(WEBVIS_PORT)/stream2$(NC)"
	@echo "$(YELLOW)  - Stream 3: http://localhost:$(WEBVIS_PORT)/stream3$(NC)"
	@echo "$(YELLOW)Use 'make docker-stop' to stop services$(NC)"

docker-stop: ## Stop Docker Compose services
	@echo "$(GREEN)Stopping Docker Compose services...$(NC)"
	@docker-compose -f docker-compose.video.yaml down
	@docker-compose -f docker-compose.multi.yaml down
	@docker-compose -f docker-compose.rtsp.yaml down
	@echo "$(GREEN)Docker services stopped!$(NC)"

docker-logs: ## Show Docker Compose logs (video mode)
	@echo "$(GREEN)Showing Docker Compose logs (video mode)...$(NC)"
	@docker-compose -f docker-compose.video.yaml logs -f

docker-logs-multi: ## Show Docker Compose logs (multi-stream mode)
	@echo "$(GREEN)Showing Docker Compose logs (multi-stream mode)...$(NC)"
	@docker-compose -f docker-compose.multi.yaml logs -f

docker-logs-rtsp: ## Show Docker Compose logs (RTSP mode)
	@echo "$(GREEN)Showing Docker Compose logs (RTSP mode)...$(NC)"
	@docker-compose -f docker-compose.rtsp.yaml logs -f

rtsp-start: ## Start RTSP streamer
	@echo "$(GREEN)Starting RTSP streamer...$(NC)"
	@docker run -d \
		--name webvis-rtsp-streamer \
		-p 8554:8554 \
		-p 8888:8888 \
		-v $(PWD)/data:/data/videos \
		us-west1-docker.pkg.dev/plainsightai-prod/oci/rtsp-streamer:1.1.0
	@echo "$(GREEN)RTSP streamer started!$(NC)"
	@echo "$(YELLOW)RTSP streams available at:$(NC)"
	@echo "$(YELLOW)  - Stream 0: rtsp://localhost:8554/stream0$(NC)"
	@echo "$(YELLOW)  - Stream 1: rtsp://localhost:8554/stream1$(NC)"
	@echo "$(YELLOW)  - Stream 2: rtsp://localhost:8554/stream2$(NC)"
	@echo "$(YELLOW)Web interface: http://localhost:8888$(NC)"

rtsp-stop: ## Stop RTSP streamer
	@echo "$(GREEN)Stopping RTSP streamer...$(NC)"
	@docker stop webvis-rtsp-streamer 2>/dev/null || true
	@docker rm webvis-rtsp-streamer 2>/dev/null || true
	@echo "$(GREEN)RTSP streamer stopped!$(NC)"

rtsp-status: ## Check RTSP streamer status
	@echo "$(GREEN)Checking RTSP streamer status...$(NC)"
	@if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q webvis-rtsp-streamer; then \
		echo "$(GREEN)RTSP streamer is running$(NC)"; \
		echo "$(YELLOW)RTSP streams:$(NC)"; \
		echo "$(YELLOW)  - Stream 0: rtsp://localhost:8554/stream0$(NC)"; \
		echo "$(YELLOW)  - Stream 1: rtsp://localhost:8554/stream1$(NC)"; \
		echo "$(YELLOW)  - Stream 2: rtsp://localhost:8554/stream2$(NC)"; \
		echo "$(YELLOW)Web interface: http://localhost:8888$(NC)"; \
	else \
		echo "$(RED)RTSP streamer is not running$(NC)"; \
		echo "$(YELLOW)Use 'make rtsp-start' to start it$(NC)"; \
	fi

clean: ## Clean up generated files and containers
	@echo "$(GREEN)Cleaning up...$(NC)"
	@docker-compose -f docker-compose.video.yaml down 2>/dev/null || true
	@docker-compose -f docker-compose.multi.yaml down 2>/dev/null || true
	@docker-compose -f docker-compose.rtsp.yaml down 2>/dev/null || true
	@docker stop webvis-rtsp-streamer 2>/dev/null || true
	@docker rm webvis-rtsp-streamer 2>/dev/null || true
	@rm -rf cache telemetry logs
	@echo "$(GREEN)Cleanup complete!$(NC)"

test: ## Run basic tests
	@echo "$(GREEN)Running basic tests...$(NC)"
	@if command -v pyenv >/dev/null 2>&1; then \
		eval "$$(pyenv init -)" && pyenv activate openfilter; \
	fi
	@python -c "import openfilter; print('OpenFilter import successful')"
	@python -c "from openfilter.filter_runtime.filters.webvis import Webvis; print('Webvis import successful')"
	@echo "$(GREEN)Tests passed!$(NC)"

analyze-latency: ## Analyze OpenFilter processing latency (proves no internal delays)
	@echo "$(GREEN)Analyzing OpenFilter processing latency...$(NC)"
	@echo "$(YELLOW)This analysis proves OpenFilter processes frames in < 1ms$(NC)"
	@cd latency_analysis && python latency_analysis.py

analyze-network: ## Analyze network latency vs OpenFilter latency
	@echo "$(GREEN)Analyzing network latency...$(NC)"
	@echo "$(YELLOW)This analysis shows the difference between OpenFilter and network latency$(NC)"
	@cd latency_analysis && python network_analysis.py


# Default target
.DEFAULT_GOAL := help
