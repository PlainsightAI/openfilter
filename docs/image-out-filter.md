# ImageOut Filter

The ImageOut filter is an output filter for OpenFilter that writes images from incoming frames to local files. It supports multiple image formats, topic-based routing, wildcard topic matching, and flexible filename formatting with timestamps and frame numbering.

## Overview

The ImageOut filter is designed to handle image output scenarios where you need to:
- Save processed images to local filesystem
- Write images in multiple formats (JPEG, PNG, BMP, TIFF, WebP)
- Route different topics to different output locations
- Use wildcard patterns to match multiple topics
- Generate timestamped and numbered filenames
- Control image quality and compression settings
- Handle multiple concurrent outputs

## Key Features

- **Multiple Image Formats**: JPEG, PNG, BMP, TIFF, WebP with format-specific options
- **Topic Routing**: Route different topics to different output files/locations
- **Wildcard Matching**: Use `*` patterns to match multiple topics (e.g., `face_*`)
- **Flexible Filenames**: Support for strftime formatting and frame numbering
- **Quality Control**: Configurable JPEG quality and PNG compression
- **Multiple Outputs**: Write the same topic to multiple locations
- **Format Detection**: Automatic format detection from file extensions
- **Directory Creation**: Automatically creates output directories

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_out import ImageOut

# Simple single output
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///path/to/output_%Y%m%d_%H%M%S_%d.png',
    )),
])
```

### Advanced Configuration with Multiple Outputs

```python
# Multiple outputs with different topics and options
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs=[
            'file:///path/to/main_images_%Y%m%d_%H%M%S_%d.jpg;main!quality=95',
            'file:///path/to/face_images_%d.png;face_*!compression=9',
            'file:///path/to/detections_%d.bmp;detection!no-bgr',
        ],
        format='jpg',  # Default format for all outputs
        quality=90,    # Default quality for JPEG outputs
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="tcp://localhost:5550"
export FILTER_OUTPUTS="file:///path/to/images_%d.jpg"
export IMAGE_OUT_BGR="true"
export IMAGE_OUT_QUALITY="95"
export IMAGE_OUT_COMPRESSION="6"
```

## Output URI Formats

### File Outputs
```
file:///absolute/path/to/image_%Y%m%d_%H%M%S_%d.png
file://relative/path/to/image_%d.jpg
file:///path/to/folder/image.png
```

### Filename Formatting
- **strftime formatting**: Use standard Python strftime codes
  - `%Y` - 4-digit year
  - `%m` - Month (01-12)
  - `%d` - Day of month (01-31)
  - `%H` - Hour (00-23)
  - `%M` - Minute (00-59)
  - `%S` - Second (00-59)
- **Frame numbering**: Use `%d` for 6-digit zero-padded frame numbers
- **Frame ID**: Frame data metadata is used for unique identifiers

## Topic Mapping

### Basic Topic Mapping
```
'file:///path/to/image.jpg;main'     # Route 'main' topic to this file
'file:///path/to/image.jpg;camera1'  # Route 'camera1' topic to this file
'file:///path/to/image.jpg'          # Default to 'main' topic
```

### Wildcard Topic Matching
```
'file:///path/to/faces_%d.png;face_*'     # Match all topics starting with 'face_'
'file:///path/to/detections_%d.jpg;*'     # Match all topics (not recommended)
'file:///path/to/cameras_%d.jpg;camera_*' # Match all topics starting with 'camera_'
```

### Multiple Outputs per Topic
```
# Same topic can be written to multiple locations
'file:///backup/images_%d.jpg;main',
'file:///archive/images_%d.png;main',
'file:///processed/images_%d.jpg;main',
```

## Output Options

You can append options to output URIs using the `!` syntax:

### Format Options
- `!format=jpg` - Force JPEG format
- `!format=png` - Force PNG format
- `!format=bmp` - Force BMP format
- `!format=tiff` - Force TIFF format
- `!format=webp` - Force WebP format

### Color Space Options
- `!bgr` - Images are in BGR format (default)
- `!no-bgr` - Images are in RGB format

### Quality Options (JPEG/WebP only)
- `!quality=95` - JPEG quality 1-100 (higher = better quality)
- `!quality=80` - Lower quality, smaller file size

### Compression Options (PNG only)
- `!compression=6` - PNG compression level 0-9 (higher = better compression)

## Configuration Options

### Global Options
These apply to all outputs unless overridden:

- `outputs`: List of output URIs with optional topic mapping and options
- `bgr`: Global BGR/RGB setting for all outputs
- `format`: Global format override for all outputs
- `quality`: Global JPEG quality for all outputs
- `compression`: Global PNG compression for all outputs

### Per-Output Options
These can be set per output using the `!` syntax:

- `format`: Image format for this specific output
- `bgr`: BGR/RGB setting for this specific output
- `quality`: JPEG quality for this specific output
- `compression`: PNG compression for this specific output

## Supported Image Formats

| Format | Extension | Quality Control | Compression | Notes |
|--------|-----------|----------------|-------------|-------|
| JPEG   | .jpg, .jpeg | ✅ (1-100) | ❌ | Most common, good compression |
| PNG    | .png | ❌ | ✅ (0-9) | Lossless, supports transparency |
| BMP    | .bmp | ❌ | ❌ | Uncompressed, large files |
| TIFF   | .tiff, .tif | ❌ | ❌ | High quality, large files |
| WebP   | .webp | ✅ (1-100) | ❌ | Modern format, good compression |

## Filename Generation

The ImageOut filter generates unique filenames using multiple strategies:

### Frame Numbering (`%d`)
```python
# Output pattern: file:///path/image_%d.jpg
# Generated files:
# image_000001.jpg
# image_000002.jpg
# image_000003.jpg
```

### Timestamp Formatting
```python
# Output pattern: file:///path/image_%Y%m%d_%H%M%S_%d.png
# Generated files:
# image_20241201_143052_000001.png
# image_20241201_143052_000002.png
```

### Frame ID Integration
```python
# Uses frame.data.meta.id or frame.data.meta.frame_id
# Output pattern: file:///path/image_%d.jpg
# Generated files:
# image_main_12345.jpg  # topic_main + frame_id
# image_face_67890.jpg  # topic_face + frame_id
```

## Usage Examples

### Example 1: Basic Image Saving
```python
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output/images_%d.jpg',
    )),
])
```

**Behavior:** Saves all incoming images as JPEG files with sequential numbering.

### Example 2: Multiple Topics with Different Formats
```python
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs=[
            'file:///output/main_%Y%m%d_%d.jpg;main!quality=95',
            'file:///output/faces_%d.png;face_*!compression=9',
            'file:///output/detections_%d.bmp;detection!no-bgr',
        ],
    )),
])
```

**Behavior:** Routes different topics to different formats and locations.

### Example 3: Wildcard Topic Matching
```python
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output/cameras_%d.jpg;camera_*!quality=90',
    )),
])
```

**Behavior:** Matches all topics starting with 'camera_' and saves them with quality 90.

### Example 4: Timestamped Outputs
```python
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output/images_%Y%m%d_%H%M%S_%d.png',
        format='png',
        compression=6,
    )),
])
```

**Behavior:** Creates timestamped PNG files with compression level 6.

### Example 5: Backup Strategy
```python
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs=[
            'file:///primary/images_%d.jpg;main!quality=95',
            'file:///backup/images_%d.jpg;main!quality=80',
            'file:///archive/images_%d.png;main!compression=9',
        ],
    )),
])
```

**Behavior:** Saves the same images to multiple locations with different quality settings.

### Example 6: Frame Processing Pipeline
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='file://input.mp4',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms='resize 1280x720',
    )),
    (ImageOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///processed/frame_%06d.jpg!quality=90',
    )),
])
```

**Behavior:** Processes video frames, resizes them, and saves as high-quality JPEG files.

## Error Handling

The ImageOut filter handles various error conditions gracefully:

### Missing Images
- Logs warning for frames without image data
- Continues processing other frames
- Skips invalid frames without crashing

### File System Issues
- Automatically creates output directories
- Handles permission errors gracefully
- Logs detailed error messages

### Invalid Formats
- Validates format parameters
- Falls back to extension-based format detection
- Logs warnings for unsupported formats

### Topic Matching Issues
- Warns when expected topics are not found
- Continues processing available topics
- Handles wildcard matching errors gracefully

## Performance Considerations

### File I/O
- Images are written synchronously (blocking)
- Consider using multiple outputs for parallel writing
- SSD storage recommended for high-throughput scenarios

### Memory Usage
- Only image data is held in memory during write
- No image caching or buffering
- Memory usage scales with image size

### Concurrent Outputs
- Each output is independent
- No synchronization between outputs
- Thread-safe for multiple concurrent writes

### Format Selection
- JPEG: Fastest encoding, good compression
- PNG: Slower encoding, lossless quality
- BMP: Fastest encoding, no compression
- TIFF: Slower encoding, large files
- WebP: Good compression, modern format

## Troubleshooting

### Common Issues

#### Images Not Being Saved
1. Check output directory exists and is writable
2. Verify topic names match exactly
3. Ensure frames contain image data
4. Check file permissions

#### Wrong Image Format
1. Verify file extension matches desired format
2. Check format option syntax
3. Ensure OpenCV supports the format
4. Validate quality/compression parameters

#### Filename Issues
1. Check strftime format codes
2. Verify frame numbering syntax
3. Ensure frame metadata is available
4. Test filename pattern generation

#### Performance Issues
1. Use faster formats (JPEG over PNG)
2. Reduce image quality for smaller files
3. Use SSD storage
4. Consider multiple outputs for parallel writing

### Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed information about:
- Image writing operations
- Topic matching
- Filename generation
- Error conditions
- Format detection

## Advanced Usage

### Custom Filename Generation
```python
# Using frame metadata for custom naming
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output/camera_{frame_id}_%d.jpg',
        # Frame metadata will be used for {frame_id} placeholder
    )),
])
```

### Quality-Based Routing
```python
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs=[
            'file:///high_quality/images_%d.jpg;main!quality=95',
            'file:///low_quality/images_%d.jpg;main!quality=60',
        ],
    )),
])
```

### Format Conversion Pipeline
```python
Filter.run_multi([
    (ImageOut, dict(
        sources='tcp://localhost:5550',
        outputs=[
            'file:///converted/images_%d.jpg!format=jpg!quality=90',
            'file:///converted/images_%d.png!format=png!compression=6',
        ],
    )),
])
```

## API Reference

### ImageOutConfig
```python
class ImageOutConfig(FilterConfig):
    class Output(adict):
        class Options(adict):
            bgr: bool | None
            format: str | None
            quality: int | None
            compression: int | None

        output: str
        topic: str | None
        options: Options | None

    outputs: str | list[str | Output]
    bgr: bool | None
    format: str | None
    quality: int | None
    compression: int | None
```

### ImageOut
```python
class ImageOut(Filter):
    FILTER_TYPE = 'Output'
    
    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def create_writers(self)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
```

### Environment Variables
- `IMAGE_OUT_BGR`: Default BGR/RGB setting
- `IMAGE_OUT_QUALITY`: Default JPEG quality (1-100)
- `IMAGE_OUT_COMPRESSION`: Default PNG compression (0-9)
- `FILTER_SOURCES`: Input sources
- `FILTER_OUTPUTS`: Output destinations
