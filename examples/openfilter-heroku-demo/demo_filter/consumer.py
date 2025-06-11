import logging
import time
import cv2
import numpy as np

from openfilter.filter_runtime.filter import FilterConfig, Filter, Frame

__all__ = ["FrameVisualizerConfig", "FrameVisualizer"]

logger = logging.getLogger(__name__)


class FrameVisualizerConfig(FilterConfig):
    """
    Configuration for FrameVisualizer that processes and visualizes frames.
    """
    create_combined_view: bool = True        # Whether to create a combined visualization of all input topics
    create_analytics: bool = True            # Whether to generate analytics from multiple inputs
    required_topics: list[str] = None        # List of required topics (if None, uses ["main", "blurred", "edges", "overlay"])


class FrameVisualizer(Filter):
    """
    A filter that processes and visualizes frames:
    
    1. Reads multiple topics from incoming frames
    2. Processes each topic differently
    3. Creates a combined visualization of all topics
    4. Generates analytics from multiple sources
    
    This demonstrates how to consume multiple different frame topics from an upstream
    filter and process them together.
    """
    
    def setup(self, config: FrameVisualizerConfig):
        """
        Initialize the filter with configuration.
        """
        logger.info("Setting up FrameVisualizer")
        self.config = config
        
        # Set default required topics if not specified
        self.required_topics = config.required_topics or ["main", "blurred", "edges", "overlay"]
        
        # Initialize analytics data
        self.frame_count = 0
        self.last_frame_time = time.time()
        self.fps_history = []
        
        logger.info(f"FrameVisualizer setup completed. Config: {config.__dict__}")
        logger.info(f"Required topics: {self.required_topics}")

    def process(self, frames: dict[str, Frame]):
        """
        Process multiple input topics and create outputs.
        """
        # Check if we have all required topics
        missing_topics = [topic for topic in self.required_topics if topic not in frames]
        if missing_topics:
            logger.warning(f"Missing required topics: {missing_topics}")
            # Continue with available topics
        
        # Calculate FPS
        current_time = time.time()
        if self.frame_count > 0:
            elapsed = current_time - self.last_frame_time
            fps = 1.0 / elapsed if elapsed > 0 else 0
            self.fps_history.append(fps)
            # Keep last 30 frames for smoothing
            if len(self.fps_history) > 30:
                self.fps_history.pop(0)
        
        self.last_frame_time = current_time
        self.frame_count += 1
        
        # Dictionary to hold our output frames
        output_frames = {}
        
        # Process each available topic
        available_topics = set(frames.keys()) & set(self.required_topics)
        topic_frames = {topic: frames[topic] for topic in available_topics}
        
        # Create a combined visualization of all topics
        if self.config.create_combined_view and topic_frames:
            output_frames["combined"] = self._create_combined_view(topic_frames)
            
        # Create analytics from multiple sources
        if self.config.create_analytics and topic_frames:
            output_frames["analytics"] = self._create_analytics(topic_frames)
            
        # Pass through original topics
        for topic, frame in topic_frames.items():
            output_frames[topic] = frame
            
        return output_frames
    
    def _create_combined_view(self, topic_frames: dict[str, Frame]) -> Frame:
        """
        Create a combined visualization of all input topics.
        """
        # Get frame dimensions from first frame
        first_frame = next(iter(topic_frames.values()))
        h, w = first_frame.height, first_frame.width
        
        # Calculate grid dimensions
        n_frames = len(topic_frames)
        grid_cols = min(2, n_frames)
        grid_rows = (n_frames + grid_cols - 1) // grid_cols  # Ceiling division
        
        # Create a blank canvas
        cell_h, cell_w = h // grid_rows, w // grid_cols
        canvas = np.zeros((cell_h * grid_rows, cell_w * grid_cols, 3), dtype=np.uint8)
        
        # Place each frame in the grid
        for i, (topic, frame) in enumerate(topic_frames.items()):
            row, col = i // grid_cols, i % grid_cols
            y, x = row * cell_h, col * cell_w
            
            # Resize frame to fit grid cell
            frame_img = frame.rw_bgr.image
            resized = cv2.resize(frame_img, (cell_w, cell_h))
            
            # Place in canvas
            canvas[y:y+cell_h, x:x+cell_w] = resized
            
            # Add topic label
            cv2.putText(
                canvas, 
                topic, 
                (x + 10, y + 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.7, 
                (0, 255, 0), 
                2
            )
        
        # Add overall info
        avg_fps = sum(self.fps_history) / len(self.fps_history) if self.fps_history else 0
        cv2.putText(
            canvas, 
            f"Combined View | FPS: {avg_fps:.1f} | Frame: {self.frame_count}", 
            (10, canvas.shape[0] - 10), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (255, 255, 255), 
            2
        )
        
        return Frame(
            canvas, 
            {"meta": {"description": "Combined view of all topics", "frame_num": self.frame_count}}, 
            "BGR"
        )
    
    def _create_analytics(self, topic_frames: dict[str, Frame]) -> Frame:
        """
        Create analytics from multiple sources.
        """
        # Start with a blank image for analytics visualization
        h, w = 300, 600
        analytics_img = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Calculate statistics from different topics
        stats = {}
        
        # Example: Calculate average brightness from main frame
        if "main" in topic_frames:
            main_frame = topic_frames["main"]
            gray = cv2.cvtColor(main_frame.rw_bgr.image, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            stats["brightness"] = brightness
            
        # Example: Calculate edge density from edges frame
        if "edges" in topic_frames:
            edges_frame = topic_frames["edges"]
            # Convert to grayscale if it's not already
            if edges_frame.format != "GRAY":
                edges_gray = cv2.cvtColor(edges_frame.rw_bgr.image, cv2.COLOR_BGR2GRAY)
            else:
                edges_gray = edges_frame.image
                
            # Count white pixels (edges)
            edge_density = np.count_nonzero(edges_gray) / (edges_gray.shape[0] * edges_gray.shape[1])
            stats["edge_density"] = edge_density
        
        # Draw analytics info
        y_offset = 100
        for i, (key, value) in enumerate(stats.items()):
            text = f"{key}: {value:.2f}"
            cv2.putText(
                analytics_img, 
                text, 
                (20, y_offset), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.7, 
                (255, 255, 255), 
                2
            )
            y_offset += 30
            
        # Add title and frame info
        cv2.putText(
            analytics_img, 
            "Analytics Dashboard", 
            (20, 30), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            1.0, 
            (0, 255, 255), 
            2
        )
        
        avg_fps = sum(self.fps_history) / len(self.fps_history) if self.fps_history else 0
        cv2.putText(
            analytics_img, 
            f"FPS: {avg_fps:.1f} | Frame: {self.frame_count}", 
            (20, h - 20), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (0, 255, 255), 
            2
        )
        
        # Create metadata with all statistics
        metadata = {
            "meta": {
                "description": "Analytics from multiple topics",
                "frame_num": self.frame_count,
                "stats": stats
            }
        }
        
        return Frame(analytics_img, metadata, "BGR")

    def shutdown(self):
        """
        Called once when the filter is shutting down.
        """
        logger.info("Shutting down FrameVisualizer")
        logger.info("FrameVisualizer shutdown complete.")


if __name__ == "__main__":
    FrameVisualizer.run() 