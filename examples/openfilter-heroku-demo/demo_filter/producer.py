import logging
import time
import cv2
import numpy as np

from openfilter.filter_runtime.filter import FilterConfig, Filter, Frame

__all__ = ["FrameProcessorConfig", "FrameProcessor"]

logger = logging.getLogger(__name__)


class FrameProcessorConfig(FilterConfig):
    """
    Configuration for FrameProcessor that processes frames into different visualizations.
    """
    main_resize: bool = False              # Whether to resize the main stream
    apply_blur: bool = True                # Apply Gaussian blur to blurred topic
    apply_edge_detection: bool = True      # Apply edge detection to edges topic
    apply_overlay: bool = True             # Add timestamp overlay to overlay topic


class FrameProcessor(Filter):
    """
    A filter that processes frames into different visualizations:
    
    1. main - The original input frame, possibly resized
    2. blurred - A blurred version of the input
    3. edges - Edge detection applied to the input
    4. overlay - The input with timestamp and counter overlay
    
    This demonstrates creating multiple different processed versions of an input frame,
    each available as a separate topic for downstream filters to consume.
    """
    
    def setup(self, config: FrameProcessorConfig):
        """
        Initialize the filter with configuration.
        """
        logger.info("Setting up FrameProcessor")
        self.config = config
        self.frame_count = 0
        
        logger.info(f"FrameProcessor setup completed. Config: {config.__dict__}")

    def process(self, frames: dict[str, Frame]):
        """
        Process the input frame and produce multiple output topics.
        """
        # Get input frame - assume "input" is the topic name or use the first one
        input_frame = frames.get("input") or next(iter(frames.values()))
        if not input_frame or not input_frame.has_image:
            logger.warning("No valid input frame received")
            return {}
        
        # Increment frame counter
        self.frame_count += 1
        current_time = time.time()
        
        # Dictionary to hold our output frames with different topics
        output_frames = {}
        
        # Process main frame (possibly resized)
        bgr_image = input_frame.rw_bgr.image
        if self.config.main_resize:
            bgr_image = cv2.resize(bgr_image, (0, 0), fx=0.75, fy=0.75)
        
        # Add base frame to output
        output_frames["main"] = Frame(
            bgr_image.copy(), 
            {"meta": {"description": "Original frame", "frame_num": self.frame_count}}, 
            "BGR"
        )
        
        # Add blurred version
        if self.config.apply_blur:
            blurred_image = cv2.GaussianBlur(bgr_image, (15, 15), 0)
            output_frames["blurred"] = Frame(
                blurred_image, 
                {"meta": {"description": "Blurred frame", "frame_num": self.frame_count}}, 
                "BGR"
            )
        
        # Add edge detection
        if self.config.apply_edge_detection:
            gray_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
            edges_image = cv2.Canny(gray_image, 100, 200)
            # Convert back to BGR for compatibility
            edges_bgr = cv2.cvtColor(edges_image, cv2.COLOR_GRAY2BGR)
            output_frames["edges"] = Frame(
                edges_bgr, 
                {"meta": {"description": "Edge detection", "frame_num": self.frame_count}}, 
                "BGR"
            )
        
        # Add timestamp overlay
        if self.config.apply_overlay:
            overlay_image = bgr_image.copy()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            text = f"Frame: {self.frame_count} | Time: {timestamp}"
            
            # Add text to image
            cv2.putText(
                overlay_image, 
                text, 
                (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.7, 
                (0, 0, 255), 
                2
            )
            
            output_frames["overlay"] = Frame(
                overlay_image, 
                {"meta": {"description": "Frame with overlay", "frame_num": self.frame_count}}, 
                "BGR"
            )
        
        return output_frames

    def shutdown(self):
        """
        Called once when the filter is shutting down.
        """
        logger.info("Shutting down FrameProcessor")
        logger.info("FrameProcessor shutdown complete.")


if __name__ == "__main__":
    FrameProcessor.run() 