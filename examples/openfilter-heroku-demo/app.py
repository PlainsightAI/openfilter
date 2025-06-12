import os, logging, argparse
from dotenv import load_dotenv

# Load .env from the app directory
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

from openfilter.filter_runtime import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.video_out import VideoOut
from openfilter.filter_runtime.filters.webvis import Webvis

from demo_filter import (
    FrameProcessor, FrameProcessorConfig,
    FrameVisualizer, FrameVisualizerConfig
)

def build_pipeline(args):
    out_dir = os.getenv("OUTPUT_DIR", "/tmp/output")
    os.makedirs(out_dir, exist_ok=True)

    # Configure output paths
    combined_output = f"file://{os.path.join(out_dir, 'combined_view.mp4')}!fps={args.fps}"
    analytics_output = f"file://{os.path.join(out_dir, 'analytics_view.mp4')}!fps={args.fps}"

    # Get and validate PORT
    port_str = os.getenv("PORT")
    if not port_str:
        raise ValueError("PORT environment variable is not set")
    try:
        port = int(port_str)
        logging.info(f"Using port: {port}")
    except ValueError as e:
        raise ValueError(f"Invalid PORT value: {port_str}") from e

    # Determine if we're running on Heroku
    is_heroku = os.getenv("DYNO") is not None
    host = "::" if is_heroku else "127.0.0.1"
    logging.info(f"Running on {'Heroku' if is_heroku else 'localhost'} with host {host}")

    return [
        # Input video source
        (VideoIn, dict(
            id="video_in",
            sources=f"{args.input}!resize=960x540lin!loop",
            outputs="tcp://*:6000"
        )),
        
        # Frame processor - creates multiple output topics
        (FrameProcessor, FrameProcessorConfig(
            id="processor",
            sources="tcp://127.0.0.1:6000",
            outputs="tcp://*:6002",
            main_resize=os.getenv("MAIN_RESIZE", "0") == "1",
            apply_blur=True,
            apply_edge_detection=True,
            apply_overlay=True
        )),
        
        # Frame visualizer - reads from multiple topics
        (FrameVisualizer, FrameVisualizerConfig(
            id="visualizer",
            sources="tcp://127.0.0.1:6002",
            outputs="tcp://*:6004",
            create_combined_view=True,
            create_analytics=True,
            required_topics=["main", "blurred", "edges", "overlay"],
            mq_log="pretty"
        )),
        
        # Web visualization for all streams
        (Webvis, dict(
            id="webvis",
            sources="tcp://127.0.0.1:6004",
            host=host,  # Use appropriate host based on environment
            port=port,
        ))
    ]

def main():
    # Configure logging first
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger = logging.getLogger(__name__)

    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--input",
            default=os.getenv("VIDEO_SOURCE", "file://./assets/sample-video.mp4!loop"),
            help="Input video URI")
        parser.add_argument("--fps", type=int,
            default=int(os.getenv("OUTPUT_FPS", 30)))
        args = parser.parse_args()

        logger.info("Starting application...")
        logger.info(f"Video source: {args.input}")
        logger.info(f"Output FPS: {args.fps}")
        logger.info(f"Output directory: {os.getenv('OUTPUT_DIR', '/tmp/output')}")

        Filter.run_multi(build_pipeline(args))
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
