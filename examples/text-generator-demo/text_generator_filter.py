"""
Text Generator Filter - Custom filter that creates frames with text for OCR testing.

This filter demonstrates:
1. Creating black frames with text at different coordinates
2. Configurable output topics for main frame and individual text crops
3. Dynamic topic naming for text crops
4. Different output modes (main only, crops only, or both)

## Running the Demo

Run different configurations using Python commands:

### 1. Multi-Text Demo (Default) - Main Frame + Text Crops
```bash
python main.py multi
# or just
python main.py
```
- Outputs the main frame with all texts
- Also outputs individual text crops on separate topics
- Uses TextGeneratorFilter with multiple text configurations

### 2. Crops-Only Demo - No Main Frame
```bash
python main.py crops
```
- Outputs only individual text crops (no main frame)
- Useful for testing OCR on isolated text regions
- Uses TextGeneratorFilter with output_main=False

### 3. Single Text Demo - Single Crop Only
```bash
python main.py single
```
- Outputs only one text crop
- Uses SingleTextGeneratorFilter for simplified processing
- Good for focused OCR testing

## Configuration Options

### TextGeneratorConfig Parameters:
- `output_main: bool` - Whether to output the main frame with all texts
- `output_crops: bool` - Whether to output individual text crops
- `crop_topic_prefix: str` - Prefix for crop topic names (e.g., 'crop_')
- `frame_width/height: int` - Dimensions of generated frames
- `texts: list` - List of text configurations with:
  - `text: str` - Text content to render
  - `x, y: int` - Position coordinates
  - `font_scale: float` - Text size multiplier
  - `color: tuple` - RGB color values (0-255)

### SingleTextGeneratorConfig Parameters:
- `text: str` - Single text content
- `x, y: int` - Position coordinates
- `font_scale: float` - Text size
- `color: tuple` - RGB color values
- `frame_width/height: int` - Frame dimensions
- `crop_topic: str` - Output topic name for the crop

## Output Topics
- Main frame: Uses the configured outputs parameter
- Text crops: Dynamic topics like 'crop_text_0', 'crop_text_1', etc.
- Single crop: Uses the configured crop_topic parameter

## Use Cases
- OCR algorithm testing and validation
- Synthetic training data generation
- Pipeline testing with known text content
- Benchmarking text detection accuracy
"""

import cv2
import numpy as np
from typing import Dict
from openfilter.filter_runtime import Filter, Frame, FilterConfig


class TextGeneratorConfig(FilterConfig):
    """Configuration for the text generator filter."""
    output_main: bool = True
    output_crops: bool = True
    crop_topic_prefix: str = 'text_crop_'
    frame_width: int = 800
    frame_height: int = 600
    texts: list = None
    mq_log: str | bool | None = None


class TextGeneratorFilter(Filter):
    """Custom filter that generates frames with text for OCR testing.
    
    This filter creates black frames with text at different coordinates
    and can output the main frame and/or individual text crops based on
    configuration variables.
    """
    
    def setup(self, config):
        """Setup the filter."""
        self.config = config
        
        # Set default texts if not provided
        if config.texts is None:
            config.texts = [
                {"text": "Hello World", "x": 100, "y": 150, "font_scale": 2.0, "color": (255, 255, 255)},
                {"text": "OpenFilter", "x": 300, "y": 250, "font_scale": 1.5, "color": (255, 255, 0)},
                {"text": "OCR Test", "x": 500, "y": 350, "font_scale": 1.0, "color": (0, 255, 255)}
            ]
        
        # Frame counter for unique identification
        self.frame_counter = 0
        
        print(f"[TextGeneratorFilter] Setup complete with config: {config}")
    
    def create_text_frame(self):
        """Create a black frame with text at specified coordinates."""
        # Create black frame
        frame = np.zeros((self.config.frame_height, self.config.frame_width, 3), dtype=np.uint8)
        
        # Add text regions
        text_regions = []
        
        for i, text_config in enumerate(self.config.texts):
            text = text_config["text"]
            x = text_config["x"]
            y = text_config["y"]
            font_scale = text_config["font_scale"]
            color = text_config["color"]
            
            # Add text to frame
            cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 
                       font_scale, color, 2)
            
            # Calculate text bounding box (approximate)
            (text_width, text_height), baseline = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2
            )
            
            # Create bounding box with some padding
            bbox = [
                max(0, x - 10),
                max(0, y - text_height - 10),
                min(self.config.frame_width, x + text_width + 10),
                min(self.config.frame_height, y + baseline + 10)
            ]
            
            text_regions.append({
                "text": text,
                "bbox": bbox,
                "region_id": f"text_{i}",
                "confidence": 1.0  # Perfect text since we generated it
            })
        
        return frame, text_regions
    
    def crop_text_regions(self, frame, text_regions):
        """Crop individual text regions from the main frame."""
        crops = {}
        
        for region in text_regions:
            bbox = region["bbox"]
            x1, y1, x2, y2 = bbox
            
            # Crop the region
            crop = frame[y1:y2, x1:x2]
            
            # Create crop data
            crop_data = {
                "text": region["text"],
                "bbox": bbox,
                "region_id": region["region_id"],
                "confidence": region["confidence"],
                "crop_width": x2 - x1,
                "crop_height": y2 - y1
            }
            
            # Store crop with dynamic topic name
            topic_name = f"{self.config.crop_topic_prefix}{region['region_id']}"
            crops[topic_name] = {
                "image": crop,
                "data": crop_data
            }
        
        return crops
    
    def process(self, frames: Dict[str, Frame]) -> Dict[str, Frame]:
        """Process frames and generate text frames with optional crops."""
        processed_frames = {}
        
        for frame_id, frame in frames.items():
            # Generate new frame with text
            text_frame, text_regions = self.create_text_frame()
            
            # Create frame data
            frame_data = {
                "text_regions": text_regions,
                "frame_width": self.config.frame_width,
                "frame_height": self.config.frame_height,
                "frame_id": self.frame_counter,
                "total_texts": len(text_regions)
            }
            
            # Add main frame if configured
            if self.config.output_main:
                # Update the existing frame with new image and data    
                processed_frames[frame_id] = Frame(
                        text_frame,
                        frame.data.update(frame_data),
                        "BGR"
                    )
            
            # Add individual crops if configured
            if self.config.output_crops:
                crops = self.crop_text_regions(text_frame, text_regions)
                for topic_name, crop_info in crops.items():
                    # Create new frame for each crop
                    processed_frames[topic_name] = Frame(
                        crop_info["image"],
                        {**frame.data, **crop_info["data"]},
                        "BGR"
                    )
            
            self.frame_counter += 1
        
        return processed_frames


class SingleTextGeneratorConfig(FilterConfig):
    """Configuration for the single text generator filter."""
    text: str = 'Sample Text'
    x: int = 100
    y: int = 150
    font_scale: float = 2.0
    color: tuple = (255, 255, 255)
    frame_width: int = 400
    frame_height: int = 300
    crop_topic: str = 'single_text_crop'
    mq_log: str | bool | None = None


class SingleTextGeneratorFilter(Filter):
    """Simplified filter that generates frames with a single text for OCR testing.
    
    This filter creates black frames with a single text and outputs only the
    cropped text region, not the main frame.
    """
    
    def setup(self, config):
        """Setup the filter."""
        self.config = config
        
        # Frame counter for unique identification
        self.frame_counter = 0
        
        print(f"[SingleTextGeneratorFilter] Setup complete with config: {config}")
    
    def create_single_text_frame(self):
        """Create a black frame with a single text."""
        # Create black frame
        frame = np.zeros((self.config.frame_height, self.config.frame_width, 3), dtype=np.uint8)
        
        # Add text to frame
        cv2.putText(frame, self.config.text, (self.config.x, self.config.y), cv2.FONT_HERSHEY_SIMPLEX, 
                   self.config.font_scale, self.config.color, 2)
        
        # Calculate text bounding box
        (text_width, text_height), baseline = cv2.getTextSize(
            self.config.text, cv2.FONT_HERSHEY_SIMPLEX, self.config.font_scale, 2
        )
        
        # Create bounding box with padding
        bbox = [
            max(0, self.config.x - 10),
            max(0, self.config.y - text_height - 10),
            min(self.config.frame_width, self.config.x + text_width + 10),
            min(self.config.frame_height, self.config.y + baseline + 10)
        ]
        
        # Crop the text region
        x1, y1, x2, y2 = bbox
        crop = frame[y1:y2, x1:x2]
        
        return crop, {
            "text": self.config.text,
            "bbox": bbox,
            "confidence": 1.0,
            "crop_width": x2 - x1,
            "crop_height": y2 - y1,
            "frame_id": self.frame_counter
        }
    
    def process(self, frames: Dict[str, Frame]) -> Dict[str, Frame]:
        """Process frames and generate single text crops."""
        processed_frames = {}
        
        for frame_id, frame in frames.items():
            # Generate crop with single text
            text_crop, crop_data = self.create_single_text_frame()
            
            # Output only the crop, not the main frame
            processed_frames[self.config.crop_topic] = Frame(
                text_crop,
                {**frame.data, **crop_data},
                "BGR"
            )
            
            self.frame_counter += 1
        
        return processed_frames 