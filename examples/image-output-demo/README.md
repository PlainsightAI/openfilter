# ImageOut Filter Demo

This example demonstrates how to use the `ImageOut` filter to save video frames as individual image files in various formats. The demo creates a complete pipeline: **VideoIn** reads a sample video, **WebVis** provides real-time visualization in your browser, and **ImageOut** saves frames in multiple formats.

## Features

The demo pipeline includes:

- **VideoIn**: Reads video from file with configurable options
- **WebVis**: Real-time web-based visualization at http://localhost:8000
- **ImageOut**: Saves frames in multiple formats with quality control

The `ImageOut` filter supports:

- **Multiple image formats**: PNG, JPG, BMP, TIFF, WebP
- **Multiple topics**: Save different topics to different outputs
- **Flexible naming**: Support for strftime formatting and frame numbering
- **Quality control**: JPEG quality (1-100) and PNG compression (0-9)
- **Color format conversion**: Automatic RGB/BGR conversion
- **Directory creation**: Automatically creates output directories

## Configuration Options

### Global Options

```python
config = FilterConfig({
    'outputs': ['file:///path/to/images_%Y%m%d_%H%M%S_%d.png'],
    'bgr': True,           # Image format (True=BGR, False=RGB)
    'format': 'png',       # Default format (auto-detected from extension)
    'quality': 95,         # JPEG quality (1-100)
    'compression': 6       # PNG compression (0-9)
})
```

### Per-Output Options

You can specify options for each output using the `!` syntax:

```python
config = FilterConfig({
    'outputs': [
        'file:///path/to/high_quality.png!format=png!compression=0',
        'file:///path/to/medium_quality.jpg!format=jpg!quality=85',
        'file:///path/to/processed.png;processed_topic!format=png'
    ]
})
```

### Filename Formatting

The output filename supports:
- **strftime formatting**: `%Y%m%d_%H%M%S` for timestamps
- **Frame numbering**: `%d` for zero-padded frame numbers
- **Topic mapping**: Use `;topic_name` to map specific topics

Examples:
- `file:///images/frame_%Y%m%d_%H%M%S_%d.png` → `frame_20241201_143022_000001.png`
- `file:///output;camera1` → saves topic 'camera1' to `/output` directory

## Environment Variables

- `IMAGE_OUT_BGR`: Default BGR setting (true/false)
- `IMAGE_OUT_QUALITY`: Default JPEG quality (1-100)
- `IMAGE_OUT_COMPRESSION`: Default PNG compression (0-9)

## Usage Example

```python
from openfilter.filter_runtime.filters.image_out import ImageOut

# Configure the filter
config = FilterConfig({
    'id': 'image-saver',
    'sources': ['tcp://127.0.0.1:5550'],
    'outputs': [
        'file:///output/frames_%Y%m%d_%H%M%S_%d.png!format=png!compression=0',
        'file:///output/frames_%Y%m%d_%H%M%S_%d.jpg!format=jpg!quality=90'
    ]
})

# Run the filter
ImageOut.run(config)
```

## Running the Demo

```bash
cd openfilter/examples/image-output-demo
python main.py
```

This will:
1. **Read the sample video** from `../openfilter-heroku-demo/assets/sample-video.mp4`
2. **Start WebVis** at http://localhost:8000 for real-time visualization
3. **Save frames** in multiple formats (PNG, JPG, WebP, BMP) with different quality settings
4. **Generate timestamped files** in the `output/` directory

### Pipeline Flow

```
VideoIn (sample-video.mp4) 
    ↓ tcp://127.0.0.1:5550
WebVis (http://localhost:8000) 
    ↓ tcp://127.0.0.1:5551  
ImageOut (multiple formats)
```

### Web Visualization

Once the demo starts:
1. Open your browser
2. Go to http://localhost:8000
3. Watch the video frames in real-time
4. The same frames are being saved as images in the background

## Supported Formats

| Format | Extension | Quality Control | Notes |
|--------|-----------|-----------------|-------|
| PNG    | .png      | Compression (0-9) | Lossless, supports transparency |
| JPEG   | .jpg/.jpeg | Quality (1-100) | Lossy, smaller file sizes |
| BMP    | .bmp      | None            | Uncompressed, large files |
| TIFF   | .tiff/.tif | None            | Lossless, professional format |
| WebP   | .webp     | Quality (1-100) | Modern format, good compression |

## Integration with Other Filters

The ImageOut filter can be used in pipelines with other filters:

```python
# Video pipeline with image saving
Filter.run_multi([
    (VideoIn, video_config),      # Read video
    (SomeProcessor, proc_config), # Process frames
    (ImageOut, image_config)      # Save processed frames
])
```

The filter automatically handles frame data and metadata, using frame IDs and timestamps for unique filenames when available.
