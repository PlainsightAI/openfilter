.PHONY: install run run-rtsp run-files run-gcs run-gcs-enhanced rtsp-start rtsp-stop rtsp-status clean help

# Default target
help:
	@echo "Video Pipeline Demo - Available targets:"
	@echo "  install     - Install dependencies"
	@echo "  run         - Run the video pipeline demo with local files"
	@echo "  run-files   - Run the video pipeline demo with local files"
	@echo "  run-rtsp    - Run the video pipeline demo with RTSP streams"
	@echo "  run-gcs     - Run the GCS image viewer (ImageIn -> Webvis)"
	@echo "  run-gcs-enhanced - Run the enhanced GCS image viewer (ImageIn -> FaceEnhancer -> Webvis)"
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

# Run GCS image viewer (ImageIn -> Webvis)
run-gcs:
	@echo "Usage: make run-gcs BUCKET=your-bucket FOLDER=your-folder"
	@echo "Example: make run-gcs BUCKET=protege-artifacts-development FOLDER=video-pipeline-demo/stream2/images"
	@if [ -z "$(BUCKET)" ] || [ -z "$(FOLDER)" ]; then \
		echo "❌ Error: BUCKET and FOLDER are required"; \
		echo "Usage: make run-gcs BUCKET=your-bucket FOLDER=your-folder"; \
		echo "Example: make run-gcs BUCKET=protege-artifacts-development FOLDER=labelled-data/demo_ocr/data"; \
		exit 1; \
	fi
	@echo "🖼️  Starting GCS image viewer..."
	@echo "📁 Bucket: $(BUCKET)"
	@echo "📂 Folder: $(FOLDER)"
	@echo "🌐 Web interface: http://127.0.0.1:8003"
	@echo "Press Ctrl+C to stop"
	python main_gcs_simple.py gs://$(BUCKET)/$(FOLDER)

# Run enhanced GCS image viewer (ImageIn -> FaceEnhancer -> Webvis)
run-gcs-enhanced:
	@echo "Usage: make run-gcs-enhanced BUCKET=your-bucket FOLDER=your-folder"
	@echo "Example: make run-gcs-enhanced BUCKET=protege-artifacts-development FOLDER=video-pipeline-demo/stream2/images"
	@if [ -z "$(BUCKET)" ] || [ -z "$(FOLDER)" ]; then \
		echo "❌ Error: BUCKET and FOLDER are required"; \
		echo "Usage: make run-gcs-enhanced BUCKET=your-bucket FOLDER=your-folder"; \
		echo "Example: make run-gcs-enhanced BUCKET=protege-artifacts-development FOLDER=video-pipeline-demo/stream2/images"; \
		exit 1; \
	fi
	@echo "🖼️  Starting enhanced GCS image viewer..."
	@echo "📁 Bucket: $(BUCKET)"
	@echo "📂 Folder: $(FOLDER)"
	@echo "🌐 Web interface: http://127.0.0.1:8004"
	@echo "✨ Features: 800x600 frames, random names, timestamps"
	@echo "Press Ctrl+C to stop"
	python main_gcs_enhanced.py gs://$(BUCKET)/$(FOLDER)

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
