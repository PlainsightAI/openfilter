# ImageIn Filter

The ImageIn filter is a robust input filter for OpenFilter that reads images from local filesystems and cloud storage, emitting them as OpenFilter Frames. It follows the same design patterns as VideoIn and provides comprehensive support for various image sources, filtering, looping, and continuous monitoring.

## Overview

The ImageIn filter is designed to handle image ingestion scenarios where you need to:
- Process batches of images from local directories
- Continuously monitor directories for new images
- Read images from cloud storage (AWS S3, Google Cloud Storage)
- Apply pattern filtering to select specific images
- Loop through images for demonstrations or testing
- Handle multiple sources with different topics

## Key Features

- **Multiple Source Types**: Local files (`file://`), AWS S3 (`s3://`), Google Cloud Storage (`gs://`)
- **Pattern Filtering**: Glob patterns (`*.jpg`) or regex patterns (`.*\.png$`)
- **Looping Support**: Infinite loops, finite loops, or no looping
- **Recursive Scanning**: Scan subdirectories for local files
- **Continuous Polling**: Background thread monitors for new images
- **Multiple Topics**: Different sources can emit to different topics
- **Robust Error Handling**: Graceful handling of missing files, network issues, etc.
- **Thread-Safe**: Background polling with proper synchronization

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn

# Simple local directory
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///path/to/images',
        outputs='tcp://*:5550',
    )),
])
```

### Advanced Configuration

```python
# Multiple sources with different topics
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///path1;main, s3://bucket/images;cloud',
        outputs='tcp://*:5550',
        poll_interval=5.0,  # Check for new images every 5 seconds
        recursive=True,  # Scan subdirectories
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="file:///path/to/images"
export FILTER_PATTERN="*.jpg"
export FILTER_POLL_INTERVAL="5.0"
export FILTER_LOOP="true"
export FILTER_RECURSIVE="false"
```

## Source URI Formats

### Local Files
```
file:///absolute/path/to/images
file://relative/path/to/images
file:///path/to/single/image.jpg
```

### AWS S3
```
s3://bucket-name/path/to/images
s3://bucket-name/path/to/single/image.jpg
```

### Google Cloud Storage
```
gs://bucket-name/path/to/images
gs://bucket-name/path/to/single/image.jpg
```

## Source Options

You can append options to source URIs using the `!` syntax:

### Looping Options
- `!loop` - Enable infinite looping
- `!loop=3` - Loop 3 times
- `!no-loop` - Disable looping (default)

### Pattern Filtering
- `!pattern=*.jpg` - Only JPEG files
- `!pattern=img_*.png` - Files starting with "img_" and ending with ".png"
- `!pattern=.*\.(jpg|png)$` - JPEG or PNG files (regex)

### Recursive Scanning (Local Only)
- `!recursive` - Scan subdirectories
- `!no-recursive` - Don't scan subdirectories (default)

### AWS Region (S3 Only)
- `!region=us-west-2` - Specify AWS region

## Configuration Options

### Global Options
These apply to all sources unless overridden:

- `sources`: Image source URIs (required)
- `pattern`: Global pattern filter
- `poll_interval`: Seconds between directory scans (default: 5.0)
- `loop`: Global loop behavior
- `recursive`: Global recursive scanning

### Per-Source Options
These can be set per source using the `!` syntax:

- `loop`: Loop behavior for this source
- `pattern`: Pattern filter for this source
- `recursive`: Recursive scanning for this source
- `region`: AWS region for S3 sources

## Queue Behavior and Empty Queue Handling

The ImageIn filter uses a sophisticated queue system to manage image processing. Understanding what happens when queues are empty is crucial for proper usage.

### Queue Structure

```python
self.queues = {}      # topic → list[path]
self.processed = {}   # topic → set[path]
self.loop_counts = {} # topic → int (remaining loops)
```

Each topic has its own queue and tracking system.

### Empty Queue Scenarios

#### Scenario 1: No Looping, Empty Queue
```python
# Configuration
sources='file:///images'  # No loop specified

# Behavior
# - Queue becomes empty after processing all images
# - Returns None
# - Filter stays alive but idle
# - Polling thread continues checking for new images
```

**What happens:**
1. All images are processed from the queue
2. Queue becomes empty
3. `get_next_frame()` returns `None`
4. Filter remains alive, waiting for new images
5. Background polling continues monitoring the directory

#### Scenario 2: Infinite Loop, Empty Queue
```python
# Configuration
sources='file:///images!loop'

# Behavior
# - Queue becomes empty
# - Reloads all images from source
# - Continues processing in infinite loop
```

**What happens:**
1. All images are processed from the queue
2. Queue becomes empty
3. Filter detects infinite loop is enabled
4. Calls `_reload_images_for_topic(topic)`
5. Clears the `processed` set to allow reprocessing
6. Adds all images back to the queue
7. Continues processing in infinite loop

#### Scenario 3: Finite Loop, Empty Queue
```python
# Configuration
sources='file:///images!loop=3'

# Behavior
# - Queue becomes empty
# - Reloads images and decrements counter (3 → 2 → 1 → 0)
# - After 3 loops, stops and returns None
```

**What happens:**
1. All images are processed from the queue
2. Queue becomes empty
3. Filter detects finite loop is enabled
4. Checks `loop_counts[topic] > 0`
5. Reloads images and decrements counter
6. Continues until counter reaches 0
7. Then returns `None` and stops processing

#### Scenario 4: Multiple Sources, Some Empty
```python
# Configuration
sources='file:///images1;main, file:///images2;secondary'

# Behavior
# - If main queue is empty but secondary has images: processes secondary
# - If both empty: returns None
# - Each topic is handled independently
```

**What happens:**
1. Each topic has its own queue and loop configuration
2. If one topic's queue is empty, others continue processing
3. Only returns `None` when ALL topic queues are empty
4. Each topic can have different loop settings

### Polling Thread Behavior

Even when queues are empty, the background polling thread continues:

```python
def _poll_loop(self):
    while not self.stop_event.is_set():
        try:
            for source in self.config.sources:
                topic = source.topic or 'main'
                new_images = self._list_images(source)
                # Add only new images that haven't been processed
                for img_path in new_images:
                    if img_path not in self.processed[topic]:
                        self.queues[topic].append(img_path)
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
        
        self.stop_event.wait(poll_interval)
```

**Key points:**
- Polling continues regardless of queue state
- New images are automatically added to queues
- Only unprocessed images are added (prevents duplicates)
- Processing resumes when `get_next_frame()` is called again

## Usage Examples

### Example 1: Basic Image Processing
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///path/to/images',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Processes all images once, then stops.

### Example 2: Continuous Monitoring
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///path/to/images',
        outputs='tcp://*:5550',
        poll_interval=2.0,  # Check every 2 seconds
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Processes existing images, then monitors for new ones.

### Example 3: Infinite Loop for Demo
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///path/to/images!loop',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Continuously loops through images for demonstrations.

### Example 4: Pattern Filtering
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///path/to/images!pattern=*.jpg',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Only processes JPEG files.

### Example 5: Multiple Sources
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///local/images;main, s3://bucket/images;cloud',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Processes images from both local and cloud sources.

### Example 6: S3 with Options
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='s3://my-bucket/images!pattern=*.png!region=us-west-2',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Processes PNG files from S3 bucket in specific region.

### Example 7: GCS with Recursive Scanning
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='gs://my-bucket/images!recursive!pattern=*.jpg',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Recursively scans GCS bucket for JPEG files.

## Cloud Storage Setup

### AWS S3
```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-west-2"
```

### Google Cloud Storage
```bash
# Option 1: Service account key file
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"

# Option 2: gcloud auth (for local development)
gcloud auth application-default login
```

## Error Handling

The ImageIn filter handles various error conditions gracefully:

### Missing Files/Directories
- Logs warning but continues processing
- Skips missing paths without crashing

### Invalid Images
- Logs error for failed image loads
- Skips invalid images and continues
- Returns `None` for failed loads

### Network Issues (Cloud Storage)
- Logs connection errors
- Continues processing other sources
- Retries on next polling cycle

### Authentication Failures
- Logs authentication errors
- Continues with other sources
- Provides helpful error messages

### Invalid Patterns
- Logs pattern compilation errors
- Falls back to literal string matching
- Continues processing

## Performance Considerations

### Memory Usage
- Images are loaded on-demand
- Processed files are tracked to avoid duplicates
- Queues only store file paths, not image data

### Polling Frequency
- Default: 5 seconds between scans
- Configurable via `poll_interval`
- Lower values = faster response to new images
- Higher values = less system load

### Threading
- Background polling thread
- Non-blocking main processing
- Proper synchronization with `Event`

### Caching
- Tracks processed files to avoid duplicates
- Clears cache when looping is enabled
- Efficient for large directories

## Troubleshooting

### Common Issues

#### Images Not Appearing
1. Check file extensions are supported
2. Verify pattern filtering isn't too restrictive
3. Ensure paths are correct
4. Check file permissions

#### S3/GCS Connection Issues
1. Verify credentials are set correctly
2. Check network connectivity
3. Ensure bucket/region names are correct
4. Verify IAM permissions

#### High CPU Usage
1. Increase `poll_interval`
2. Use more specific patterns
3. Avoid recursive scanning on large directories

#### Memory Issues
1. Reduce number of sources
2. Use more specific patterns
3. Increase `poll_interval`

### Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed information about:
- Image discovery
- Queue operations
- Polling activity
- Error conditions

## Advanced Usage

### Custom Image Processing Pipeline
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///images!loop',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms='resize 640x480, flipx',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
    )),
])
```

### Multi-Source with Different Topics
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///local;main, s3://bucket/cloud;cloud',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

### Batch Processing with Exit
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file:///batch',
        outputs='tcp://*:5550',
        exit_after=300,  # Exit after 5 minutes
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

## API Reference

### ImageInConfig
```python
class ImageInConfig(FilterConfig):
    sources: str | list[str | Source]
    pattern: str | None = None
    poll_interval: float = 5.0
    loop: bool | int | None = False
    recursive: bool = False
```

### ImageIn
```python
class ImageIn(Filter):
    FILTER_TYPE = 'Input'
    
    @classmethod
    def normalize_config(cls, config)
    def setup(self, config)
    def process(self, frames)
    def shutdown(self)
```

### Environment Variables
- `IMAGE_IN_POLL_INTERVAL`: Default polling interval
- `IMAGE_IN_LOOP`: Default loop behavior
- `IMAGE_IN_RECURSIVE`: Default recursive scanning
- `FILTER_SOURCES`: Image sources
- `FILTER_PATTERN`: Global pattern filter
- `FILTER_LOOP`: Global loop behavior
- `FILTER_RECURSIVE`: Global recursive scanning

## Conclusion

The ImageIn filter provides a robust, flexible solution for image ingestion in OpenFilter pipelines. Its sophisticated queue management, comprehensive error handling, and support for multiple source types make it suitable for both simple batch processing and complex continuous monitoring scenarios.

The filter's design follows OpenFilter best practices and integrates seamlessly with other filters in the ecosystem, making it an essential component for image processing pipelines. 