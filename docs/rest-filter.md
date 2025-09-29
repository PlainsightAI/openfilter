# REST Filter

The REST filter is an input filter for OpenFilter that provides HTTP REST API endpoints to receive data from external sources. It exposes FastAPI endpoints that can accept JSON payloads and binary data, then forwards the received data through the OpenFilter pipeline as Frame objects.

## Overview

The REST filter is designed to handle HTTP-based data ingestion scenarios where you need to:
- Accept data from web applications and external systems
- Provide RESTful API endpoints for data ingestion
- Support various HTTP methods (GET, POST, PUT, PATCH, DELETE)
- Load local files from a specified resource path
- Convert HTTP requests into OpenFilter Frame objects
- Handle JSON and binary data payloads

## Key Features

- **REST API Endpoints**: FastAPI-based HTTP server with multiple endpoints
- **JSON Payload Support**: Direct JSON data ingestion
- **Local File Loading**: Serve files from local resource path
- **Path Parameters**: Dynamic endpoint routing with path parameters
- **HTTP Methods**: Support for GET, POST, PUT, PATCH, DELETE
- **Data Conversion**: Automatic conversion to Frame objects
- **Resource Management**: Local file serving capabilities

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.rest import Rest

# Simple REST API server
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
    )),
])
```

### Advanced Configuration

```python
# REST API with local resources
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
        resource_path='/path/to/local/files',
        methods=['GET', 'POST', 'PUT'],
        endpoints=['/data', '/files/{filename}'],
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_OUTPUTS="tcp://*:5550"
export FILTER_HOST="0.0.0.0"
export FILTER_PORT="8080"
export FILTER_RESOURCE_PATH="/path/to/files"
export FILTER_METHODS="GET,POST,PUT"
export FILTER_ENDPOINTS="/data,/files/{filename}"
```

## HTTP Endpoints

### Default Endpoints

The REST filter provides several built-in endpoints:

#### 1. Root Endpoint (`/`)
- **Method**: GET
- **Purpose**: Health check and basic information
- **Response**: JSON with server status

#### 2. Data Endpoint (`/data`)
- **Method**: POST, PUT, PATCH
- **Purpose**: JSON data ingestion
- **Content-Type**: `application/json`
- **Body**: JSON payload

#### 3. Dynamic File Endpoint (`/files/{filename}`)
- **Method**: GET, POST, PUT, PATCH, DELETE
- **Purpose**: File operations with path parameters
- **Path Parameters**: `filename` - the file to operate on

### Custom Endpoints

You can define custom endpoints using the `endpoints` configuration:

```python
endpoints=[
    '/api/v1/data',
    '/api/v1/files/{filename}',
    '/custom/endpoint/{id}',
]
```

## HTTP Methods

### Supported Methods
- **GET**: Retrieve data and files
- **POST**: Send data
- **PUT**: Update/replace data
- **PATCH**: Partial data updates
- **DELETE**: Remove data

### Method Configuration
```python
methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
```

## Data Handling

### JSON Payload Processing
The REST filter converts JSON payloads into Frame objects:

```python
# Incoming JSON
{
    "detections": [
        {"class": "person", "confidence": 0.95, "bbox": [100, 100, 200, 200]}
    ],
    "timestamp": "2024-01-15T10:30:00Z",
    "camera_id": "cam1"
}

# Converted to Frame object
frame = Frame()
frame.data = {
    "detections": [...],
    "timestamp": "...",
    "camera_id": "cam1"
}
```


## Local File Serving

### Resource Path Configuration
The `resource_path` parameter specifies where local files are served from:

```python
resource_path='/path/to/local/files'
```

### File Access
Files can be accessed via the `/files/{filename}` endpoint:

```
GET /files/image1.jpg
GET /files/data/sensor_readings.json
GET /files/videos/sample.mp4
```

### File Operations
Different HTTP methods provide different file operations:

- **GET**: Download/read file
- **POST**: Create file
- **PUT**: Replace file content
- **PATCH**: Update file metadata
- **DELETE**: Remove file

## Usage Examples

### Example 1: Basic REST API Server
```python
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (ImageOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///output/detected_{frame_number}.jpg',
    )),
])
```

**Behavior:** Accepts HTTP requests, processes data through object detection, and saves results.

### Example 2: Data Processing Pipeline
```python
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
        resource_path='/data',
        endpoints=['/data', '/files/{filename}'],
    )),
    (DataProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (OutputFilter, dict(
        sources='tcp://localhost:5552',
        outputs='file:///processed/data.json',
    )),
])
```

**Behavior:** Accepts data requests, processes them, and saves processed results.

### Example 3: JSON Data Ingestion
```python
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
        methods=['POST', 'PUT'],
        endpoints=['/data', '/api/v1/sensors'],
    )),
    (DataProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Recorder, dict(
        sources='tcp://localhost:5552',
        outputs='file:///logs/sensor_data.jsonl',
        rules=['+'],
    )),
])
```

**Behavior:** Accepts JSON sensor data, processes it, and logs results.

### Example 4: Multi-Endpoint API
```python
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
        resource_path='/resources',
        endpoints=[
            '/api/v1/data',
            '/api/v1/files/{filename}',
            '/health',
            '/status',
        ],
    )),
    (Router, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        routing_rules={
            'data': 'tcp://*:5554',
            'files': 'tcp://*:5555',
        },
    )),
])
```

**Behavior:** Provides multiple API endpoints with different processing paths.

### Example 5: Webhook Integration
```python
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
        endpoints=['/webhook/{source}'],
    )),
    (WebhookProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (NotificationSender, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
])
```

**Behavior:** Accepts webhook calls from external services and processes them.

### Example 6: File Management API
```python
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
        resource_path='/files',
        methods=['GET', 'POST', 'PUT', 'DELETE'],
        endpoints=['/files/{filename}'],
    )),
    (FileProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (FileManager, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
])
```

**Behavior:** Provides complete file management API with CRUD operations.

## API Usage Examples

### Sending JSON Data

#### Using curl
```bash
# Send JSON data
curl -X POST http://localhost:8080/data \
  -H "Content-Type: application/json" \
  -d '{
    "detections": [
      {"class": "person", "confidence": 0.95, "bbox": [100, 100, 200, 200]}
    ],
    "timestamp": "2024-01-15T10:30:00Z",
    "camera_id": "cam1"
  }'
```

#### Using Python requests
```python
import requests
import json

# Send JSON data
data = {
    "detections": [
        {"class": "person", "confidence": 0.95, "bbox": [100, 100, 200, 200]}
    ],
    "timestamp": "2024-01-15T10:30:00Z",
    "camera_id": "cam1"
}
response = requests.post('http://localhost:8080/data', json=data)
print(response.json())
```

### File Operations

#### Download file
```bash
# Download a file
curl -X GET http://localhost:8080/files/data1.json -o downloaded_data.json
```

#### Create file
```bash
# Create a new file
curl -X POST http://localhost:8080/files/new_data.json \
  -H "Content-Type: application/json" \
  -d '{"data": "content"}'
```

#### Delete file
```bash
# Delete a file
curl -X DELETE http://localhost:8080/files/old_data.json
```

## Error Handling

### HTTP Status Codes
- **200 OK**: Successful operation
- **400 Bad Request**: Invalid request data
- **404 Not Found**: Endpoint or file not found
- **405 Method Not Allowed**: Unsupported HTTP method
- **413 Payload Too Large**: File too large
- **500 Internal Server Error**: Server processing error

### Error Response Format
```json
{
    "error": "Error description",
    "detail": "Detailed error information",
    "status_code": 400
}
```

### Common Error Scenarios
- **Invalid JSON**: Malformed JSON payload
- **Missing Files**: File not found in resource path
- **Permission Errors**: File access permission issues
- **Large Data**: Data exceeding size limits
- **Unsupported Methods**: HTTP method not allowed
- **Missing Parameters**: Required parameters not provided

## Security Considerations

### Input Validation
- **Data Type Validation**: Restrict allowed data types
- **Size Limits**: Limit data payload sizes
- **Path Traversal**: Prevent directory traversal attacks
- **Content Validation**: Validate received content

### Access Control
- **Authentication**: Implement authentication mechanisms
- **Authorization**: Control access to endpoints
- **Rate Limiting**: Prevent abuse and DoS attacks
- **CORS**: Configure cross-origin resource sharing

### Security Best Practices
```python
# Example security configuration
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='127.0.0.1',  # Bind to localhost only
        port=8080,
        resource_path='/secure/data',  # Restricted path
        # Add authentication middleware
        # Add rate limiting
        # Add input validation
    )),
])
```

## Performance Considerations

### Request Handling
- **Async Processing**: FastAPI provides async request handling
- **Connection Pooling**: Efficient HTTP connection management
- **Memory Usage**: Monitor memory usage for large data payloads
- **Processing Time**: Consider downstream processing time

### File Operations
- **Streaming**: Stream large files instead of loading into memory
- **Caching**: Cache frequently accessed files
- **Compression**: Use compression for large responses
- **CDN Integration**: Use CDN for static file serving

### Monitoring
- **Request Metrics**: Monitor request rates and response times
- **Error Rates**: Track HTTP error rates
- **Data Operations**: Monitor data processing rates
- **Resource Usage**: Track CPU and memory usage

## Troubleshooting

### Common Issues

#### Server Not Starting
1. Check port availability
2. Verify host binding
3. Check firewall settings
4. Validate configuration parameters

#### Data Processing Failures
1. Check data size limits
2. Verify data permissions
3. Ensure sufficient disk space
4. Validate data format support

#### JSON Processing Errors
1. Validate JSON syntax
2. Check content-type headers
3. Verify data structure
4. Handle encoding issues

#### Path Parameter Issues
1. Validate endpoint patterns
2. Check parameter extraction
3. Verify file path construction
4. Handle special characters

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable REST filter debugging
export DEBUG_REST=true
export LOG_LEVEL=DEBUG
```

### Debug Information
- **Request Logging**: Log all incoming requests
- **Response Logging**: Log response details
- **Data Operations**: Log data access operations
- **Error Details**: Detailed error information

## Advanced Usage

### Custom Middleware
```python
# Add custom middleware for authentication, logging, etc.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Custom Endpoints
```python
# Define additional custom endpoints
@rest_app.post("/custom/endpoint")
async def custom_endpoint(data: dict):
    # Custom processing logic
    return {"status": "processed", "data": data}
```

### Integration with External Systems
```python
# Integrate with external APIs and services
Filter.run_multi([
    # ... other filters above
    (Rest, dict(
        outputs='tcp://*:5550',
        host='0.0.0.0',
        port=8080,
    )),
    (ExternalAPIClient, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        api_url='https://external-api.com',
        api_key='your-api-key',
    )),
    (ResponseFormatter, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
])
```

## API Reference

### RestConfig
```python
class RestConfig(FilterConfig):
    outputs: str | list[str] | list[tuple[str, dict[str, Any]]]
    host: str
    port: int
    resource_path: str | None
    methods: list[str] | None
    endpoints: list[str] | None
```

### Rest
```python
class Rest(Filter):
    FILTER_TYPE = 'Input'
    
    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
    @staticmethod
    def load_file(filename: str, resource_path: str | None) -> bytes
    @staticmethod
    def parse_multipart_data(content: bytes, content_type: str) -> tuple[dict[str, Any], dict[str, bytes]]
    @staticmethod
    def parse_json_data(content: bytes) -> dict[str, Any]
    @staticmethod
    def parse_form_data(content: bytes, content_type: str) -> dict[str, Any]
```

### Environment Variables
- `DEBUG_REST`: Enable debug logging
- `FILTER_OUTPUTS`: Output destinations
- `FILTER_HOST`: Server host address
- `FILTER_PORT`: Server port number
- `FILTER_RESOURCE_PATH`: Local file resource path
- `FILTER_METHODS`: Allowed HTTP methods
- `FILTER_ENDPOINTS`: Custom endpoint patterns
