# Recorder Filter

The Recorder filter is an output filter for OpenFilter that records frame data to files in JSON or CSV format. It provides flexible data filtering rules to include or exclude specific fields, supports both JSON and CSV output formats, and offers configurable data handling for different use cases.

## Overview

The Recorder filter is designed to handle data recording scenarios where you need to:
- Log frame data for analysis and debugging
- Export processed data in structured formats
- Filter sensitive or unnecessary data fields
- Record data in JSON or CSV format
- Append to existing files or create new ones
- Control data granularity and detail level
- Handle empty data scenarios gracefully

## Key Features

- **Flexible Data Filtering**: Include/exclude specific fields with rule-based syntax
- **Multiple Output Formats**: JSON (line-delimited) and CSV formats
- **Rule-Based Processing**: Complex filtering rules with path-based field selection
- **Empty Data Handling**: Configurable handling of empty or missing data
- **File Management**: Append mode or overwrite mode
- **CSV Headers**: Automatic CSV header generation and management
- **Debugging Support**: Optional debug logging for rule processing
- **Data Pruning**: Automatic removal of empty nested structures

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.recorder import Recorder

# Simple JSON recording
Filter.run_multi([
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///path/to/record.jsonl',
        rules=['+', '-/meta/ts'],  # Include everything except timestamps
    )),
])
```

### Advanced Configuration with CSV Output

```python
# CSV recording with specific field filtering
Filter.run_multi([
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///path/to/data.csv!append',
        rules=[
            '+main/data/detections',
            '+main/data/confidence',
            '+main/data/timestamp',
            '-/meta/fps',
            '-/meta/cpu',
        ],
        empty=1,  # Include fields even if empty
        flush=True,  # Flush after each write
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="tcp://localhost:5550"
export FILTER_OUTPUTS="file:///path/to/record.jsonl"
export FILTER_RULES="+, -/meta/ts, -/meta/fps"
export FILTER_EMPTY="1"
export FILTER_FLUSH="true"
export DEBUG_RECORDER="true"
```

## Data Filtering Rules

The Recorder filter uses a powerful rule-based system for filtering frame data:

### Rule Syntax
```
"+topic/path"  - Include specific field
"-topic/path"  - Exclude specific field
"+"            - Include everything
"-"            - Exclude everything
```

### Rule Components

#### Operators
- `+`: Include (additive rule)
- `-`: Exclude (subtractive rule)

#### Path Specification
- `topic`: Specific topic name (e.g., 'main', 'camera1')
- `topic/field`: Specific field in topic data
- `topic/nested/field`: Deep nested field access
- `/field`: Field in all topics
- Empty path: Apply to entire topic

### Rule Processing Order
Rules are processed in the order they appear, allowing for complex filtering logic:

```python
rules = [
    '+',                    # Start with everything
    '-/meta/ts',           # Remove timestamps from all topics
    '-/meta/fps',          # Remove FPS from all topics
    '+main/data/detections', # Include detections from main topic
    '-camera1/data/raw',   # Exclude raw data from camera1
]
```

## Rule Examples

### Basic Filtering
```python
# Include everything except timestamps
rules = ['+', '-/meta/ts']

# Include only detection data
rules = ['+main/data/detections']

# Include main topic but exclude camera metadata
rules = ['+main', '-main/meta']
```

### Advanced Filtering
```python
# Complex filtering for analysis
rules = [
    '+',                           # Start with everything
    '-/meta/ts',                  # Remove timestamps
    '-/meta/fps',                 # Remove FPS data
    '-/meta/cpu',                 # Remove CPU data
    '-/meta/mem',                 # Remove memory data
    '+main/data/detections',      # Keep detections
    '+main/data/confidence',      # Keep confidence scores
    '+camera1/data/temperature',  # Keep temperature from camera1
    '+camera2/data/humidity',     # Keep humidity from camera2
]
```

### Topic-Specific Filtering
```python
# Different rules for different topics
rules = [
    '+main/data/detections',      # Main topic: only detections
    '+camera1',                   # Camera1: everything
    '-camera1/meta',              # But exclude metadata
    '+camera2/data/sensors',      # Camera2: only sensor data
]
```

## Output Formats

### JSON Format (Default)
- **File Extension**: `.json`, `.jsonl`, or any non-CSV extension
- **Format**: Line-delimited JSON (one JSON object per line)
- **Structure**: Preserves nested data structure
- **Use Cases**: Logging, debugging, data analysis

#### JSON Output Example
```json
{"main": {"data": {"detections": [{"class": "person", "confidence": 0.95}]}, "meta": {"id": 123}}}
{"main": {"data": {"detections": [{"class": "car", "confidence": 0.87}]}, "meta": {"id": 124}}}
```

### CSV Format
- **File Extension**: `.csv`
- **Format**: Comma-separated values with headers
- **Structure**: Flattened data structure
- **Headers**: Automatically generated from first record
- **Use Cases**: Spreadsheet analysis, data import, reporting

#### CSV Output Example
```csv
main_data_detections_class,main_data_detections_confidence,main_meta_id
person,0.95,123
car,0.87,124
```

## Empty Data Handling

The `empty` parameter controls how empty data is handled:

### Empty Levels
- **0**: Only include if there is actual data (most restrictive)
- **1**: Include if there are fields, even if empty (default)
- **2**: Include everything, including completely empty structures

### Examples

#### Empty Level 0 (Most Restrictive)
```python
empty=0
# Only writes records that have actual data values
# Skips records with all empty/null fields
```

#### Empty Level 1 (Default)
```python
empty=1
# Writes records if they have fields, even if empty
# Good balance between completeness and efficiency
```

#### Empty Level 2 (Most Inclusive)
```python
empty=2
# Writes everything, including empty structures
# Useful for maintaining complete data lineage
```

## File Management

### Output Options
- **Overwrite Mode**: Default behavior, creates new file each time
- **Append Mode**: Use `!append` option to append to existing file

### Append Mode
```python
outputs='file:///path/to/data.csv!append'
```

**Benefits:**
- Preserves historical data
- Allows continuous logging
- Maintains CSV headers across restarts
- Useful for long-running processes

### File Creation
- **Directory Creation**: Automatically creates output directories
- **File Permissions**: Uses default system permissions
- **Error Handling**: Graceful handling of permission issues

## Usage Examples

### Example 1: Basic Data Logging
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='file://input.mp4',
        outputs='tcp://*:5550',
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Recorder, dict(
        sources='tcp://localhost:5552',
        outputs='file:///logs/detections.jsonl',
        rules=['+', '-/meta/ts'],  # Everything except timestamps
    )),
])
```

**Behavior:** Records all detection data except timestamps in JSON format.

### Example 2: CSV Analysis Export
```python
Filter.run_multi([
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///analysis/detection_data.csv!append',
        rules=[
            '+main/data/detections',
            '+main/data/confidence',
            '+main/data/timestamp',
        ],
        empty=0,  # Only records with actual data
        flush=True,
    )),
])
```

**Behavior:** Exports detection data to CSV for analysis, appending to existing file.

### Example 3: Sensor Data Logging
```python
Filter.run_multi([
    (SensorFilter, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Recorder, dict(
        sources='tcp://localhost:5552',
        outputs='file:///logs/sensors.jsonl',
        rules=[
            '+camera1/data/temperature',
            '+camera1/data/humidity',
            '+camera1/data/pressure',
            '+camera2/data/temperature',
            '+camera2/data/humidity',
            '-/meta',  # Exclude all metadata
        ],
    )),
])
```

**Behavior:** Records sensor data from multiple cameras, excluding metadata.

### Example 4: Debug Logging
```python
Filter.run_multi([
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///debug/full_data.jsonl',
        rules=['+'],  # Include everything for debugging
        empty=2,      # Include even empty structures
        flush=True,   # Immediate flush for debugging
    )),
])
```

**Behavior:** Records complete data for debugging purposes.

### Example 5: Selective Field Recording
```python
Filter.run_multi([
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///reports/summary.csv',
        rules=[
            '+main/data/detection_count',
            '+main/data/average_confidence',
            '+main/data/processing_time',
            '+camera1/data/frame_rate',
            '+camera2/data/frame_rate',
        ],
        empty=1,
    )),
])
```

**Behavior:** Records only summary statistics for reporting.

### Example 6: Multi-Topic Recording
```python
Filter.run_multi([
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///logs/all_topics.jsonl',
        rules=[
            '+main/data/detections',
            '+main/data/confidence',
            '+face/data/faces',
            '+face/data/emotions',
            '+license_plate/data/text',
            '+license_plate/data/confidence',
            '-/meta/fps',
            '-/meta/cpu',
            '-/meta/mem',
        ],
    )),
])
```

**Behavior:** Records data from multiple processing topics while excluding system metrics.

## CSV Format Details

### Header Generation
- **Automatic Headers**: Generated from first record
- **Field Naming**: Uses dot notation for nested fields
- **Column Order**: Determined by first record structure
- **Header Validation**: Ensures consistency across records

### Field Naming Convention
```python
# Nested data structure
{
    "main": {
        "data": {
            "detections": [{"class": "person", "confidence": 0.95}]
        }
    }
}

# CSV column names
main_data_detections_class
main_data_detections_confidence
```

### CSV Compatibility
- **Excel Compatible**: Standard CSV format
- **Quote Handling**: Proper escaping of special characters
- **Newline Handling**: Standard line endings
- **Encoding**: UTF-8 encoding

## Performance Considerations

### File I/O
- **Synchronous Writes**: Blocking file operations
- **Flush Control**: Optional immediate flushing
- **Buffer Management**: Standard Python file buffering
- **Disk Space**: Monitor output file sizes

### Memory Usage
- **Data Copying**: Deep copy of filtered data
- **Rule Processing**: Minimal memory overhead
- **CSV Headers**: Stored for consistency checking
- **Large Records**: Consider memory usage for large data

### Processing Overhead
- **Rule Evaluation**: Linear complexity with number of rules
- **Data Filtering**: Efficient dictionary operations
- **CSV Conversion**: Additional processing for CSV format
- **Empty Pruning**: Recursive cleanup operations

## Error Handling

### File System Issues
- **Permission Errors**: Graceful handling with clear messages
- **Disk Space**: Continues processing if possible
- **Directory Creation**: Automatic directory creation
- **File Locks**: Handles concurrent access issues

### Data Processing Errors
- **Invalid Rules**: Clear error messages for malformed rules
- **Data Structure**: Handles missing or malformed data
- **CSV Consistency**: Validates CSV structure consistency
- **Serialization**: Handles non-serializable data types

### Common Error Scenarios
- **Missing Fields**: Continues processing with available data
- **Type Mismatches**: Handles different data types gracefully
- **Empty Data**: Configurable handling based on `empty` setting
- **Rule Conflicts**: Last rule takes precedence

## Debugging and Monitoring

### Debug Logging
```python
# Enable debug logging
export DEBUG_RECORDER=true
export LOG_LEVEL=DEBUG
```

### Debug Information
- **Rule Processing**: Shows each rule application
- **Data Filtering**: Shows before/after data states
- **File Operations**: Logs file write operations
- **Error Details**: Detailed error information

### Monitoring
- **File Sizes**: Monitor output file growth
- **Write Rates**: Track data recording frequency
- **Error Rates**: Monitor processing errors
- **Disk Usage**: Track storage consumption

## Troubleshooting

### Common Issues

#### No Data Being Recorded
1. Check rule syntax and logic
2. Verify data structure matches rules
3. Check `empty` parameter setting
4. Ensure output file permissions

#### CSV Header Issues
1. Verify first record has expected structure
2. Check for dynamic field names
3. Ensure consistent data types
4. Validate field naming conventions

#### File Permission Errors
1. Check output directory permissions
2. Verify file write permissions
3. Ensure sufficient disk space
4. Check for file locks

#### Performance Issues
1. Optimize rule complexity
2. Reduce data volume with better filtering
3. Consider CSV vs JSON trade-offs
4. Monitor disk I/O performance

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable recorder debugging
export DEBUG_RECORDER=true
```

## Advanced Usage

### Dynamic Rule Generation
```python
# Rules can be generated dynamically based on configuration
rules = ['+']  # Start with everything
if exclude_timestamps:
    rules.append('-/meta/ts')
if exclude_metrics:
    rules.extend(['-/meta/fps', '-/meta/cpu', '-/meta/mem'])
if include_detections:
    rules.append('+main/data/detections')
```

### Conditional Recording
```python
# Use with other filters for conditional recording
Filter.run_multi([
    (ThresholdFilter, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        threshold=0.8,
    )),
    (Recorder, dict(
        sources='tcp://localhost:5552',
        outputs='file:///logs/high_confidence.jsonl',
        rules=['+main/data/detections'],
    )),
])
```

### Multi-Format Recording
```python
# Record same data in different formats
Filter.run_multi([
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///logs/detailed.jsonl',
        rules=['+'],  # Full data in JSON
    )),
    (Recorder, dict(
        sources='tcp://localhost:5550',
        outputs='file:///reports/summary.csv',
        rules=['+main/data/detections'],  # Summary in CSV
    )),
])
```

## API Reference

### RecorderConfig
```python
class RecorderConfig(FilterConfig):
    outputs: str | list[str] | list[tuple[str, dict[str, Any]]]
    rules: list[str]
    empty: int | None
    flush: bool | None
```

### Recorder
```python
class Recorder(Filter):
    FILTER_TYPE = 'Output'
    
    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
    @staticmethod
    def prune_empties(d: dict) -> dict
    @staticmethod
    def to_csv(d: dict) -> list[CSVEntry]
```

### Environment Variables
- `DEBUG_RECORDER`: Enable debug logging
- `FILTER_SOURCES`: Input sources
- `FILTER_OUTPUTS`: Output file path
- `FILTER_RULES`: Data filtering rules
- `FILTER_EMPTY`: Empty data handling level
- `FILTER_FLUSH`: File flush behavior
