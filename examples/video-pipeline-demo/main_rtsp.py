#!/usr/bin/env python3
"""
Video Pipeline Demo with RTSP Support

This example demonstrates a comprehensive video processing pipeline using OpenFilter with support for both:
1. Local video files (from ./data folder)
2. RTSP streams (from RTSP streamer)

The pipeline processes multiple video streams in parallel, with face detection, camera analysis, 
frame deduplication, and cloud storage integration.

Usage:
    # With local video files
    python main_rtsp.py --mode files
    
    # With RTSP streams
    python main_rtsp.py --mode rtsp
    
    # With specific RTSP URLs
    python main_rtsp.py --mode rtsp --rtsp-urls "rtsp://localhost:8554/stream0,rtsp://localhost:8554/stream1,rtsp://localhost:8554/stream2"
"""

import os
import logging
import argparse
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis
from openfilter.filter_runtime.filters.image_out import ImageOut
from filter_frame_dedup.filter import FilterFrameDedup
from filter_faceblur.filter import FilterFaceblur
from filter_crop.filter import FilterCrop
from filter_connector_gcs.filter import FilterConnectorGCS
from vizcal.filter import Vizcal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_video_sources(mode, rtsp_urls=None):
    """Get video sources based on mode."""
    if mode == "files":
        # Use local video files from ./data folder
        video1_path = os.getenv('VIDEO1_PATH', './data/01.mp4')
        video2_path = os.getenv('VIDEO2_PATH', './data/02.mp4')
        video3_path = os.getenv('VIDEO3_PATH', './data/03.mp4')
        
        # Check if video files exist
        for path, name in [(video1_path, "Video 1"), (video2_path, "Video 2"), (video3_path, "Video 3")]:
            if not os.path.exists(path):
                logger.warning(f"{name} not found: {path}. Please provide {name.upper().replace(' ', '')}_PATH environment variable.")
                return None
        
        sources = f'''
            file://{video1_path}!loop,          
            file://{video2_path}!loop;stream2,
            file://{video3_path}!loop;stream3
        '''
        logger.info("Using local video files:")
        logger.info(f"  Video 1 (Sallon): {video1_path}")
        logger.info(f"  Video 2 (Kitchen): {video2_path}")
        logger.info(f"  Video 3 (Reception): {video3_path}")
        
    elif mode == "rtsp":
        # Use RTSP streams
        if rtsp_urls:
            urls = rtsp_urls.split(',')
        else:
            # Default RTSP URLs
            urls = [
                "rtsp://localhost:8554/stream0",
                "rtsp://localhost:8554/stream1", 
                "rtsp://localhost:8554/stream2"
            ]
        
        # Ensure we have at least 3 streams
        while len(urls) < 3:
            urls.append(f"rtsp://localhost:8554/stream{len(urls)}")
        
        sources = f'''
            {urls[0]}!loop,          
            {urls[1]}!loop;stream2,
            {urls[2]}!loop;stream3
        '''
        logger.info("Using RTSP streams:")
        logger.info(f"  Stream 1 (Sallon): {urls[0]}")
        logger.info(f"  Stream 2 (Kitchen): {urls[1]}")
        logger.info(f"  Stream 3 (Reception): {urls[2]}")
    
    else:
        raise ValueError(f"Invalid mode: {mode}. Use 'files' or 'rtsp'")
    
    return sources

def main():
    """Run the video pipeline demo with RTSP support."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Video Pipeline Demo with RTSP Support')
    parser.add_argument('--mode', choices=['files', 'rtsp'], default='files',
                       help='Video source mode: files (local) or rtsp (streams)')
    parser.add_argument('--rtsp-urls', type=str,
                       help='Comma-separated RTSP URLs (e.g., "rtsp://localhost:8554/stream0,rtsp://localhost:8554/stream1")')
    args = parser.parse_args()
    
    # Get video sources based on mode
    sources = get_video_sources(args.mode, args.rtsp_urls)
    if sources is None:
        return
    
    # Get GCS configuration from environment or use defaults
    gcs_bucket = os.getenv('GCS_BUCKET')
    gcs_path = os.getenv('GCS_PATH', 'video-pipeline-demo')
    segment_duration = float(os.getenv('SEGMENT_DURATION', '0.2'))
    image_directory = os.getenv('IMAGE_DIRECTORY', './output/sallon')
    
    # Get VizCal configuration from environment or use defaults
    vizcal_config = {
        'calculate_camera_stability': os.getenv('FILTER_CALCULATE_CAMERA_STABILITY', 'True').lower() == 'true',
        'calculate_video_properties': os.getenv('FILTER_CALCULATE_VIDEO_PROPERTIES', 'True').lower() == 'true',
        'calculate_movement': os.getenv('FILTER_CALCULATE_MOVEMENT', 'False').lower() == 'true',
        'shake_threshold': float(os.getenv('FILTER_SHAKE_THRESHOLD', '5')),
        'movement_threshold': float(os.getenv('FILTER_MOVEMENT_THRESHOLD', '1.0')),
        'forward_upstream_data': os.getenv('FILTER_FORWARD_UPSTREAM_DATA', 'True').lower() == 'true',
        'show_text_overlays': os.getenv('FILTER_SHOW_TEXT_OVERLAYS', 'True').lower() == 'true',
    }
    
    logger.info("Starting Video Pipeline Demo")
    logger.info(f"Mode: {args.mode.upper()}")
    logger.info("=" * 60)
    
    # Define the filter pipeline
    filters = [
        # Video Input - Multiple streams with different topics
        (VideoIn, {
            "id": "video_in",
            "sources": sources,
            "outputs": "tcp://*:5550",
        }),
        
        # Face Blur - Stream 1 (main topic)
        (FilterFaceblur, {
            "id": "faceblur_1",
            "sources": "tcp://localhost:5550;main",
            "outputs": "tcp://*:5552",
            "detector_name": "yunet",
            "blurrer_name": "gaussian",
            "blur_strength": 2.0,
            "detection_confidence_threshold": 0.3,
            "include_face_coordinates": True,
            "forward_upstream_data": True,
            "debug": False,
        }),
        
        # Face Blur - Stream 2 (stream2 topic)
        (FilterFaceblur, {
            "id": "faceblur_2",
            "sources": "tcp://localhost:5550;stream2",
            "outputs": "tcp://*:5554",
            "detector_name": "yunet",
            "blurrer_name": "gaussian",
            "blur_strength": 0.0,
            "detection_confidence_threshold": 0.3,
            "include_face_coordinates": True,
            "forward_upstream_data": True,
            "debug": False,
        }),
        
        # Face Blur - Stream 3 (stream3 topic)
        (FilterFaceblur, {
            "id": "faceblur_3",
            "sources": "tcp://localhost:5550;stream3",
            "outputs": "tcp://*:5556",
            "detector_name": "yunet",
            "blurrer_name": "gaussian",
            "blur_strength": 10,
            "detection_confidence_threshold": 0.3,
            "include_face_coordinates": True,
            "forward_upstream_data": True,
            "debug": False,
        }),
        
        # VizCal - Stream 2 analysis (after face blur)
        (Vizcal, {
            "id": "vizcal_stream2",
            "sources": "tcp://localhost:5554;stream2",
            "outputs": "tcp://*:5580",
            "calculate_camera_stability": vizcal_config['calculate_camera_stability'],
            "calculate_video_properties": vizcal_config['calculate_video_properties'],
            "calculate_movement": vizcal_config['calculate_movement'],
            "shake_threshold": vizcal_config['shake_threshold'],
            "movement_threshold": vizcal_config['movement_threshold'],
            "forward_upstream_data": vizcal_config['forward_upstream_data'],
            "show_text_overlays": vizcal_config['show_text_overlays'],
        }),
        
        # Face Crop - Stream 2 (from VizCal output with face detections)
        (FilterCrop, {
            "id": "facecrop",
            "sources": "tcp://localhost:5554;stream2",
            "outputs": "tcp://*:5558",
            "detection_key": "detections",
            "detection_class_field": "class",
            "detection_roi_field": "rois",
            "output_prefix": "face_",
            "mutate_original_frames": False,
            "topic_mode": "all",
        }),
        
        # ImageOut - Save only cropped face images
        (ImageOut, {
            "id": "face_crops_output",
            "sources": "tcp://localhost:5558",
            "outputs": [
                "file://./output/face_crops/crop_%Y%m%d_%H%M%S_%d.png!format=png!compression=0;face_*"
            ],
            "bgr": True,
            "quality": 95,
            "compression": 6
        }),
        
        # Frame Deduplication
        (FilterFrameDedup, {
            "id": "frame_dedup_crops",
            "sources": "tcp://localhost:5550",
            "outputs": "tcp://*:5560",
            "hash_threshold": 5,
            "motion_threshold": 1200,
            "min_time_between_frames": 1.0,
            "ssim_threshold": 0.90,
            "output_folder": "./output/sallon",
            "forward_deduped_frames": True,
            "save_images": True,
            "debug": False,
        }),
        
        # GCS Connector - Upload multiple streams to different folders in GCS
        (FilterConnectorGCS, {
            "id": "gcs_connector",
            "sources": [
                "tcp://localhost:5552;main",      # Stream 1 (face blurred)
                "tcp://localhost:5554;stream2",   # Stream 2 (face blurred + VizCal analysis) 
                "tcp://localhost:5556;stream3",   # Stream 3 (face blurred)
            ],
            "outputs": [
                f"gs://{gcs_bucket}/{gcs_path}/stream2/stream2_%Y-%m-%d_%H-%M-%S.mp4!segtime={segment_duration};stream2", 
                f"gs://{gcs_bucket}/{gcs_path}/stream1/stream1_%Y-%m-%d_%H-%M-%S.mp4!segtime={segment_duration};main",
                f"gs://{gcs_bucket}/{gcs_path}/stream3/stream3_%Y-%m-%d_%H-%M-%S.mp4!segtime={segment_duration};stream3",
            ],
            "gcs_bucket": gcs_bucket,
            "gcs_path": gcs_path,
            "segment_duration": segment_duration,
            "image_directory": image_directory,
            "debug": True,
        }),
        
        # Web Visualization - Multiple streams
        (Webvis, {
            "id": "webvis",
            "sources": [
                "tcp://localhost:5552;main>stream1",  # Stream 1 with face crops
                "tcp://localhost:5554;stream2",       # Stream 2 with VizCal analysis
                "tcp://localhost:5556;stream3",       # Stream 3 with face crops
            ],
            "port": 8000,
        }),
        
        # Web Visualization - Face crops and analysis
        (Webvis, {
            "id": "webvis_crops",
            "sources": [
                "tcp://localhost:5560",  # All topics from FilterFrameDedup
                "tcp://localhost:5580;stream2>stream2_info",  # Stream 2 with VizCal analysis
            ],
            "port": 8001,
        }),
    ]
    
    logger.info("Pipeline Configuration:")
    logger.info("Stream 1: Video → FaceBlur → Webvis")
    logger.info("Stream 2: Video → FaceBlur → VizCal → FaceCrop → ImageOut + Webvis + GCS")
    logger.info("Stream 3: Video → FaceBlur → Webvis")
    logger.info("Deduplication: Video → FrameDedup → GCS Connector")
    logger.info("Webvis available at:")
    logger.info("  - Main streams: http://localhost:8000")
    logger.info("    - Stream 1: http://localhost:8000/stream1 (face blurred)")
    logger.info("    - Stream 2: http://localhost:8000/stream2 (face blurred + VizCal analysis)")
    logger.info("    - Stream 3: http://localhost:8000/stream3 (face blurred)")
    logger.info("  - Face crops: http://localhost:8001 (all FilterCrop outputs)")
    logger.info("Image outputs:")
    logger.info("  - Cropped face images only (face_* topics): ./output/face_crops/")
    logger.info("  - Deduplicated frames: ./output/sallon/")
    if gcs_bucket:
        logger.info("GCS Configuration:")
        logger.info(f"  - Bucket: {gcs_bucket}")
        logger.info(f"  - Path: {gcs_path}")
    logger.info("=" * 60)
    
    try:
        # Run the pipeline
        Filter.run_multi(filters)
    except KeyboardInterrupt:
        logger.info("Pipeline stopped by user")
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise

if __name__ == '__main__':
    main()
