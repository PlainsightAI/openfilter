# ImageIn Filter Example

This example demonstrates the ImageIn filter, which reads images from local filesystem or cloud storage and emits them as OpenFilter Frames.

## Features

- **Local Images**: Read images from local directories (`file://`)
- **Cloud Storage**: Support for AWS S3 (`s3://`) and Google Cloud Storage (`gs://`)
- **Pattern Filtering**: Filter images by glob patterns or regex
- **Polling**: Continuously monitor for new images
- **Looping**: Option to loop through images infinitely or N times
- **Recursive**: Option to scan subdirectories recursively
- **Multiple Sources**: Support for multiple sources with different topics
- **Robust Error Handling**: Graceful handling of missing files, network issues, etc.
- **FPS Control**: Control display rate with maxfps parameter
- **Dynamic File Handling**: Respond to file additions, removals, and changes

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the demo:
   ```bash
   python main.py
   ```

3. Open your browser to `http://localhost:8000` to see the images

## Demo Scenarios

This directory includes two demonstration scenarios that showcase real-world use cases:

### 1. `scenario1_empty_start.py` - Empty Folder Start
**Simulates:** Pipeline starts with an empty folder and waits for images to appear.

**What it does:**
- Creates an empty `test_images/` directory
- Starts the pipeline with no images present
- Automatically adds images at 5, 15, 25, 35, and 45 seconds
- Demonstrates how the pipeline remains idle until images appear
- Shows automatic pickup of new images when they're added

**Usage:**
```bash
python scenario1_empty_start.py
```

**Expected behavior:**
1. Pipeline starts with empty folder
2. Webvis shows no images initially
3. Images appear automatically as they're added to the folder
4. Pipeline processes each new image as it appears

**Timeline:**
- **0s**: Pipeline starts with empty folder
- **5s**: First image appears in browser
- **15s**: Second image appears in browser
- **25s**: Third image appears in browser
- **35s**: Fourth image appears in browser
- **45s**: Fifth image appears in browser

### 2. `scenario2_excluded_images.py` - Dynamic Pattern Exclusion
**Simulates:** Pipeline starts with images in folder but they're excluded by pattern, then demonstrates dynamic add/remove behavior.

**What it does:**
- Creates `test_images/` with 3 excluded images (.bmp, .png, .tiff)
- Starts pipeline with pattern `*.jpg` only
- Pipeline remains idle (ignores excluded formats)
- Demonstrates dynamic file changes: add → remove → re-add
- Shows how pipeline handles real-world file system changes

**Usage:**
```bash
python scenario2_excluded_images.py
```

**Expected behavior:**
1. Pipeline starts with excluded images present
2. Webvis shows no images (pattern excludes them)
3. Matching .jpg images are added, then removed, then re-added
4. Pipeline responds dynamically to file system changes

**Dynamic Timeline:**
- **0-8s**: Pipeline idle (only excluded images present)
- **8s**: Add matching image 1 → appears in browser
- **12s**: Add matching image 2 → appears in browser
- **16s**: Add matching image 3 → appears in browser
- **25s**: Remove image 1 → disappears from browser
- **28s**: Remove image 2 → disappears from browser
- **31s**: Remove image 3 → disappears from browser
- **40s**: Re-add image 1 → reappears in browser
- **44s**: Re-add image 2 → reappears in browser
- **48s**: Re-add image 3 → reappears in browser
- **55s**: Remove image 1 again → disappears from browser
- **60s**: Add new image 4 → appears in browser

**Browser Display Timeline:**
```
Time    | Browser Display
--------|------------------
0-8s    | Empty (no matching images)
8-12s   | Image 1 visible
12-16s  | Images 1,2 visible  
16-25s  | Images 1,2,3 visible
25-28s  | Images 2,3 visible (1 removed)
28-31s  | Image 3 visible (2 removed)
31-40s  | Empty (all removed)
40-44s  | Image 1 visible (re-added)
44-48s  | Images 1,2 visible (re-added)
48-55s  | Images 1,2,3 visible (re-added)
55-60s  | Images 2,3 visible (1 removed again)
60s+    | Images 2,3,4 visible (new image added)
```

## Configuration

The ImageIn filter supports various configuration options:

### Basic Configuration

```python
# Simple local directory
(ImageIn, dict(
    sources='file:///path/to/images',
    outputs='tcp://*:5550',
))

# With pattern filtering
(ImageIn, dict(
    sources='file:///path/to/images!pattern=*.jpg',
    outputs='tcp://*:5550',
))

# With looping
(ImageIn, dict(
    sources='file:///path/to/images!loop',
    outputs='tcp://*:5550',
))

# With FPS control
(ImageIn, dict(
    sources='file:///path/to/images!maxfps=1.0',  # 1 image per second
    outputs='tcp://*:5550',
))
```

### Advanced Configuration

```python
# Multiple sources with different topics
(ImageIn, dict(
    sources='file:///path1;main, file:///path2;secondary',
    outputs='tcp://*:5550',
    poll_interval=5.0,  # Check for new images every 5 seconds
    recursive=True,  # Scan subdirectories
))

# S3 bucket with options
(ImageIn, dict(
    sources='s3://my-bucket/images!pattern=*.png!region=us-west-2',
    outputs='tcp://*:5550',
))

# GCS bucket with options
(ImageIn, dict(
    sources='gs://my-bucket/images!pattern=*.jpg',
    outputs='tcp://*:5550',
))
```

### Environment Variables

You can also configure via environment variables:

```bash
export FILTER_SOURCES="file:///path/to/images"
export FILTER_PATTERN="*.jpg"
export FILTER_POLL_INTERVAL="5.0"
export FILTER_LOOP="true"
export FILTER_RECURSIVE="false"
export IMAGE_IN_MAXFPS="1.0"
```

## Pipeline Examples

### Basic Image Display
```python
Filter.run_multi([
    (ImageIn, dict(sources='file://images', outputs='tcp://*:5550')),
    (Webvis, dict(sources='tcp://localhost:5550')),
])
```

### Image Processing Pipeline
```python
Filter.run_multi([
    (ImageIn, dict(sources='file://images!loop', outputs='tcp://*:5550')),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms='resize 640x480, flipx'
    )),
    (Webvis, dict(sources='tcp://localhost:5552')),
])
```

### Multiple Sources Pipeline
```python
Filter.run_multi([
    (ImageIn, dict(
        sources='file://images1;main, gs://my-bucket/images;cloud',
        outputs='tcp://*:5550'
    )),
    (Webvis, dict(sources='tcp://localhost:5550')),
])
```

## Source URI Formats

### Local Files
- `file:///absolute/path/to/images`
- `file://relative/path/to/images`

### AWS S3
- `s3://bucket-name/path/to/images`
- Requires AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, etc.)

### Google Cloud Storage
- `gs://bucket-name/path/to/images`
- Requires Google Cloud credentials (GOOGLE_APPLICATION_CREDENTIALS or gcloud auth)

## Options

### Source Options (using `!` syntax)
- `!loop` - Enable infinite looping
- `!loop=3` - Loop 3 times
- `!pattern=*.jpg` - Filter by pattern
- `!recursive` - Scan subdirectories (local only)
- `!region=us-west-2` - AWS region for S3 sources
- `!maxfps=1.0` - Control display FPS (images per second)

### Configuration Options
- `sources`: Image source URIs
- `pattern`: Glob or regex pattern to filter files
- `poll_interval`: Seconds between directory scans (default: 5.0)
- `loop`: Loop behavior (False, True, or integer)
- `recursive`: Scan subdirectories (local only)
- `maxfps`: Maximum frames per second for display

## Advanced Features

### Pattern Matching
The filter supports both glob patterns and regex patterns:

```python
# Glob patterns
sources='file:///images!pattern=*.jpg'
sources='file:///images!pattern=img_*.png'

# Regex patterns
sources='file:///images!pattern=.*\\.(jpg|png)$'
```

### Looping Behavior
Different looping options:

```python
# No looping (default)
sources='file:///images'

# Infinite loop
sources='file:///images!loop'

# Loop 3 times
sources='file:///images!loop=3'
```

### Recursive Scanning
Scan subdirectories for images:

```python
sources='file:///images!recursive'
```

### FPS Control
Control how fast images are displayed:

```python
# Display 1 image per second
sources='file:///images!maxfps=1.0'

# Display 1 image every 2 seconds
sources='file:///images!maxfps=0.5'

# Display 2 images per second
sources='file:///images!maxfps=2.0'
```

### S3 Integration
Read images from S3 buckets:

```python
sources='s3://my-bucket/images!pattern=*.jpg!region=us-west-2'
```

### GCS Integration
Read images from Google Cloud Storage:

```python
sources='gs://my-bucket/images!pattern=*.jpg'
```

## Key Features Demonstrated

### Polling Behavior
The filter polls for new images at the specified interval, demonstrating real-time monitoring capability.

### Pattern Filtering
Demonstrates how patterns can exclude certain file types while monitoring for matching ones.

### FPS Control
Controls display rate to prevent overwhelming downstream processing.

### Dynamic File Handling
Demonstrates the pipeline's ability to:
- **Add files**: Images appear immediately when added
- **Remove files**: Images disappear when removed
- **Re-add files**: Same images can be re-added and processed again
- **Real-time monitoring**: Responds to file system changes instantly

### Threading Architecture
Uses background threads for non-blocking operation:
- **Non-blocking**: Pipeline starts immediately
- **Clean shutdown**: Proper thread cleanup on Ctrl+C
- **Error handling**: Thread errors don't crash the pipeline

## Real-World Applications

### Scenario 1 Use Cases:
- **Security cameras**: Pipeline starts before cameras are active
- **Batch processing**: Waiting for new image batches to arrive
- **Monitoring systems**: Starting monitoring before data arrives
- **File upload systems**: Monitoring for new uploads

### Scenario 2 Use Cases:
- **File format filtering**: Only process specific image formats
- **Quality control**: Ignore temporary or low-quality images
- **Multi-format environments**: Handle mixed file types intelligently
- **Dynamic content**: Handle files that are added/removed frequently
- **Testing environments**: Simulate real-world file system changes

## Error Handling

The filter handles various error conditions gracefully:
- Missing directories/files
- Invalid image files
- Network issues (for cloud storage)
- Authentication failures
- Invalid patterns or options

Errors are logged but don't stop the filter from continuing to process other images.

## Performance Considerations

- **Polling**: The filter polls for new images at the specified interval
- **Memory**: Images are loaded on-demand to minimize memory usage
- **Threading**: Uses background threads for polling to avoid blocking
- **Caching**: Tracks processed files to avoid duplicates
- **FPS Control**: Prevents overwhelming downstream processing

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

## Running the Scripts

1. **Navigate to the directory:**
   ```bash
   cd examples/image_in
   ```

2. **Run the main demo:**
   ```bash
   python main.py
   ```

3. **Run scenario demos:**
   ```bash
   python scenario1_empty_start.py
   # or
   python scenario2_excluded_images.py
   ```

4. **Open browser:**
   Navigate to http://localhost:8000 to see the results

5. **Stop the pipeline:**
   Press Ctrl+C to stop the pipeline

## Environment Variables

You can customize behavior with environment variables:
```bash
# Control polling frequency
export IMAGE_IN_POLL_INTERVAL=2.0

# Control FPS
export IMAGE_IN_MAXFPS=1.0

# Run with custom settings
python scenario1_empty_start.py
```

## Troubleshooting

- **No images appear**: Check that the `test_images/` directory is created
- **Webvis not loading**: Ensure port 8000 is available
- **Pipeline errors**: Check that all dependencies are installed
- **Permission issues**: Ensure write permissions for creating test directories
- **Thread issues**: Ensure proper cleanup with Ctrl+C 