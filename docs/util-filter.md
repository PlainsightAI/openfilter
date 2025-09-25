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
    # ... other filters above
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
    # ... other filters above
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,
        sleep=0.1,  # 100ms delay
        maxfps=30,  # Limit to 30 FPS
        xforms=[
            'flipx;main',  # Flip main topic images horizontally
            'rotcw;main',  # Rotate main topic images 90 degrees clockwise
            'resize 800x600;main',  # Resize main topic images
            'box 0+0x0.2x0.2#f00;main',  # Draw red box on main topic
        ],
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
export FILTER_XFORMS="flipx;main,rotcw;main,resize 800x600;main"
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

### 4. Image Transformations (`xforms`)

The Util filter supports various image transformations through the `xforms` parameter. Each transform is specified as a string with the format `action[parameters];topics`:

#### Available Transform Actions

**Flip Operations:**
```python
xforms=['flipx;main']      # Flip around Y axis (horizontal flip)
xforms=['flipy;main']      # Flip around X axis (vertical flip)  
xforms=['flipboth;main']   # Flip both axes (same as 180° rotation)
```

**Rotation Operations:**
```python
xforms=['rotcw;main']      # Rotate 90° clockwise
xforms=['rotccw;main']     # Rotate 90° counter-clockwise
```

**Color Format Operations:**
```python
xforms=['swaprgb;main']    # Swap RGB channels (BGR ↔ RGB)
xforms=['fmtrgb;main']     # Convert to RGB format
xforms=['fmtbgr;main']     # Convert to BGR format
xforms=['fmtgray;main']    # Convert to grayscale
```

**Resize Operations:**
```python
xforms=['resize 800x600;main']           # Resize to exact dimensions (preserves aspect)
xforms=['resize 800+600;main']           # Resize to exact dimensions (ignores aspect)
xforms=['maxsize 800x600;main']          # Scale down if larger than max size
xforms=['minsize 800x600;main']          # Scale up if smaller than min size
xforms=['resize 800x600lin;main']        # With linear interpolation
xforms=['resize 800x600near;main']       # With nearest neighbor interpolation
xforms=['resize 800x600cub;main']        # With cubic interpolation
```

**Box Drawing:**
```python
xforms=['box 0+0x0.2x0.2#f00;main']      # Draw red box at (0,0) with size 0.2x0.2
xforms=['box 0.1+0.1x0.3x0.3#00ff00;main'] # Draw green box with specific position
```

#### Topic Specification

Transformations can be applied to specific topics or all topics:
```python
xforms=['flipx;main']                    # Apply only to 'main' topic
xforms=['flipx;main,camera1']            # Apply to 'main' and 'camera1' topics
xforms=['flipx']                         # Apply to all topics (no topic specified)
```

## Topic Filtering

The Util filter supports topic-specific operations through the `xforms` parameter:

### Topic Configuration in XForms
```python
# Apply to specific topics
xforms=['flipx;main,camera1']  # Apply flipx to main and camera1 topics

# Apply to all topics (no topic specified)
xforms=['flipx']  # Apply flipx to all topics
```

### Topic-Specific Examples
```python
# Log all topics (log applies to all)
log=True

# Flip only camera images
xforms=['flipx;camera1,camera2']

# Resize only detection results
xforms=['resize 800x600;detections']

# Different operations for different topics
xforms=[
    'flipx;camera1',           # Flip camera1
    'rotcw;camera2',           # Rotate camera2
    'resize 640x480;detections' # Resize detections
]
```

## Usage Examples

### Example 1: Basic Logging and Monitoring
```python
Filter.run_multi([
    # ... other filters above
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
    # ... other filters above
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
    # ... other filters above
    (ImageIn, dict(
        sources='file:///images/',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms=[
            'flipx',              # Flip all images horizontally
            'rotcw',              # Rotate all images 90 degrees clockwise
            'resize 800x600',     # Resize all images to 800x600
        ],
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
    # ... other filters above
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Util, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        xforms=['box 0+0x0.2x0.2#f00;main'],  # Draw red box on main topic
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
    # ... other filters above
    (MultiSourceInput, dict(
        sources=['camera1', 'camera2', 'camera3'],
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,  # Log all topics
        xforms=[
            'flipx;camera1',           # Flip camera1
            'rotcw;camera2',           # Rotate camera2
            'resize 640x480;camera3',  # Resize camera3
        ],
    )),
])
```

**Behavior:** Different operations on different camera topics.

### Example 6: Debug and Performance Monitoring
```python
Filter.run_multi([
    # ... other filters above
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

### XForms Syntax

The `xforms` parameter accepts a list of transform specifications with the format:
```
action[parameters];topic1,topic2,...
```

Where:
- `action`: The transform action (flipx, rotcw, resize, etc.)
- `parameters`: Optional parameters for the action
- `topic1,topic2`: Optional comma-separated list of topics (if omitted, applies to all topics)

### Flip Operations

**flipx** - Flip around Y axis (horizontal flip):
```python
xforms=['flipx;main']  # Flip main topic horizontally
```

**flipy** - Flip around X axis (vertical flip):
```python
xforms=['flipy;main']  # Flip main topic vertically
```

**flipboth** - Flip both axes (equivalent to 180° rotation):
```python
xforms=['flipboth;main']  # Flip main topic both ways
```

### Rotation Operations

**rotcw** - Rotate 90° clockwise:
```python
xforms=['rotcw;main']  # Rotate main topic clockwise
```

**rotccw** - Rotate 90° counter-clockwise:
```python
xforms=['rotccw;main']  # Rotate main topic counter-clockwise
```

### Color Format Operations

**swaprgb** - Swap RGB channels (BGR ↔ RGB):
```python
xforms=['swaprgb;main']  # Swap color channels for main topic
```

**fmtrgb**, **fmtbgr**, **fmtgray** - Convert to specific color formats:
```python
xforms=['fmtrgb;main']   # Convert to RGB format
xforms=['fmtbgr;main']   # Convert to BGR format  
xforms=['fmtgray;main']  # Convert to grayscale
```

### Resize Operations

**resize** - Resize to exact dimensions:
```python
xforms=['resize 800x600;main']     # Preserve aspect ratio
xforms=['resize 800+600;main']     # Ignore aspect ratio
xforms=['resize 800x600lin;main']  # With linear interpolation
```

**maxsize** - Scale down if larger than specified size:
```python
xforms=['maxsize 800x600;main']  # Scale down if larger than 800x600
```

**minsize** - Scale up if smaller than specified size:
```python
xforms=['minsize 800x600;main']  # Scale up if smaller than 800x600
```

### Box Drawing

**box** - Draw solid color box with relative coordinates:
```python
xforms=['box 0+0x0.2x0.2#f00;main']  # Red box at (0,0) with size 0.2x0.2
xforms=['box 0.1+0.1x0.3x0.3#00ff00;main']  # Green box at (0.1,0.1) with size 0.3x0.3
```

Box format: `x+yxwidthxheight[#color]`
- Coordinates and sizes are relative (0.0 to 1.0)
- Color is optional RGB hex (3 or 6 digits)
- If no color specified, uses black

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
    # ... other filters above
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=False,        # Disable logging for production
        sleep=None,       # No delays
        maxfps=30,        # Reasonable frame rate limit
        xforms=['resize 640x480'], # Smaller images for faster processing
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
# Invalid xforms format
xforms=['invalid_action;main']  # Error: Invalid xform action

# Invalid resize format
xforms=['resize invalid;main']  # Error: Invalid size format

# Invalid rotation (only 90° increments supported)
xforms=['rotate 45;main']  # Error: Use rotcw or rotccw for 90° rotations

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
    # ... other filters above
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
    # ... other filters above
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms=[
            'flipx',
            'rotcw',
            'resize 800x600',
        ],
    )),
])
```

### Conditional Processing
```python
# Different operations for different topics
Filter.run_multi([
    # ... other filters above
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,  # Log all topics
        xforms=[
            'resize 640x480;camera1,camera2',  # Resize only cameras
        ],
    )),
])
```

### Performance Profiling
```python
# Profile processing performance
Filter.run_multi([
    # ... other filters above
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
    log: bool | str | None
    sleep: float | None
    maxfps: float | None
    xforms: str | list[str | XForm] | None
```

### Util
```python
class Util(Filter):
    FILTER_TYPE = 'System'
    
    @classmethod
    def normalize_config(cls, config)
    def setup(self, config)
    def process(self, frames)
    def execute_xforms(self, topic_xform)
    def execute_xform_size(self, xform, frame)
    def execute_xform_box(self, xform, frame)
```

### Environment Variables
- `DEBUG_UTIL`: Enable debug logging
- `FILTER_SOURCES`: Input sources
- `FILTER_OUTPUTS`: Output destinations
- `FILTER_LOG`: Enable frame logging
- `FILTER_SLEEP`: Processing delay in seconds
- `FILTER_MAXFPS`: Maximum frame rate
- `FILTER_XFORMS`: Comma-separated list of transforms
