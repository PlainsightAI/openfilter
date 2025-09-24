# Util Filter

The Util filter is a versatile utility filter for OpenFilter that provides various utility operations on incoming frames. It can perform logging, introduce processing delays, apply image transformations, and handle miscellaneous tasks within the filter pipeline. The filter supports both data processing and image manipulation operations.

## Overview

The Util filter is designed to handle utility operations where you need to:
- Log frame data for debugging and monitoring
- Introduce processing delays for performance tuning
- Apply image transformations (flip, rotate, resize, draw boxes)
- Handle miscellaneous processing tasks
- Control frame rate and processing timing
- Debug and monitor pipeline performance
- Apply transforms to specific topics or all topics

## Key Features

- **Data Logging**: Comprehensive frame data logging with configurable detail levels
- **Processing Delays**: Sleep and frame rate control for performance tuning
- **Image Transformations**: Flip, rotate, resize, and draw operations on images
- **Topic Filtering**: Apply operations to specific topics or all topics
- **Debug Support**: Extensive debugging and monitoring capabilities
- **Performance Control**: Frame rate limiting and processing delays
- **Flexible Configuration**: Multiple operation modes and options

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.util import Util

# Simple logging utility
Filter.run_multi([
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,
    )),
])
```

### Advanced Configuration with Multiple Operations

```python
# Util filter with logging, delays, and image transforms
Filter.run_multi([
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,
        sleep=0.1,  # 100ms delay
        maxfps=30,  # Limit to 30 FPS
        flip=True,  # Flip images horizontally
        rotate=90,  # Rotate images 90 degrees
        resize='800x600',  # Resize images
        draw_boxes=True,  # Draw bounding boxes
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="tcp://localhost:5550"
export FILTER_OUTPUTS="tcp://*:5552"
export FILTER_LOG="true"
export FILTER_SLEEP="0.1"
export FILTER_MAXFPS="30"
export FILTER_FLIP="true"
export FILTER_ROTATE="90"
export FILTER_RESIZE="800x600"
export FILTER_DRAW_BOXES="true"
```

## Operation Types

### 1. Data Logging (`log`)

The logging operation provides comprehensive frame data logging:

#### Logging Configuration
```python
log=True  # Enable logging
log=False  # Disable logging (default)
```

#### Log Output Format
```
[timestamp] [topic] [frame_id] [data_summary]
```

#### Log Examples
```
2024-01-15 10:30:00.123 main 12345 {"detections": 3, "confidence": 0.95}
2024-01-15 10:30:00.124 camera1 12346 {"temperature": 25.5, "humidity": 60}
```

#### Logging Use Cases
- **Debugging**: Monitor frame data flow
- **Monitoring**: Track processing performance
- **Analysis**: Analyze data patterns
- **Troubleshooting**: Identify processing issues

### 2. Processing Delays (`sleep`)

The sleep operation introduces delays between frame processing:

#### Sleep Configuration
```python
sleep=0.1  # 100ms delay
sleep=1.0  # 1 second delay
sleep=None  # No delay (default)
```

#### Sleep Use Cases
- **Performance Tuning**: Control processing rate
- **Synchronization**: Align with external systems
- **Load Balancing**: Distribute processing load
- **Testing**: Simulate processing delays

### 3. Frame Rate Control (`maxfps`)

The maxfps operation limits the maximum frame rate:

#### FPS Configuration
```python
maxfps=30  # Limit to 30 FPS
maxfps=60  # Limit to 60 FPS
maxfps=None  # No limit (default)
```

#### FPS Control Use Cases
- **Performance Optimization**: Reduce CPU usage
- **Bandwidth Control**: Limit data transmission
- **Display Synchronization**: Match display refresh rates
- **Resource Management**: Control resource consumption

### 4. Image Transformations

The Util filter supports various image transformations:

#### Flip Operation (`flip`)
```python
flip=True   # Flip horizontally
flip=False  # No flip (default)
```

#### Rotate Operation (`rotate`)
```python
rotate=90   # Rotate 90 degrees clockwise
rotate=180  # Rotate 180 degrees
rotate=270  # Rotate 270 degrees (90 counter-clockwise)
rotate=None # No rotation (default)
```

#### Resize Operation (`resize`)
```python
resize='800x600'    # Resize to 800x600
resize='1920x1080'  # Resize to 1920x1080
resize=None         # No resize (default)
```

#### Draw Boxes Operation (`draw_boxes`)
```python
draw_boxes=True   # Draw bounding boxes
draw_boxes=False  # No boxes (default)
```

## Topic Filtering

The Util filter supports topic-specific operations:

### Topic Configuration
```python
# Apply to specific topics
topics=['main', 'camera1']  # Only process these topics

# Apply to all topics (default)
topics=None  # Process all topics
```

### Topic-Specific Examples
```python
# Log only main topic
log=True
topics=['main']

# Flip only camera images
flip=True
topics=['camera1', 'camera2']

# Resize only detection results
resize='800x600'
topics=['detections']
```

## Usage Examples

### Example 1: Basic Logging and Monitoring
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='file://input.mp4',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,  # Log all frame data
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
])
```

**Behavior:** Logs all incoming video frames before object detection processing.

### Example 2: Performance Tuning with Delays
```python
Filter.run_multi([
    (CameraInput, dict(
        sources='rtsp://camera.url',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        sleep=0.1,  # 100ms delay
        maxfps=15,  # Limit to 15 FPS
    )),
    (ImageProcessor, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
])
```

**Behavior:** Introduces delays and limits frame rate for performance optimization.

### Example 3: Image Transformations
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///images/',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        flip=True,      # Flip images horizontally
        rotate=90,      # Rotate 90 degrees
        resize='800x600',  # Resize to 800x600
    )),
    (ImageOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///processed/{filename}',
    )),
])
```

**Behavior:** Applies multiple image transformations before saving processed images.

### Example 4: Detection Visualization
```python
Filter.run_multi([
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Util, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        draw_boxes=True,  # Draw bounding boxes
        topics=['main'],  # Only on main topic
    )),
    (ImageOut, dict(
        sources='tcp://localhost:5554',
        outputs='file:///detected/{filename}',
    )),
])
```

**Behavior:** Draws bounding boxes on detection results before saving images.

### Example 5: Multi-Topic Processing
```python
Filter.run_multi([
    (MultiSourceInput, dict(
        sources=['camera1', 'camera2', 'camera3'],
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,
        topics=['camera1', 'camera2'],  # Log only specific cameras
    )),
    (Util, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        resize='640x480',
        topics=['camera3'],  # Resize only camera3
    )),
])
```

**Behavior:** Different operations on different camera topics.

### Example 6: Debug and Performance Monitoring
```python
Filter.run_multi([
    (ComplexProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Util, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        log=True,        # Log all data
        sleep=0.05,      # Small delay for monitoring
        maxfps=10,       # Limit rate for debugging
    )),
    (Recorder, dict(
        sources='tcp://localhost:5554',
        outputs='file:///debug/log.jsonl',
        rules=['+'],
    )),
])
```

**Behavior:** Comprehensive debugging with logging, delays, and rate limiting.

## Image Transformation Details

### Flip Operation
The flip operation performs horizontal image flipping:

```python
# Before flip
image = [1, 2, 3, 4, 5, 6, 7, 8]

# After flip
image = [8, 7, 6, 5, 4, 3, 2, 1]
```

**Use Cases:**
- **Mirror Effects**: Create mirror images
- **Camera Correction**: Fix camera orientation
- **Data Augmentation**: Increase dataset variety
- **Display Adjustment**: Match display requirements

### Rotate Operation
The rotate operation rotates images by specified degrees:

```python
# 90-degree rotation
rotate=90   # Clockwise rotation
rotate=270  # Equivalent to -90 degrees (counter-clockwise)
```

**Rotation Matrix:**
- **90°**: (x, y) → (y, -x)
- **180°**: (x, y) → (-x, -y)
- **270°**: (x, y) → (-y, x)

**Use Cases:**
- **Orientation Correction**: Fix image orientation
- **Display Rotation**: Match display orientation
- **Data Augmentation**: Rotate training data
- **Camera Mounting**: Adjust for camera angle

### Resize Operation
The resize operation scales images to specified dimensions:

```python
resize='800x600'    # Width x Height
resize='1920x1080'  # HD resolution
resize='640x480'    # VGA resolution
```

**Resize Methods:**
- **Bilinear Interpolation**: Smooth scaling
- **Aspect Ratio**: Maintains proportions
- **Quality**: Preserves image quality

**Use Cases:**
- **Performance Optimization**: Reduce processing load
- **Standardization**: Uniform image sizes
- **Display Requirements**: Match display resolution
- **Storage Optimization**: Reduce file sizes

### Draw Boxes Operation
The draw_boxes operation draws bounding boxes on images:

```python
draw_boxes=True   # Enable box drawing
draw_boxes=False  # Disable box drawing
```

**Box Drawing Features:**
- **Detection Boxes**: Draws detection bounding boxes
- **Color Coding**: Different colors for different classes
- **Labels**: Optional class labels
- **Confidence**: Optional confidence scores

**Use Cases:**
- **Visualization**: Visualize detection results
- **Debugging**: Verify detection accuracy
- **Presentation**: Show results to users
- **Analysis**: Visual analysis of detections

## Performance Considerations

### Logging Performance
- **Data Volume**: Large data structures impact performance
- **I/O Operations**: File logging can be slow
- **Memory Usage**: Logging consumes memory
- **Processing Time**: Logging adds processing overhead

### Delay Performance
- **Sleep Overhead**: Sleep operations add latency
- **Frame Rate**: Delays reduce effective frame rate
- **Synchronization**: Delays help with synchronization
- **Resource Usage**: Delays reduce CPU usage

### Image Transformation Performance
- **Memory Usage**: Transformations require additional memory
- **Processing Time**: Complex transformations are slower
- **Quality Loss**: Some transformations reduce quality
- **GPU Acceleration**: Consider GPU-accelerated operations

### Optimization Strategies
```python
# Optimize for performance
Filter.run_multi([
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=False,        # Disable logging for production
        sleep=None,       # No delays
        maxfps=30,        # Reasonable frame rate limit
        resize='640x480', # Smaller images for faster processing
    )),
])
```

## Error Handling

### Common Error Scenarios
- **Invalid Parameters**: Invalid configuration values
- **Image Processing Errors**: Failed image transformations
- **Memory Issues**: Insufficient memory for operations
- **File System Errors**: Logging file access issues

### Error Recovery
- **Graceful Degradation**: Continue processing on errors
- **Error Logging**: Log errors for debugging
- **Fallback Behavior**: Use default values on errors
- **Resource Cleanup**: Proper cleanup on failures

### Error Examples
```python
# Invalid resize format
resize='invalid'  # Error: Invalid resize format

# Invalid rotation angle
rotate=45  # Error: Only 90, 180, 270 degrees supported

# Invalid sleep value
sleep=-1  # Error: Sleep cannot be negative
```

## Debugging and Monitoring

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable util filter debugging
export DEBUG_UTIL=true
export LOG_LEVEL=DEBUG
```

### Debug Information
- **Operation Status**: Shows which operations are active
- **Performance Metrics**: Processing times and rates
- **Error Details**: Detailed error information
- **Resource Usage**: Memory and CPU usage

### Monitoring
- **Frame Rates**: Track actual vs. target frame rates
- **Processing Times**: Monitor operation durations
- **Error Rates**: Track operation failure rates
- **Resource Consumption**: Monitor memory and CPU usage

## Troubleshooting

### Common Issues

#### Performance Problems
1. Check operation complexity
2. Monitor resource usage
3. Optimize configuration
4. Consider hardware limitations

#### Image Quality Issues
1. Verify transformation parameters
2. Check image formats
3. Monitor quality loss
4. Adjust processing settings

#### Logging Issues
1. Check file permissions
2. Monitor disk space
3. Verify log format
4. Check I/O performance

#### Synchronization Issues
1. Adjust sleep values
2. Check frame rate limits
3. Monitor timing accuracy
4. Verify system clock

### Debug Configuration
```python
# Enable comprehensive debugging
Filter.run_multi([
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,        # Enable logging
        sleep=0.1,       # Add delay for monitoring
        maxfps=10,       # Limit rate for debugging
    )),
])
```

## Advanced Usage

### Custom Transformations
```python
# Combine multiple transformations
Filter.run_multi([
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        flip=True,
        rotate=90,
        resize='800x600',
    )),
])
```

### Conditional Processing
```python
# Different operations for different topics
Filter.run_multi([
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,
        topics=['main'],  # Log only main topic
    )),
    (Util, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        resize='640x480',
        topics=['camera1', 'camera2'],  # Resize only cameras
    )),
])
```

### Performance Profiling
```python
# Profile processing performance
Filter.run_multi([
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,        # Log for profiling
        sleep=0.01,      # Small delay for measurement
        maxfps=60,       # High frame rate for testing
    )),
])
```

## API Reference

### UtilConfig
```python
class UtilConfig(FilterConfig):
    sources: str | list[str] | list[tuple[str, dict[str, Any]]]
    outputs: str | list[str] | list[tuple[str, dict[str, Any]]]
    log: bool | None
    sleep: float | None
    maxfps: int | None
    flip: bool | None
    rotate: int | None
    resize: str | None
    draw_boxes: bool | None
    topics: list[str] | None
```

### Util
```python
class Util(Filter):
    FILTER_TYPE = 'Processing'
    
    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
    def log_frame(self, frame)
    def apply_delay(self, frame)
    def apply_fps_limit(self, frame)
    def apply_transforms(self, frame)
    def flip_image(self, image)
    def rotate_image(self, image, angle)
    def resize_image(self, image, size)
    def draw_boxes(self, image, detections)
```

### Environment Variables
- `DEBUG_UTIL`: Enable debug logging
- `FILTER_SOURCES`: Input sources
- `FILTER_OUTPUTS`: Output destinations
- `FILTER_LOG`: Enable frame logging
- `FILTER_SLEEP`: Processing delay in seconds
- `FILTER_MAXFPS`: Maximum frame rate
- `FILTER_FLIP`: Enable image flipping
- `FILTER_ROTATE`: Image rotation angle
- `FILTER_RESIZE`: Image resize dimensions
- `FILTER_DRAW_BOXES`: Enable box drawing
- `FILTER_TOPICS`: Target topics for operations
