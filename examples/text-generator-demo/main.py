"""
Text Generator Demo - Main pipeline demonstrating custom text generation filters.

This example shows different configurations of the TextGeneratorFilter:
1. Output main frame + individual text crops
2. Output only individual text crops (no main frame)  
3. Single text generator with only crop output

## Quick Start

Run any of the three demo modes:

```bash
# Multi-text demo (default) - shows main frame + individual crops
python main.py multi
python main.py  # same as 'multi'

# Crops-only demo - shows only text crops, no main frame
python main.py crops

# Single text demo - shows only one text crop
python main.py single
```

## Demo Modes Explained

### 1. Multi-Text Demo (`python main.py multi`)
- **Purpose**: Demonstrates full pipeline with multiple texts
- **Output**: Main frame containing all texts + individual text crops
- **Topics**: 
  - Main: `tcp://*:5552` (webvis displays this)
  - Crops: `crop_text_0`, `crop_text_1`, `crop_text_2`
- **Configuration**:
  - Frame size: 800x600
  - 3 texts with different colors and sizes
  - Both `output_main=True` and `output_crops=True`

### 2. Crops-Only Demo (`python main.py crops`)  
- **Purpose**: Focus on individual text regions without main frame
- **Output**: Only individual text crops (no main frame)
- **Topics**: `crop_text_0`, `crop_text_1`, `crop_text_2`
- **Configuration**:
  - Frame size: 800x600
  - 3 texts with different properties
  - `output_main=False`, `output_crops=True`
- **Use case**: OCR testing on isolated text regions

### 3. Single Text Demo (`python main.py single`)
- **Purpose**: Simplified pipeline for single text processing
- **Output**: One text crop only
- **Topics**: `single_text_crop`
- **Configuration**:
  - Frame size: 400x300 (smaller)
  - Single text: "Single Text Sample"
  - Uses `SingleTextGeneratorFilter`
- **Use case**: Focused OCR testing or simple text generation

## Configuration Examples

### TextGeneratorConfig (Multi/Crops demos):
```python
config = TextGeneratorConfig(
    id="multi_text_generator",
    sources="tcp://localhost:5550",     # Input from VideoIn
    outputs="tcp://*:5552",             # Output to Webvis
    output_main=True,                   # Include main frame
    output_crops=True,                  # Include text crops
    crop_topic_prefix='crop_',          # Crop topics: crop_text_0, etc.
    frame_width=800,                    # Generated frame width
    frame_height=600,                   # Generated frame height
    texts=[                             # List of texts to render
        {
            "text": "Hello World", 
            "x": 100, "y": 150,         # Position coordinates
            "font_scale": 2.0,          # Text size multiplier
            "color": (255, 255, 255)    # RGB color (white)
        },
        # ... more texts
    ]
)
```

### SingleTextGeneratorConfig (Single demo):
```python
config = SingleTextGeneratorConfig(
    id="single_text_generator",
    sources="tcp://localhost:5550",
    outputs="tcp://*:5552", 
    text='Single Text Sample',          # Single text content
    x=150, y=200,                       # Position
    font_scale=2.5,                     # Size
    color=(255, 255, 255),              # Color
    frame_width=400,                    # Frame dimensions
    frame_height=300,
    crop_topic='single_text_crop'       # Output topic name
)
```

## Pipeline Architecture

All demos follow this pattern:
1. **VideoIn**: Reads sample video file (looped)
2. **TextGenerator**: Processes frames, adds text, outputs crops
3. **Webvis**: Displays results in web browser

## Video Sources

- Multi/Crops demos: `../observability-demo/sample_video.mp4`
- Single demo: `../openfilter-heroku-demo/assets/sample-video.mp4`

Both sources use `!loop` to continuously repeat the video.

## Output Visualization

- Open web browser after running any demo
- Webvis will show the generated frames with text
- Different demos will show different output patterns
- Use browser developer tools to see individual topic streams

## Customization Tips

1. **Change text content**: Modify the `texts` list or `text` parameter
2. **Adjust positions**: Change `x`, `y` coordinates 
3. **Resize frames**: Modify `frame_width`, `frame_height`
4. **Change colors**: Use different RGB tuples
5. **Add more texts**: Extend the `texts` list in multi-text configs
6. **Custom topics**: Change `crop_topic_prefix` or `crop_topic`

## Metadata Flow and Process Function Returns

### Multi-Text Demo (`python main.py multi`)

The `TextGeneratorFilter.process()` function returns a dictionary with multiple Frame objects:

```python
# Return structure:
{
    # Main frame (if output_main=True)
    "main_topic": Frame(
        image=numpy_array_800x600x3,    # Generated frame with all texts
        data={
            # Original frame data + new metadata:
            "text_regions": [
                {
                    "text": "Hello World",
                    "bbox": [90, 120, 280, 170],    # [x1, y1, x2, y2]
                    "region_id": "text_0",
                    "confidence": 1.0
                },
                {
                    "text": "OpenFilter", 
                    "bbox": [290, 220, 450, 270],
                    "region_id": "text_1",
                    "confidence": 1.0
                },
                # ... more text regions
            ],
            "frame_width": 800,
            "frame_height": 600,
            "frame_id": 123,                    # Incremental counter
            "total_texts": 3
        },
        format="BGR"
    ),
    
    # Individual text crops (if output_crops=True)
    "crop_text_0": Frame(
        image=numpy_array_cropped,              # Cropped region around "Hello World"
        data={
            # Original frame data + crop-specific metadata:
            "text": "Hello World",
            "bbox": [90, 120, 280, 170],
            "region_id": "text_0", 
            "confidence": 1.0,
            "crop_width": 190,                  # x2 - x1
            "crop_height": 50                   # y2 - y1
        },
        format="BGR"
    ),
    
    "crop_text_1": Frame(
        image=numpy_array_cropped,              # Cropped region around "OpenFilter"
        data={
            "text": "OpenFilter",
            "bbox": [290, 220, 450, 270],
            "region_id": "text_1",
            "confidence": 1.0,
            "crop_width": 160,
            "crop_height": 50
        },
        format="BGR"
    ),
    # ... more crops for each text
}
```

### Crops-Only Demo (`python main.py crops`)

Same as multi-text demo but **excludes the main frame**:

```python
# Return structure (no main frame):
{
    "crop_text_0": Frame(...),    # Same structure as above
    "crop_text_1": Frame(...),
    "crop_text_2": Frame(...)
    # No main topic - only individual crops
}
```

### Single Text Demo (`python main.py single`)

The `SingleTextGeneratorFilter.process()` function returns only one Frame:

```python
# Return structure:
{
    "single_text_crop": Frame(
        image=numpy_array_cropped,              # Cropped region around single text
        data={
            # Original frame data + single text metadata:
            "text": "Single Text Sample",
            "bbox": [140, 150, 340, 200],       # Calculated bounding box
            "confidence": 1.0,
            "crop_width": 200,
            "crop_height": 50,
            "frame_id": 456                     # Incremental counter
        },
        format="BGR"
    )
}
```

## Topic Routing and Message Flow

### 1. Multi-Text Demo Flow:
```
VideoIn(file) 
    ↓ [main_input_topic]
TextGeneratorFilter.process() 
    ↓ [tcp://*:5552] → main frame
    ↓ [crop_text_0] → individual crop
    ↓ [crop_text_1] → individual crop  
    ↓ [crop_text_2] → individual crop
Webvis (displays main frame)
```

### 2. Crops-Only Demo Flow:
```
VideoIn(file)
    ↓ [main_input_topic] 
TextGeneratorFilter.process()
    ↓ [crop_text_0] → individual crop
    ↓ [crop_text_1] → individual crop
    ↓ [crop_text_2] → individual crop
Webvis (may not display anything since no main frame)
```

### 3. Single Text Demo Flow:
```
VideoIn(file)
    ↓ [main_input_topic]
SingleTextGeneratorFilter.process()
    ↓ [tcp://*:5552] → single crop sent as main
Webvis (displays the single crop)
```

## Frame Data Inheritance

All demos preserve original frame data and augment it:

1. **Input Frame Data**: Whatever VideoIn provides (timestamps, frame numbers, etc.)
2. **Generated Metadata**: Text regions, bounding boxes, confidence scores
3. **Crop-Specific Data**: Dimensions, region IDs, cropped coordinates

The `Frame.data.update()` call merges original data with new text-specific metadata, ensuring downstream filters receive complete context about both the video source and generated text content.

## Image Formats and Dimensions

- **Input**: Whatever VideoIn provides (typically BGR from video file)
- **Generated Frames**: Always BGR format, black background (np.zeros)
- **Main Frame**: Full configured dimensions (800x600 or 400x300)
- **Crops**: Variable dimensions based on text bounding boxes + padding
- **Text Rendering**: OpenCV putText with FONT_HERSHEY_SIMPLEX
"""

from openfilter.filter_runtime.filter import Filter
from text_generator_filter import TextGeneratorFilter, SingleTextGeneratorFilter, TextGeneratorConfig, SingleTextGeneratorConfig
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis


def run_multi_text_demo():
    """Run demo with multiple texts - outputs main frame and individual crops."""
    print("Running Multi-Text Demo (Main + Crops)")
    
    # Create configuration
    config = TextGeneratorConfig(
        id="multi_text_generator",
        sources="tcp://localhost:5550",
        outputs="tcp://*:5552",
        output_main=True,  # Output main frame
        output_crops=True,  # Output individual text crops
        crop_topic_prefix='crop_',
        frame_width=800,
        frame_height=600,
        texts=[
            {"text": "Hello World", "x": 100, "y": 150, "font_scale": 2.0, "color": (255, 255, 255)},
            {"text": "OpenFilter", "x": 300, "y": 250, "font_scale": 1.5, "color": (255, 255, 0)},
            {"text": "OCR Test", "x": 500, "y": 350, "font_scale": 1.0, "color": (0, 255, 255)}
        ]
    )
    
    Filter.run_multi([
        (VideoIn, dict(
            sources='file://../observability-demo/sample_video.mp4!loop',
            outputs='tcp://*:5550',
        )),
        (TextGeneratorFilter, config),
        (Webvis, dict(
            sources='tcp://localhost:5552',
        )),
    ])


def run_crops_only_demo():
    """Run demo with multiple texts - outputs only individual crops (no main frame)."""
    print("Running Crops-Only Demo (No Main Frame)")
    
    # Create configuration
    config = TextGeneratorConfig(
        id="crops_only_generator",
        sources="tcp://localhost:5550",
        outputs="tcp://*:5552",
        output_main=False,  # Don't output main frame
        output_crops=True,   # Output individual text crops
        crop_topic_prefix='crop_',
        frame_width=800,
        frame_height=600,
        texts=[
            {"text": "First Text", "x": 100, "y": 150, "font_scale": 2.0, "color": (255, 255, 255)},
            {"text": "Second Text", "x": 300, "y": 250, "font_scale": 1.5, "color": (255, 255, 0)},
            {"text": "Third Text", "x": 500, "y": 350, "font_scale": 1.0, "color": (0, 255, 255)}
        ]
    )
    
    Filter.run_multi([
        (VideoIn, dict(
            sources='file://../observability-demo/sample_video.mp4!loop',
            outputs='tcp://*:5550',
        )),
        (TextGeneratorFilter, config),
        (Webvis, dict(
            sources='tcp://localhost:5552',
        )),
    ])


def run_single_text_demo():
    """Run demo with single text - outputs only the text crop."""
    print("Running Single Text Demo (Crop Only)")
    
    # Create configuration
    config = SingleTextGeneratorConfig(
        id="single_text_generator",
        sources="tcp://localhost:5550",
        outputs="tcp://*:5552",
        text='Single Text Sample',
        x=150,
        y=200,
        font_scale=2.5,
        color=(255, 255, 255),
        frame_width=400,
        frame_height=300,
        crop_topic='single_text_crop'
    )
    
    Filter.run_multi([
        (VideoIn, dict(
            sources='file:///Users/navarmn/dev/plainsight/openfilter/examples/openfilter-heroku-demo/assets/sample-video.mp4!loop',
            outputs='tcp://*:5550',
        )),
        (SingleTextGeneratorFilter, config),
        (Webvis, dict(
            sources='tcp://localhost:5552',
        )),
    ])


if __name__ == '__main__':
    import sys
    
    # Choose demo based on command line argument
    if len(sys.argv) > 1:
        demo_type = sys.argv[1].lower()
        
        if demo_type == 'multi':
            run_multi_text_demo()
        elif demo_type == 'crops':
            run_crops_only_demo()
        elif demo_type == 'single':
            run_single_text_demo()
        else:
            print("Usage: python main.py [multi|crops|single]")
            print("  multi  - Output main frame + individual text crops")
            print("  crops  - Output only individual text crops (no main)")
            print("  single - Output single text crop only")
            sys.exit(1)
    else:
        # Default to multi-text demo
        print("No demo type specified, running multi-text demo...")
        run_multi_text_demo() 