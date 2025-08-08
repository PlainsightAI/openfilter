# Text Generator Demo

This example demonstrates a custom OpenFilter that generates frames with text for OCR testing. The filter creates black frames with text at different coordinates and can output the main frame and/or individual text crops based on configuration variables.

## Features

- **Text Generation**: Creates black frames with customizable text at specified coordinates
- **Configurable Output**: Can output main frame, individual text crops, or both
- **Dynamic Topic Naming**: Text crops are output to dynamically named topics
- **Multiple Text Support**: Can handle multiple texts per frame with different styles
- **Single Text Mode**: Simplified mode for single text generation
- **Simple and Clean**: Focused on text generation without complex observability features

## Filter Classes

### TextGeneratorFilter

The main filter class that supports multiple texts per frame:

- Creates black frames with multiple text regions
- Configurable output modes (main frame, crops, or both)
- Dynamic topic naming for text crops
- Customizable text positions, fonts, and colors

### SingleTextGeneratorFilter

A simplified filter for single text generation:

- Creates frames with a single text
- Outputs only the cropped text region (no main frame)
- Optimized for single text OCR testing

## Configuration Options

### TextGeneratorFilter Options

- `output_main` (bool): Whether to output the main frame (default: True)
- `output_crops` (bool): Whether to output individual text crops (default: True)
- `crop_topic_prefix` (str): Prefix for crop topic names (default: 'text_crop_')
- `frame_width` (int): Width of generated frames (default: 800)
- `frame_height` (int): Height of generated frames (default: 600)
- `texts` (list): List of text configurations with position, style, and color

### SingleTextGeneratorFilter Options

- `text` (str): The text to display (default: 'Sample Text')
- `x` (int): X coordinate for text (default: 100)
- `y` (int): Y coordinate for text (default: 150)
- `font_scale` (float): Font scale factor (default: 2.0)
- `color` (tuple): BGR color tuple (default: (255, 255, 255))
- `frame_width` (int): Width of generated frame (default: 400)
- `frame_height` (int): Height of generated frame (default: 300)
- `crop_topic` (str): Topic name for the text crop (default: 'single_text_crop')

## Usage Examples

### Multi-Text Demo (Main + Crops)

```bash
python main.py multi
```

This demo outputs both the main frame and individual text crops to separate topics.

### Crops-Only Demo (No Main Frame)

```bash
python main.py crops
```

This demo outputs only individual text crops, not the main frame.

### Single Text Demo (Crop Only)

```bash
python main.py single
```

This demo generates a single text and outputs only the cropped text region.

## Output Topics

### Multi-Text Demo Topics

- `main`: The complete frame with all texts
- `text_crop_text_0`: Crop of the first text ("Hello World")
- `text_crop_text_1`: Crop of the second text ("OpenFilter")
- `text_crop_text_2`: Crop of the third text ("OCR Test")

### Crops-Only Demo Topics

- `crop_text_0`: Crop of the first text ("First Text")
- `crop_text_1`: Crop of the second text ("Second Text")
- `crop_text_2`: Crop of the third text ("Third Text")

### Single Text Demo Topics

- `single_text_crop`: Crop of the single text

## Custom Text Configuration

You can customize the texts by modifying the `texts` parameter:

```python
texts=[
    {
        "text": "Custom Text",
        "x": 100,
        "y": 150,
        "font_scale": 2.0,
        "color": (255, 255, 255)  # BGR format
    },
    {
        "text": "Another Text",
        "x": 300,
        "y": 250,
        "font_scale": 1.5,
        "color": (0, 255, 0)  # Green text
    }
]
```

## Configuration

The filters use OpenFilter's standard configuration system with `FilterConfig` classes:

- `TextGeneratorConfig`: Configuration for multi-text generation
- `SingleTextGeneratorConfig`: Configuration for single text generation

All configuration parameters are type-safe and have default values.

## Installation

1. Install the required dependencies:
   ```bash
   pip install -e .
   ```

2. Make sure you have a sample video file named `example_video.mp4` in the directory.

3. Run one of the demo modes:
   ```bash
   python main.py [multi|crops|single]
   ```

## Dependencies

- openfilter[all]==0.1.5
- opencv-python>=4.8.0
- numpy>=1.24.0

## Use Cases

This demo is particularly useful for:

- **OCR Testing**: Generate synthetic text data for testing OCR algorithms
- **Pipeline Development**: Test text processing pipelines with controlled input
- **Performance Testing**: Measure OCR performance on known text
- **Training Data**: Generate training data for text recognition models
- **Debugging**: Isolate text processing issues with controlled inputs 