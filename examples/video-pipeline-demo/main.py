#!/usr/bin/env python3
"""
Video Pipeline Demo

This example demonstrates a comprehensive video processing pipeline using OpenFilter:
1. VideoIn - Reads two video streams
2. FilterFrameDedup - Deduplicates frames in one stream
3. FilterFaceblur - Applies face blurring to both streams
4. FilterCrop - Crops images from face detections

The pipeline processes two video streams in parallel, with one stream going through
frame deduplication before face processing, while the other goes directly to face processing.
"""

import os
import logging
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis
from filter_frame_dedup.filter import FilterFrameDedup
from filter_faceblur.filter import FilterFaceblur
from filter_crop.filter import FilterCrop

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Run the video pipeline demo."""
    
    # Get video file paths from environment or use defaults
    video1_path = os.getenv('VIDEO1_PATH', 'sample_video1.mp4')
    video2_path = os.getenv('VIDEO2_PATH', 'sample_video2.mp4')
    video3_path = os.getenv('VIDEO3_PATH', 'sample_video3.mp4')
    
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
            "blur_strength": 2.0,
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
        
        # Frame Deduplication - Only on Stream 1
        # (FilterFrameDedup, {
        #     "id": "frame_dedup",
        #     "sources": "tcp://localhost:5552",
        #     "outputs": "tcp://*:5556",
        #     "hash_threshold": 5,
        #     "motion_threshold": 1200,
        #     "min_time_between_frames": 1.0,
        #     "ssim_threshold": 0.90,
        #     "output_folder": "./output/deduped_frames",
        #     "forward_deduped_frames": True,
        #     "debug": False,
        # }),
        
        # # Face Crop - Stream 1 (from face detections)
        # (FilterCrop, {
        #     "id": "facecrop_1",
        #     "sources": "tcp://localhost:5556",
        #     "outputs": "tcp://*:5558",
        #     "detection_key": "face_coordinates",
        #     "detection_class_field": "class",
        #     "detection_roi_field": "bbox",
        #     "output_prefix": "face_crop_1_",
        #     "mutate_original_frames": False,
        #     "topic_mode": "main_only",
        # }),
        
        # # Face Crop - Stream 2 (from face detections)
        # (FilterCrop, {
        #     "id": "facecrop_2",
        #     "sources": "tcp://localhost:5554",
        #     "outputs": "tcp://*:5560",
        #     "detection_key": "face_coordinates",
        #     "detection_class_field": "class",
        #     "detection_roi_field": "bbox",
        #     "output_prefix": "face_crop_2_",
        #     "mutate_original_frames": False,
        #     "topic_mode": "main_only",
        # }),
        
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
    ]
    
    logger.info("Pipeline Configuration:")
    logger.info("Stream 1: Video → FaceBlur → Dedup → FaceCrop → Webvis")
    logger.info("Stream 2: Video → FaceBlur → FaceCrop → Webvis")
    logger.info("Webvis available at: http://localhost:8000")
    logger.info("  - Stream 1: http://localhost:8000/main")
    logger.info("  - Stream 2: http://localhost:8000/main")
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
