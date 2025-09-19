.PHONY: install run run-rtsp run-files rtsp-start rtsp-stop rtsp-status clean help

# Default target
help:
	@echo "Video Pipeline Demo - Available targets:"
	@echo "  install     - Install dependencies"
	@echo "  run         - Run the video pipeline demo with local files"
	@echo "  run-files   - Run the video pipeline demo with local files"
	@echo "  run-rtsp    - Run the video pipeline demo with RTSP streams"
	@echo "  rtsp-start  - Start RTSP streamer with videos from ./data"
	@echo "  rtsp-stop   - Stop RTSP streamer"
	@echo "  rtsp-status - Check RTSP streamer status"
	@echo "  clean       - Clean output files"
	@echo "  help        - Show this help message"

# Install dependencies
install:
	pip install -e .

# Run the demo with local files (default)
run: run-files

# Run with local video files
run-files:
	python main_rtsp.py --mode files

# Run with RTSP streams
run-rtsp:
	GCS_BUCKET=protege-artifacts-development python main_rtsp.py --mode rtsp

# Start RTSP streamer with videos from ./data
rtsp-start:
	@echo "Starting RTSP streamer with videos from ./data..."
	@echo "Using published Docker image: us-west1-docker.pkg.dev/plainsightai-prod/oci/rtsp-streamer:1.1.0"
	@docker run -d \
		--name rtsp-streamer \
		-p 8554:8554 \
		-p 8888:8888 \
		-v "$(PWD)/data:/data/videos:ro" \
		-e VIDEO_LOOP=true \
		-e VIDEO_STREAM_NAME=stream0 \
		-e RTSP_PORT=8554 \
		-e WEB_INTERFACE_PORT=8888 \
		us-west1-docker.pkg.dev/plainsightai-prod/oci/rtsp-streamer:1.1.0
	@echo "RTSP streamer started!"
	@echo "RTSP streams available at:"
	@echo "  - Stream 0: rtsp://localhost:8554/stream0"
	@echo "  - Stream 1: rtsp://localhost:8554/stream1" 
	@echo "  - Stream 2: rtsp://localhost:8554/stream2"
	@echo "Web interface: http://localhost:8888"

# Stop RTSP streamer
rtsp-stop:
	@echo "Stopping RTSP streamer..."
	@docker stop rtsp-streamer 2>/dev/null || echo "Container not running"
	@docker rm rtsp-streamer 2>/dev/null || echo "Container not found"
	@echo "RTSP streamer stopped!"

# Check RTSP streamer status
rtsp-status:
	@echo "Checking RTSP streamer status..."
	@docker ps --filter name=rtsp-streamer --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
	@echo ""
	@echo "Testing RTSP port 8554..."
	@nc -z localhost 8554 && echo "✅ RTSP port 8554 is open" || echo "❌ RTSP port 8554 is not accessible"
	@echo "Testing web interface port 8888..."
	@nc -z localhost 8888 && echo "✅ Web interface port 8888 is open" || echo "❌ Web interface port 8888 is not accessible"

# Clean output files
clean:
	rm -rf output/deduped_frames/*
	rm -rf output/face_crops/*
	rm -rf output/sallon/*
	rm -rf logs/*

# Run with custom videos
run-custom:
	@echo "Usage: make run-custom VIDEO1=path/to/video1.mp4 VIDEO2=path/to/video2.mp4"
	VIDEO1_PATH=$(VIDEO1) VIDEO2_PATH=$(VIDEO2) python main.py
