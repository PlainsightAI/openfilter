# Video Pipeline Demo

This example demonstrates a comprehensive video processing pipeline using OpenFilter with multiple filters working together to process two video streams in parallel.

## 🚀 Ready to Use

This example is complete and ready to run! It includes:
- ✅ Complete pipeline script (`main.py`)
- ✅ Sample video files for testing
- ✅ All configuration files
- ✅ Test script to verify setup
- ✅ Comprehensive documentation

## Pipeline Overview

The demo showcases a sophisticated video processing pipeline with two parallel streams:

**Stream 1 (with deduplication):**
```
VideoIn → FilterFrameDedup → FilterFaceblur → FilterCrop → Webvis
```

**Stream 2 (direct processing):**
```
VideoIn → FilterFaceblur → FilterCrop → Webvis
```

## Features

- **Dual Video Input**: Processes two video streams simultaneously
- **Frame Deduplication**: Reduces redundant frames in one stream using multiple detection methods
- **Face Detection & Blurring**: Automatically detects and blurs faces in both streams
- **Face Cropping**: Extracts cropped images from detected faces
- **Real-time Visualization**: Web interface to view processed streams

## Quick Start

### Prerequisites

1. Install OpenFilter and required filters:
```bash
# Install from the openfilter package index
pip install -r requirements.txt

# Or install from local development versions (if available)
pip install ../../filter-frame-dedup
pip install ../../filter-faceblur  
pip install ../../filter-crop
```

2. Prepare video files:
```bash
# Place your video files in the example directory
cp your_video1.mp4 sample_video1.mp4
cp your_video2.mp4 sample_video2.mp4
```

3. Test the installation:
```bash
python test_pipeline.py
```

### Running the Demo

```bash
# Basic usage with default video files
python main.py

# Or specify custom video files
VIDEO1_PATH=path/to/video1.mp4 VIDEO2_PATH=path/to/video2.mp4 python main.py
```

### Viewing Results

Open your browser and navigate to:
- **Webvis Interface**: http://localhost:8000
- **Stream 1**: http://localhost:8000/stream1 (face-blurred frames)
- **Stream 2**: http://localhost:8000/stream2 (face-blurred frames)
- **Stream 3**: http://localhost:8000/stream3 (face-blurred frames)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIDEO1_PATH` | `sample_video1.mp4` | Path to first video file |
| `VIDEO2_PATH` | `sample_video2.mp4` | Path to second video file |
| `VIDEO3_PATH` | `sample_video3.mp4` | Path to third video file |

### Filter Configuration

The pipeline uses the following filter configurations:

#### FilterFrameDedup
- **Hash Threshold**: 5 (lower = more sensitive)
- **Motion Threshold**: 1200 (lower = more sensitive)
- **SSIM Threshold**: 0.90 (lower = more dissimilar)
- **Min Time Between Frames**: 1.0 seconds

#### FilterFaceblur
- **Detector**: YuNet face detection model
- **Blur Algorithm**: Gaussian blur
- **Blur Strength**: 2.0 (higher = more blur)
- **Confidence Threshold**: 0.3 (lower = detect more faces)

#### FilterCrop
- **Detection Key**: `face_coordinates`
- **Output Prefix**: `face_crop_1_` and `face_crop_2_`
- **Topic Mode**: `main_only`

## Output

The pipeline generates several outputs:

1. **Deduplicated Frames**: Saved to `./output/deduped_frames/`
2. **Web Visualization**: Real-time display of processed streams
3. **Face Crops**: Individual cropped face images in the web interface

## Pipeline Architecture

```
┌─────────────┐    ┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│   Video 1   │───▶│ FilterFrameDedup│───▶│ FilterFaceblur│───▶│ FilterCrop  │
└─────────────┘    └─────────────────┘    └──────────────┘    └─────────────┘
                                                                    │
┌─────────────┐    ┌──────────────┐    ┌─────────────┐             │
│   Video 2   │───▶│ FilterFaceblur│───▶│ FilterCrop  │─────────────┘
└─────────────┘    └──────────────┘    └─────────────┘
                                                           │
                                                           ▼
                                                    ┌─────────────┐
                                                    │   Webvis    │
                                                    │ (Port 8000) │
                                                    └─────────────┘
```

## Use Cases

This pipeline is ideal for:

- **Privacy Protection**: Automatically blur faces in surveillance footage
- **Content Analysis**: Extract keyframes and face regions from video content
- **Storage Optimization**: Reduce storage by deduplicating similar frames
- **Real-time Processing**: Process live video streams with multiple filters

## Troubleshooting

### Common Issues

1. **Video files not found**: Ensure video files exist and paths are correct
2. **Port conflicts**: Make sure port 8000 is available for Webvis
3. **Memory issues**: Large video files may require more memory

### Debug Mode

Enable debug logging by modifying the filter configurations in `main.py`:
```python
"debug": True,  # Enable for FilterFrameDedup and FilterFaceblur
```

## License

Apache-2.0
