#!/bin/bash

# Video Pipeline Demo with RTSP Support
# This script helps you get started with the RTSP-enabled video pipeline demo

set -e

echo "🚀 Video Pipeline Demo with RTSP Support"
echo "========================================"

# Check if we're in the right directory
if [ ! -f "main_rtsp.py" ]; then
    echo "❌ Error: Please run this script from the video-pipeline-demo directory"
    exit 1
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed or not in PATH"
    echo "Please install Docker to use RTSP streaming features"
    echo "You can still use local video files (option 1)"
fi

# Check if data directory exists and has videos
if [ ! -d "data" ] || [ -z "$(ls -A data/*.mp4 2>/dev/null)" ]; then
    echo "❌ Error: No video files found in ./data directory"
    echo "Please add video files (01.mp4, 02.mp4, 03.mp4) to the ./data directory"
    exit 1
fi

echo "✅ Found video files in ./data directory:"
ls -la data/*.mp4

echo ""
echo "Choose your demo mode:"
echo "1) Local video files (default)"
echo "2) RTSP streams (requires RTSP streamer)"
echo "3) Start RTSP streamer only"
echo "4) Stop RTSP streamer"
echo "5) Check RTSP streamer status"
echo "6) Exit"

read -p "Enter your choice (1-6): " choice

case $choice in
    1)
        echo "🎬 Starting pipeline with local video files..."
        python main_rtsp.py --mode files
        ;;
    2)
        echo "📡 Starting pipeline with RTSP streams..."
        echo "Checking if RTSP streamer is running..."
        if make rtsp-status > /dev/null 2>&1; then
            echo "✅ RTSP streamer is running, starting pipeline..."
            python main_rtsp.py --mode rtsp
        else
            echo "❌ RTSP streamer is not running. Please start it first (option 3)"
            exit 1
        fi
        ;;
    3)
        echo "📡 Starting RTSP streamer with videos from ./data..."
        echo "Using published Docker image: us-west1-docker.pkg.dev/plainsightai-prod/oci/rtsp-streamer:1.1.0"
        make rtsp-start
        echo ""
        echo "✅ RTSP streamer started!"
        echo "RTSP streams available at:"
        echo "  - Stream 0: rtsp://localhost:8554/stream0"
        echo "  - Stream 1: rtsp://localhost:8554/stream1"
        echo "  - Stream 2: rtsp://localhost:8554/stream2"
        echo "Web interface: http://localhost:8888"
        echo ""
        echo "You can now run the pipeline with RTSP streams (option 2)"
        ;;
    4)
        echo "🛑 Stopping RTSP streamer..."
        make rtsp-stop
        echo "✅ RTSP streamer stopped!"
        ;;
    5)
        echo "🔍 Checking RTSP streamer status..."
        make rtsp-status
        ;;
    6)
        echo "👋 Goodbye!"
        exit 0
        ;;
    *)
        echo "❌ Invalid choice. Please run the script again."
        exit 1
        ;;
esac
