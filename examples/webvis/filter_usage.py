#!/usr/bin/env python3
"""
Webvis Filter Usage Example

This example demonstrates how to use the Webvis filter with OpenFilter using Filter.run_multi().
It supports both local video files and RTSP streams.

Usage:
    # With local video files
    python filter_usage.py
    
    # With RTSP streams
    python filter_usage.py --mode rtsp
    
    # With custom video file
    python filter_usage.py --input ./data/custom-video.mp4
    
    # With custom RTSP URL
    python filter_usage.py --mode rtsp --rtsp-url rtsp://your-server:8554/stream0
"""

import os
import logging
import argparse
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_video_sources(mode, video_input=None, rtsp_url=None):
    """Get video sources based on mode."""
    if mode == "files":
        # Use local video files
        video_path = video_input or os.getenv('VIDEO_INPUT', './data/sample-video-with-timestamp.mp4')
        
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            logger.error("Please run 'make add-timestamp' to create the video with timestamp")
            return None
        
        sources = f'file://{video_path}!loop'
        logger.info(f"Using local video file: {video_path}")
        
    elif mode == "rtsp":
        # Use RTSP stream
        url = rtsp_url or os.getenv('RTSP_URL', 'rtsp://localhost:8554/stream0')
        sources = f'{url}'
        logger.info(f"Using RTSP stream: {url}")
    
    else:
        raise ValueError(f"Invalid mode: {mode}. Use 'files' or 'rtsp'")
    
    return sources

def create_single_stream_pipeline(sources, port=8000):
    """Create a simple single stream pipeline."""
    return [
        # Video Input
        (VideoIn, {
            "id": "video_in",
            "sources": sources,
            "outputs": "tcp://*:5550",
        }),
        
        # Web Visualization
        (Webvis, {
            "id": "webvis",
            "sources": "tcp://localhost:5550",
            "port": port,
        }),
    ]

def create_multi_stream_pipeline(sources, port=8000):
    """Create a multi-stream pipeline with different topics."""
    return [
        # Video Input - Multiple streams with different topics
        (VideoIn, {
            "id": "video_in",
            "sources": f"""
                {sources},
                {sources};stream2,
                {sources};stream3
            """,
            "outputs": "tcp://*:5550",
        }),
        
        # Web Visualization - Multiple streams
        (Webvis, {
            "id": "webvis",
            "sources": [
                "tcp://localhost:5550;main>stream1",
                "tcp://localhost:5550;stream2",
                "tcp://localhost:5550;stream3",
            ],
            "port": port,
        }),
    ]

def main():
    """Run the webvis filter example."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Webvis Filter Usage Example')
    parser.add_argument('--mode', choices=['files', 'rtsp'], default='files',
                       help='Video source mode: files (local) or rtsp (streams)')
    parser.add_argument('--input', type=str,
                       help='Path to input video file (for files mode)')
    parser.add_argument('--rtsp-url', type=str,
                       help='RTSP URL (for rtsp mode)')
    parser.add_argument('--port', type=int, default=8000,
                       help='Webvis port (default: 8000)')
    parser.add_argument('--multi-stream', action='store_true',
                       help='Use multi-stream pipeline (3 parallel streams)')
    args = parser.parse_args()
    
    # Get video sources based on mode
    sources = get_video_sources(args.mode, args.input, args.rtsp_url)
    if sources is None:
        return
    
    # Get port from environment or arguments
    port = int(os.getenv('WEBVIS_PORT', args.port))
    
    logger.info("Starting Webvis Filter Example")
    logger.info(f"Mode: {args.mode.upper()}")
    logger.info(f"Port: {port}")
    logger.info(f"Multi-stream: {args.multi_stream}")
    logger.info("=" * 50)
    
    # Create pipeline based on configuration
    if args.multi_stream:
        filters = create_multi_stream_pipeline(sources, port)
        logger.info("Pipeline: VideoIn (3 streams) → Webvis")
        logger.info("Webvis available at:")
        logger.info(f"  - Stream 1: http://localhost:{port}/stream1")
        logger.info(f"  - Stream 2: http://localhost:{port}/stream2")
        logger.info(f"  - Stream 3: http://localhost:{port}/stream3")
    else:
        filters = create_single_stream_pipeline(sources, port)
        logger.info("Pipeline: VideoIn → Webvis")
        logger.info(f"Webvis available at: http://localhost:{port}")
    
    logger.info("=" * 50)
    
    try:
        # Run the pipeline
        Filter.run_multi(filters)
    except KeyboardInterrupt:
        logger.info("Pipeline stopped by user")
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise

if __name__ == '__main__':
    main()
