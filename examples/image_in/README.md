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

### Configuration Options
- `sources`: Image source URIs
- `pattern`: Glob or regex pattern to filter files
- `poll_interval`: Seconds between directory scans (default: 5.0)
- `loop`: Loop behavior (False, True, or integer)
- `recursive`: Scan subdirectories (local only)

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