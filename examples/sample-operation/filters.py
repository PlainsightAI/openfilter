import os, logging, argparse
from dotenv import load_dotenv

# Load .env from the app directory
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

from openfilter.filter_runtime import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.util import Util, Util
from openfilter.filter_runtime.filters.webvis import Webvis

def build_pipeline(args):
    return [
        # Input video source
        (VideoIn, dict(
            id="video_in",
            sources=f"{args.input}!resize=960x540lin!loop",
            outputs="tcp://*:6000"
        )),
        
        # Frame processor - creates multiple output topics
        (Util, dict(
            id="processor",
            sources="tcp://127.0.0.1:6000",
            outputs="tcp://*:6002",
            xforms=["rotcw"]  # Apply 90-degree clockwise rotation
        )),
        
        # Web visualization for all streams
        (Webvis, dict(
            id="webvis",
            sources="tcp://127.0.0.1:6000",
            host='127.0.0.1',  # Use appropriate host based on environment
            port=8000,
        )),
        
        # Web visualization for all streams
        (Webvis, dict(
            id="webvis",
            sources="tcp://127.0.0.1:6002",
            host='127.0.0.1',  # Use appropriate host based on environment
            port=8001,
        )),
    ]

def main():
    # Configure logging first
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger = logging.getLogger(__name__)

    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--input",
            default=os.getenv("VIDEO_SOURCE", "file://../openfilter-heroku-demo/assets/sample-video.mp4!loop"),
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
