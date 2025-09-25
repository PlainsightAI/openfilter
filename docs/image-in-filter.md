# ImageIn Filter

The ImageIn filter is a input filter for OpenFilter that reads images from local filesystems and cloud storage, emitting them as OpenFilter Frames. It follows the same design patterns as VideoIn and provides comprehensive support for various image sources, filtering, looping, continuous monitoring, and FPS control.

## Overview

The ImageIn filter is designed to handle image ingestion scenarios where you need to:
- Process batches of images from local directories
- Continuously monitor directories for new images
- Read images from cloud storage (AWS S3, Google Cloud Storage)
- Apply pattern filtering to select specific images
- Loop through images for demonstrations or testing
- Handle multiple sources with different topics
- Control the display rate of images with FPS limiting
- Test dynamic file system scenarios

## Key Features

- **Multiple Source Types**: Local files (`file://`), AWS S3 (`s3://`), Google Cloud Storage (`gs://`)
- **Pattern Filtering**: Glob patterns (`*.jpg`) or regex patterns (`.*\.png$`)
- **Looping Support**: Infinite loops, finite loops, or no looping
- **Recursive Scanning**: Scan subdirectories for local files
- **Continuous Polling**: Background thread monitors for new images
- **Multiple Topics**: Different sources can emit to different topics
- **FPS Control**: Control image display rate with `maxfps` parameter
- **Robust Error Handling**: Graceful handling of missing files, network issues, etc.
- **Thread-Safe**: Background polling with proper synchronization
- **Dynamic File Handling**: Respond to file additions, removals, and changes

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn

# Simple local directory
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///path/to/images',
        outputs='tcp://*:5550',
    )),
])
```

### Advanced Configuration with FPS Control

```python
# Multiple sources with FPS limiting
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///path1;main, s3://bucket/images;cloud',
        outputs='tcp://*:5550',
        poll_interval=5.0,  # Check for new images every 5 seconds
        recursive=True,  # Scan subdirectories
        maxfps=1.0,  # Display 1 image per second
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
export IMAGE_IN_MAXFPS="1.0"  # Control display rate
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

### FPS Control
- `!maxfps=2.0` - Display 2 images per second
- `!maxfps=0.5` - Display 1 image every 2 seconds

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
- `maxfps`: Global FPS limiting (images per second)

### Per-Source Options
These can be set per source using the `!` syntax:

- `loop`: Loop behavior for this source
- `pattern`: Pattern filter for this source
- `recursive`: Recursive scanning for this source
- `maxfps`: FPS limiting for this source
- `region`: AWS region for S3 sources

## FPS Control

The ImageIn filter supports FPS (Frames Per Second) control to limit the rate at which images are displayed. This is useful for:

- **Demo scenarios**: Control display rate for presentations
- **Performance optimization**: Prevent overwhelming downstream filters
- **User experience**: Provide consistent viewing pace
- **Resource management**: Control memory and CPU usage

### FPS Configuration

```python
# Global FPS control
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///images',
        outputs='tcp://*:5550',
        maxfps=1.0,  # 1 image per second
    )),
])

# Per-source FPS control
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///images!maxfps=2.0, s3://bucket/images!maxfps=0.5',
        outputs='tcp://*:5550',
    )),
])
```

### FPS Behavior

- **Default**: No FPS limiting (images processed as fast as possible)
- **Global setting**: Applies to all sources unless overridden
- **Per-source setting**: Overrides global setting for specific source
- **Environment variable**: `IMAGE_IN_MAXFPS` sets default value
- **Timing precision**: Uses nanosecond precision for accurate timing

### FPS Implementation

The FPS control uses the same timing mechanism as VideoIn:

```python
def _wait_for_fps(self, topic):
    """Wait if necessary to maintain FPS limit."""
    if topic in self.ns_per_maxfps:
        now = time_ns()
        if now - self.tmaxfps[topic] < self.ns_per_maxfps[topic]:
            sleep_time = (self.ns_per_maxfps[topic] - (now - self.tmaxfps[topic])) / 1e9
            if sleep_time > 0:
                sleep(sleep_time)
        self.tmaxfps[topic] = time_ns()
```

## Queue Behavior and Dynamic Image Handling

The ImageIn filter uses a sophisticated queue system to manage image processing with full support for dynamic image addition. Understanding how the filter handles existing queued images when new images appear is crucial for real-world usage.

### Queue Structure

```python
self.queues = {}      # topic → list[path]
self.processed = {}   # topic → set[path]
self.loop_counts = {} # topic → int (remaining loops)
self.ns_per_maxfps = {}  # topic → nanoseconds per frame
self.tmaxfps = {}     # topic → last frame timestamp
```

Each topic has its own queue, tracking system, and FPS control.

### Dynamic Image Addition Behavior

#### How It Works When New Images Appear

**Yes, the ImageIn filter fully supports dynamic image addition with existing queued images.** Here's what happens:

1. **Existing Queue Preservation**: When new images are detected, they are appended to the end of the existing queue without disrupting current processing
2. **FIFO Processing**: Images are processed First-In-First-Out, so existing images continue processing in order
3. **Duplicate Prevention**: Only truly new images (not in the `processed` set) are added to avoid reprocessing
4. **Seamless Integration**: No interruption to the current processing flow - new images just join the queue

#### Background Polling Mechanism

The filter uses a background polling thread that continuously monitors sources:

```python
def _poll_loop(self):
    """Background thread that polls for new images."""
    poll_interval = self.config.poll_interval or IMAGE_IN_POLL_INTERVAL
    
    while not self.stop_event.is_set():
        try:
            for source in self.config.sources:
                topic = source.topic or 'main'
                new_images = self._list_images(source)
                # Add only new images that haven't been processed
                for img_path in new_images:
                    if img_path not in self.processed[topic]:
                        self.queues[topic].append(img_path)  # Append to end of queue
```

**Key behaviors:**
- **Continuous Monitoring**: Runs every `poll_interval` seconds (default: 5.0 seconds)
- **Smart Detection**: Only adds images that haven't been processed before
- **Queue Preservation**: New images are appended to the end, preserving processing order
- **Non-Disruptive**: Current image processing continues uninterrupted

#### Real-World Scenarios

**Scenario A: Processing Batch with New Arrivals**
```
Initial Queue: [img1.jpg, img2.jpg, img3.jpg]
Currently Processing: img1.jpg
New Images Added: [img4.jpg, img5.jpg]
Resulting Queue: [img2.jpg, img3.jpg, img4.jpg, img5.jpg]
Processing Order: img1 → img2 → img3 → img4 → img5
```

**Scenario B: Empty Queue with New Images**
```
Initial Queue: [] (empty, idle)
New Images Added: [img1.jpg, img2.jpg]
Resulting Queue: [img1.jpg, img2.jpg]
Processing: Resumes automatically
```

**Scenario C: Mixed Sources with Different Topics**
```python
# Configuration
sources='file:///local/images;main, s3://bucket/images;cloud'

# Behavior
# - Each topic has independent queue
# - New images in local folder → main queue
# - New images in S3 bucket → cloud queue
# - Processing continues for both topics independently
```

#### Configuration for Dynamic Monitoring

```python
# Optimal settings for dynamic image monitoring
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///watch/folder',
        outputs='tcp://*:5550',
        poll_interval=1.0,    # Check every 1 second for faster response
        maxfps=2.0,          # Process 2 images per second
        loop=False,          # Don't loop (for one-time processing)
    )),
])
```

#### Timing and Performance

- **Detection Latency**: New images detected within `poll_interval` seconds
- **Processing Continuity**: No gaps or delays in processing existing images
- **Memory Efficiency**: Only file paths stored in queue, not image data
- **Thread Safety**: Background polling with proper synchronization

#### Queue State During Dynamic Operations

The ImageIn filter maintains consistent behavior across all dynamic scenarios:

**During Active Processing:**
```python
# Example queue state during dynamic addition
Current State:
- Queue: [img2.jpg, img3.jpg]         # Remaining images to process
- Processing: img1.jpg                # Currently being processed
- Processed: {img0.jpg}              # Already completed

New Images Detected: [img4.jpg, img5.jpg]

Updated State:
- Queue: [img2.jpg, img3.jpg, img4.jpg, img5.jpg]  # New images appended
- Processing: img1.jpg                              # Continues unchanged
- Processed: {img0.jpg}                            # Unchanged
```

**Key Guarantees:**
1. **No Lost Images**: All detected images are eventually processed
2. **Ordered Processing**: FIFO order is maintained for predictable behavior
3. **No Reprocessing**: `processed` set prevents duplicate processing
4. **Continuous Operation**: No interruptions during dynamic changes

**Memory Management:**
- Queue grows dynamically as new images are found
- `processed` set tracks completed images (prevents reprocessing)
- Memory usage scales with number of unique images discovered
- Looping clears `processed` set to allow reprocessing

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

## Test Scenarios and Example Demonstrations

The ImageIn filter includes comprehensive test coverage and real example scenarios that demonstrate dynamic image handling:

### Example Scenario 1: Empty Directory Start
**File**: `examples/image_in/scenario1_empty_start.py`

**Demonstrates**: Pipeline starting with an empty folder and automatically picking up images as they appear.

**What it shows:**
- Pipeline starts with completely empty directory
- Remains idle (but alive) waiting for images
- Background thread adds images at timed intervals (5s, 15s, 25s, etc.)
- Filter automatically detects and processes new images
- Shows seamless integration of new images into processing queue

**Key Configuration:**
```python
(ImageIn, dict(
    sources=f'file://{test_dir}!loop!maxfps=0.5',  # 1 image every 2 seconds
    loop=True,         # Infinite loop through images
    poll_interval=1.0, # Check for new images every 1 second
))
```

**Real-world use case**: Monitoring upload directories, batch processing folders, surveillance image feeds.

### Example Scenario 2: Excluded Images with Dynamic Changes
**File**: `examples/image_in/scenario2_excluded_images.py`

**Demonstrates**: Advanced dynamic behavior with pattern filtering and image removal/re-addition.

**What it shows:**
- Directory pre-populated with excluded images (.bmp, .png, .tiff)
- Pipeline ignores excluded images (pattern=`*.jpg`)
- Matching images (.jpg) added, removed, and re-added dynamically
- Shows add/remove timeline: add → remove → re-add → final changes
- Demonstrates pattern filtering with dynamic file changes

**Timeline Example:**
```
8s:  Add image 1 (matches pattern)
12s: Add image 2 (matches pattern) 
16s: Add image 3 (matches pattern)
25s: Remove image 1
28s: Remove image 2
31s: Remove image 3
40s: Re-add image 1
44s: Re-add image 2
48s: Re-add image 3
```

**Key Configuration:**
```python
(ImageIn, dict(
    sources=f'file://{test_dir}!loop!pattern=*.jpg!maxfps=0.5',
    loop=True,         # Infinite loop
    poll_interval=1.0, # Fast detection of changes
))
```

**Real-world use case**: Mixed file type environments, selective processing, content management systems.

### Test Coverage for Dynamic Behavior

**Unit Tests:**
- `test_empty_directory_scenario()`: Empty start behavior
- `test_excluded_images_scenario()`: Pattern filtering with dynamic changes
- `test_dynamic_file_changes()`: File addition/removal handling
- `test_basic_read()`: Core functionality
- `test_pattern_filtering()`: Pattern matching behavior

### Additional Test Coverage

- **Basic Functionality**: `test_basic_read()`, `test_pattern_filtering()`
- **Looping Behavior**: `test_loop()`, `test_recursive_scanning()`
- **Configuration**: `test_normalize_config()`, `test_config_params()`
- **FPS Control**: `test_maxfps_config()`
- **Multiple Sources**: `test_multiple_sources()`
- **Error Handling**: `test_invalid_source()`, `test_file_scheme_parsing()`
- **Dynamic Behavior**: `test_dynamic_file_changes()`

## Usage Examples

### Example 1: Basic Image Processing
```python
Filter.run_multi([
    # ... other filters above
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

### Example 2: Continuous Monitoring with FPS Control
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///path/to/images',
        outputs='tcp://*:5550',
        poll_interval=2.0,  # Check every 2 seconds
        maxfps=1.0,  # Display 1 image per second
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Processes existing images at controlled rate, then monitors for new ones.

### Example 3: Infinite Loop for Demo with FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///path/to/images!loop!maxfps=0.5',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Continuously loops through images at 0.5 FPS for demonstrations.

### Example 4: Pattern Filtering with FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///path/to/images!pattern=*.jpg!maxfps=2.0',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Only processes JPEG files at 2 FPS.

### Example 5: Multiple Sources with Different FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///local/images!maxfps=1.0;main, s3://bucket/images!maxfps=0.5;cloud',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Processes local images at 1 FPS, cloud images at 0.5 FPS.

### Example 6: S3 with Options and FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='s3://my-bucket/images!pattern=*.png!region=us-west-2!maxfps=1.0',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Processes PNG files from S3 bucket at 1 FPS.

### Example 7: GCS with Recursive Scanning and FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='gs://my-bucket/images!recursive!pattern=*.jpg!maxfps=0.5',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

**Behavior:** Recursively scans GCS bucket for JPEG files at 0.5 FPS.

### Example 8: Dynamic Image Processing (Real-World Scenario)
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///upload/incoming!pattern=*.jpg!maxfps=1.0',
        outputs='tcp://*:5550',
        poll_interval=2.0,    # Check every 2 seconds for new uploads
        loop=False,           # Process each image only once
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms='resize 1024x768, quality 85',  # Process uploaded images
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
    )),
])
```

**Real-World Scenario:** This configuration handles a common use case where:
1. **Initial State**: Pipeline starts with some images already in `/upload/incoming/`
2. **Processing**: Begins processing existing images in queue order
3. **Dynamic Addition**: New images uploaded by users are automatically detected
4. **Queue Behavior**: New images join the end of the queue without disrupting current processing
5. **Continuous Operation**: Pipeline runs indefinitely, processing both existing and new images

**What Happens:**
- Existing images: `[photo1.jpg, photo2.jpg, photo3.jpg]` start processing immediately
- New uploads: `[photo4.jpg, photo5.jpg]` are detected and queued
- Processing order: `photo1 → photo2 → photo3 → photo4 → photo5`
- No images are lost or reprocessed

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

## Google Cloud Authg for Docker and Container Authentication

When running the ImageIn filter in Docker containers or other containerized environments, you need to handle cloud storage authentication differently than in local development. Here are the best practices for different scenarios:

### Authentication Methods

#### 1. Service Account Key (Recommended for Production)

**How it works:**
- Create a service account in Google Cloud Console with appropriate permissions
- Download the JSON key file
- Mount it as a volume in your Docker container
- Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable

**Steps:**
1. Go to Google Cloud Console → IAM & Admin → Service Accounts
2. Create a new service account with Storage Object Viewer permissions
3. Create and download a JSON key file
4. Mount the key file in your Docker container
5. Set the environment variable to point to the mounted file

**Docker Example:**
```bash
docker run -v /path/to/service-account-key.json:/app/credentials/key.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/key.json \
  your-openfilter-image
```

**Security considerations:**
- Never commit the key file to version control
- Use Docker secrets or Kubernetes secrets in production
- Rotate keys regularly
- Use least-privilege principle for service account permissions

#### 2. Workload Identity (Kubernetes/GKE)

**How it works:**
- Uses Kubernetes service accounts with Google Cloud IAM
- No key files needed
- Automatic credential rotation
- Most secure for Kubernetes environments

#### 3. Application Default Credentials (Development)

**How it works:**
- Mount your local gcloud credentials into the container
- Uses the same credentials as your development environment
- Good for development/testing scenarios

**Steps:**
1. Run `gcloud auth application-default login` on your host machine
2. Mount the credentials directory into the container
3. Set the environment variable to point to the mounted credentials

**Docker Example:**
```bash
docker run -v ~/.config/gcloud:/root/.config/gcloud:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud/application_default_credentials.json \
  your-openfilter-image
```

#### 4. Environment Variables (Alternative)

**How it works:**
- Pass credentials directly as environment variables
- Less secure, not recommended for production
- Good for quick testing or CI/CD pipelines

**Steps:**
1. Set `GOOGLE_APPLICATION_CREDENTIALS_JSON` with the entire key content
2. Modify your application to read from this environment variable
3. Write the content to a temporary file at runtime

**Docker Example:**
```bash
docker run -e GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type": "service_account", ...}' \
  your-openfilter-image
```

### Security Best Practices

#### Never Do:
- ❌ Commit service account keys to version control
- ❌ Use root user in containers
- ❌ Store credentials in Docker images
- ❌ Use overly broad permissions
- ❌ Use the same credentials across environments

#### Always Do:
- ✅ Use least-privilege service accounts
- ✅ Rotate credentials regularly
- ✅ Use secrets management (Docker secrets, Kubernetes secrets)
- ✅ Monitor access and audit logs
- ✅ Use workload identity when possible
- ✅ Use separate service accounts for different environments

### Error Handling for Authentication Failures

The ImageIn filter should handle authentication failures gracefully:

#### Common Error Messages:
```
Failed to list GCS images from gs://bucket/path: Your default credentials were not found.
To set up Application Default Credentials, see https://cloud.google.com/docs/authentication/external/set-up-adc
```

#### What the Filter Does:
1. **Logs clear error messages** about what's missing
2. **Provides helpful instructions** for setting up credentials
3. **Gracefully handles failures** without crashing the entire pipeline
4. **Continues processing other sources** if available
5. **Retries on next polling cycle** for transient failures

#### User Actions Required:
1. **For Service Account Key**: Ensure the key file is mounted and accessible
2. **For Workload Identity**: Verify service account annotations and IAM bindings
3. **For Application Default Credentials**: Check that credentials are properly mounted
4. **For Environment Variables**: Verify the JSON content is correct and complete

### Docker Compose Example

```yaml
version: '3.8'
services:
  openfilter-gcs:
    build: .
    volumes:
      # Mount service account key from host
      - ./service-account-key.json:/app/credentials/service-account-key.json:ro
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account-key.json
      - FILTER_SOURCES=gs://your-bucket/images!loop!maxfps=1.0
    ports:
      - "8000:8000"
```

### Production Recommendations

1. **Use Workload Identity** if running on GKE
2. **Use Service Account Keys** with proper secrets management
3. **Implement proper error handling** in your filter code
4. **Monitor authentication failures** and alert on them
5. **Use separate service accounts** for different environments (dev/staging/prod)
6. **Regularly rotate credentials** and monitor access logs
7. **Use least-privilege permissions** for service accounts
8. **Test authentication in CI/CD** before deploying to production

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

### FPS Control Errors
- Logs timing errors
- Continues processing without FPS limiting
- Graceful degradation

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

### FPS Control Impact
- Minimal CPU overhead for timing
- Nanosecond precision for accurate control
- Per-topic FPS tracking
- Graceful handling of timing errors

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
4. Adjust FPS settings if too aggressive

#### Memory Issues
1. Reduce number of sources
2. Use more specific patterns
3. Increase `poll_interval`
4. Lower FPS settings

#### FPS Control Issues
1. Check `maxfps` values are reasonable (> 0)
2. Verify timing precision on your system
3. Monitor for timing-related errors in logs

### Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed information about:
- Image discovery
- Queue operations
- Polling activity
- FPS timing
- Error conditions

## Advanced Usage

### Custom Image Processing Pipeline with FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///images!loop!maxfps=1.0',
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

### Multi-Source with Different Topics and FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///local!maxfps=1.0;main, s3://bucket/cloud!maxfps=0.5;cloud',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
    )),
])
```

### Batch Processing with Exit and FPS
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///batch!maxfps=2.0',
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
    maxfps: float | None = None  # New FPS control
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
    def _wait_for_fps(self, topic)  # New FPS method
```

### Environment Variables
- `IMAGE_IN_POLL_INTERVAL`: Default polling interval
- `IMAGE_IN_LOOP`: Default loop behavior
- `IMAGE_IN_RECURSIVE`: Default recursive scanning
- `IMAGE_IN_MAXFPS`: Default FPS limiting (new)
- `FILTER_SOURCES`: Image sources
- `FILTER_PATTERN`: Global pattern filter
- `FILTER_LOOP`: Global loop behavior
- `FILTER_RECURSIVE`: Global recursive scanning
- `FILTER_MAXFPS`: Global FPS limiting (new)