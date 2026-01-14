# Webvis Example

This comprehensive webvis example demonstrates how to use the Webvis filter in OpenFilter with multiple input methods and deployment options.

## Quick Start

### 1. Setup Environment
```bash
# Navigate to the webvis example
cd openfilter/examples/webvis

# Install dependencies
make install

# Add timestamp to video
make add-timestamp
```

### 2. Run Examples

#### Python Example (Filter.run_multi())
```bash
# Basic usage
make run

# Multi-stream mode
make run-multi

# With RTSP streams
make rtsp-start  # Start RTSP streamer first
make run-rtsp
```

#### OpenFilter CLI Example
```bash
# Basic CLI
make cli

# Multi-stream CLI
make cli-multi

# RTSP CLI
make cli-rtsp
```

#### Docker Example
```bash
# Start Docker Compose
make docker-start

# With RTSP streamer
make docker-start-rtsp

# With multi-stream webvis
make docker-start-multi
```

### 3. View Results
- **Main Webvis**: http://localhost:8000
- **RTSP Web Interface**: http://localhost:8888 (when using RTSP)
- **Multi-stream**: http://localhost:8000 (when using multi-stream mode)

## Key Features

### 1. Multiple Input Methods
- **Local Video Files**: Direct file access with timestamp overlay
- **RTSP Streams**: Live video streaming support
- **Multi-Stream**: Parallel processing of multiple video sources

### 2. Deployment Options
- **Python**: Direct execution with Filter.run_multi()
- **CLI**: Command-line interface with argument parsing
- **Docker**: Containerized deployment with Docker Compose
- **RTSP Streamer**: Live video streaming with published Docker image

### 3. VS Code Integration
- **Launch Configurations**: Pre-configured debug settings
- **Multiple Modes**: Python, CLI, Multi-stream, RTSP configurations

## 📁 File Structure

```
webvis/
├── README.md                     # This comprehensive guide
├── filter_usage.py              # Python example with Filter.run_multi()
├── docker-compose.video.yaml    # Docker Compose for video mode
├── docker-compose.multi.yaml    # Docker Compose for multi-stream mode
├── docker-compose.rtsp.yaml     # Docker Compose for RTSP mode
├── Makefile                     # Build and run automation
├── add_timestamp.py             # Script to add timestamp to video
├── requirements.txt             # Python dependencies
├── env-example                  # Environment variables template
└── data/                        # Video data directory
    └── sample-video-with-timestamp.mp4
```

## 🔧 Configuration

### Environment Variables
```bash
export VIDEO_INPUT=./data/sample-video-with-timestamp.mp4
export WEBVIS_PORT=8000
export RTSP_URL=rtsp://localhost:8554/stream0
```

### Makefile Commands
```bash
make help              # Show all available commands
make install           # Install dependencies
make add-timestamp     # Add timestamp to video
make run               # Run Python example
make cli               # Run CLI example
make docker-start      # Start Docker Compose
make rtsp-start        # Start RTSP streamer
make analyze-latency   # Analyze OpenFilter processing latency
make analyze-network   # Analyze network vs OpenFilter latency
make analyze-all       # Run comprehensive latency analysis suite
make clean             # Clean up generated files
```

## Video Processing

The example includes a timestamp overlay script that:
- Adds real-time timestamps to video frames
- Includes frame counters
- Creates a video with timestamp overlay in the `data/` directory
- Uses the sample video from openfilter-heroku-demo assets

## Web Interface

The webvis filter provides a real-time web interface showing:
- Live video streams
- Multiple stream support
- Responsive design
- Easy navigation between streams

## Docker Support

### Docker Compose Services
- **vidin**: Video input service
- **webvis**: Web visualization service
- **rtsp-streamer**: Optional RTSP streaming service

### Docker Compose Files
- **docker-compose.video.yaml**: Basic video file processing
- **docker-compose.multi.yaml**: Multi-stream video processing
- **docker-compose.rtsp.yaml**: RTSP streaming with health checks

## Code Examples

### Basic Video Processing
```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis

Filter.run_multi([
    (VideoIn, {
        "sources": "file://./data/sample-video-with-timestamp.mp4!loop",
        "outputs": "tcp://*:5550",
    }),
    (Webvis, {
        "sources": "tcp://localhost:5550",
        "port": 8000,
    }),
])
```

### Multi-Stream Processing
```python
Filter.run_multi([
    (VideoIn, {
        "sources": """
            file://./data/sample-video-with-timestamp.mp4!loop,
            file://./data/sample-video-with-timestamp.mp4!loop;stream2,
            file://./data/sample-video-with-timestamp.mp4!loop;stream3
        """,
        "outputs": "tcp://*:5550",
    }),
    (Webvis, {
        "sources": [
            "tcp://localhost:5550;main>stream1",
            "tcp://localhost:5550;stream2",
            "tcp://localhost:5550;stream3",
        ],
        "port": 8000,
    }),
])
```

### RTSP Streams
```python
Filter.run_multi([
    (VideoIn, {
        "sources": "rtsp://localhost:8554/stream0!loop",
        "outputs": "tcp://*:5550",
    }),
    (Webvis, {
        "sources": "tcp://localhost:5550",
        "port": 8000,
    }),
])
```

## 🔍 Troubleshooting

### Common Issues
1. **Port conflicts**: Ensure ports 8000 and 8554 are available
2. **Video not found**: Run `make add-timestamp` to create the video
3. **RTSP connection failed**: Ensure RTSP streamer is running
4. **Docker containers not starting**: Check Docker logs with `make docker-logs`

### Debug Mode
```bash
# Enable debug logging
python filter_usage.py --input ./data/sample-video-with-timestamp.mp4 --debug
```

## Success!

You now have a complete webvis example with:
- ✅ Python examples using Filter.run_multi()
- ✅ CLI interface with argument parsing
- ✅ Docker Compose configuration
- ✅ RTSP streamer integration
- ✅ Timestamp overlay functionality
- ✅ VS Code launch configurations
- ✅ Comprehensive Makefile automation
- ✅ Multi-stream support

Enjoy exploring the webvis filter capabilities! 🚀
