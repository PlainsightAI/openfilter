#!/usr/bin/env python3
"""
Video Pipeline Demo

This example demonstrates a comprehensive video processing pipeline using OpenFilter:
1. VideoIn - Reads multiple video streams
2. FilterFrameDedup - Deduplicates frames in one stream
3. FilterFaceblur - Applies face blurring to all streams
4. FilterCrop - Crops images from face detections
5. ImageOut - Saves cropped face images in multiple formats
6. Webvis - Provides web-based visualization

The pipeline processes multiple video streams in parallel, with face cropping and
image saving capabilities for analysis and archival purposes.
"""

import os
import logging
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis
from openfilter.filter_runtime.filters.image_out import ImageOut
from filter_frame_dedup.filter import FilterFrameDedup
from filter_faceblur.filter import FilterFaceblur
from filter_crop.filter import FilterCrop
from filter_connector_gcs.filter import FilterConnectorGCS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Run the video pipeline demo."""
    
    # Get video file paths from environment or use defaults
    video1_path = os.getenv('VIDEO1_PATH', 'sample_video1.mp4')
    video2_path = os.getenv('VIDEO2_PATH', 'sample_video2.mp4')
    video3_path = os.getenv('VIDEO3_PATH', 'sample_video3.mp4')
    
    # Get GCS configuration from environment or use defaults
    gcs_bucket = os.getenv('GCS_BUCKET')
    gcs_path = os.getenv('GCS_PATH', 'video-pipeline-demo/deduplicated-frames')
    segment_duration = float(os.getenv('SEGMENT_DURATION', '0.2'))
    image_directory = os.getenv('IMAGE_DIRECTORY', './output/sallon')
    
    # Check if video files exist
    if not os.path.exists(video1_path):
        logger.warning(f"Video 1 not found: {video1_path}. Please provide VIDEO1_PATH environment variable.")
        return
    
    if not os.path.exists(video2_path):
        logger.warning(f"Video 2 not found: {video2_path}. Please provide VIDEO2_PATH environment variable.")
        return
    
    if not os.path.exists(video3_path):
        logger.warning(f"Video 3 not found: {video3_path}. Please provide VIDEO3_PATH environment variable.")
        return
    
    logger.info("Starting Video Pipeline Demo")
    logger.info(f"Video 1: {video1_path}")          
    logger.info(f"Video 2: {video2_path}")          
    logger.info(f"Video 3: {video3_path}")          
    logger.info("=" * 60)
    
    # Define the filter pipeline
    filters = [
        # Video Input - Two streams with different topics
        # main sallon
        # stream2 kitchen 
        # stream3 reception
        (VideoIn, {
            "id": "video_in",
            "sources": f'''
                file://{video1_path}!loop,          
                file://{video2_path}!loop;stream2,
                file://{video3_path}!loop;stream3
            ''',
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
        
        # Face Crop - Stream 1 (from face detections)
        (FilterCrop, {
            "id": "facecrop",
            "sources": "tcp://localhost:5554",
            "outputs": "tcp://*:5558",
            "detection_key": "detections",
            "detection_class_field": "class",
            "detection_roi_field": "rois",
            "output_prefix": "face_",
            "mutate_original_frames": False,  # Creates both 'main' and 'face_*' topics
            "topic_mode": "all",
        }),
        
        # ImageOut - Save only cropped face images (using wildcard topic filtering)
        (ImageOut, {
            "id": "face_crops_output",
            "sources": "tcp://localhost:5558",  # Receive all topics from FilterCrop
            "outputs": [
                "file://./output/face_crops/crop_%Y%m%d_%H%M%S_%d.png!format=png!compression=0;face_*"
            ],
            "bgr": True,
            "quality": 95,
            "compression": 6
        }),
        
        # Frame Deduplication - On face crops
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
                "tcp://localhost:5554;stream2",   # Stream 2 (face blurred) 
                "tcp://localhost:5556;stream3",   # Stream 3 (face blurred)
            ],
            "outputs": [
                # stream2 first because the images are saved in the stream2 folder
                f"gs://{gcs_bucket}/{gcs_path}/stream2/stream2_%Y-%m-%d_%H-%M-%S.mp4!segtime={segment_duration};stream2", 
                
                f"gs://{gcs_bucket}/{gcs_path}/stream1/stream1_%Y-%m-%d_%H-%M-%S.mp4!segtime={segment_duration};main",
                
                f"gs://{gcs_bucket}/{gcs_path}/stream3/stream3_%Y-%m-%d_%H-%M-%S.mp4!segtime={segment_duration};stream3",
            ],
            "gcs_bucket": gcs_bucket,
            "gcs_path": gcs_path,
            "segment_duration": segment_duration,
            "image_directory": image_directory,
            "debug": True,   # Enable debug to see what's happening
        }),
        
        # Web Visualization - Multiple streams
        (Webvis, {
            "id": "webvis",
            "sources": [
                "tcp://localhost:5552;main>stream1",  # Stream 1 with face crops
                "tcp://localhost:5554;stream2",  # Stream 2 with face crops
                "tcp://localhost:5556;stream3",  # Stream 3 with face crops
            ],
            "port": 8000,
        }),
        
        (Webvis, {
            "id": "webvis_crops",
            "sources": [
                "tcp://localhost:5560",  # All topics from FilterCrop (including face crops)
            ],
            "port": 8001,
        }),
    ]
    
    logger.info("Pipeline Configuration:")
    logger.info("Stream 1: Video → FaceBlur → Webvis")
    logger.info("Stream 2: Video → FaceBlur → FaceCrop → ImageOut (face_* topics only) + Webvis")
    logger.info("Stream 3: Video → FaceBlur → Webvis")
    logger.info("Deduplication: Video → FrameDedup → GCS Connector")
    logger.info("Webvis available at:")
    logger.info("  - Main streams: http://localhost:8000")
    logger.info("    - Stream 1: http://localhost:8000/stream1 (face blurred)")
    logger.info("    - Stream 2: http://localhost:8000/stream2 (face blurred)")
    logger.info("    - Stream 3: http://localhost:8000/stream3 (face blurred)")
    logger.info("  - Face crops: http://localhost:8001 (all FilterCrop outputs)")
    logger.info("Image outputs:")
    logger.info("  - Cropped face images only (face_* topics): ./output/face_crops/")
    logger.info("  - Deduplicated frames: ./output/sallon/")
    logger.info("GCS Configuration:")
    logger.info("  - Bucket: protege-artifacts-development")
    logger.info("  - Path: video-pipeline-demo/deduplicated-frames")
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
