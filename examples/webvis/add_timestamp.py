#!/usr/bin/env python3
"""
Add Timestamp to Video

This script adds a timestamp overlay to a video file and saves it to the data directory.
It uses the sample video from the openfilter-heroku-demo assets.

Usage:
    python add_timestamp.py
"""

import os
import cv2
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_timestamp_to_video(input_path, output_path):
    """Add timestamp overlay to video."""
    # Open input video
    cap = cv2.VideoCapture(input_path)
    
    if not cap.isOpened():
        logger.error(f"Could not open input video: {input_path}")
        return False
    
    # Get video properties
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    logger.info(f"Input video properties:")
    logger.info(f"  - FPS: {fps}")
    logger.info(f"  - Resolution: {width}x{height}")
    logger.info(f"  - Total frames: {total_frames}")
    
    # Create output directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Setup video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    frame_count = 0
    start_time = datetime.now()
    
    logger.info("Processing video frames...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Calculate timestamp
        current_time = start_time.timestamp() + (frame_count / fps)
        timestamp = datetime.fromtimestamp(current_time)
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Include milliseconds
        
        # Add timestamp overlay
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        color = (255, 255, 255)  # White
        thickness = 2
        
        # Add background rectangle for better visibility
        text_size = cv2.getTextSize(timestamp_str, font, font_scale, thickness)[0]
        text_x = 10
        text_y = 30
        
        # Draw background rectangle
        cv2.rectangle(frame, 
                     (text_x - 5, text_y - text_size[1] - 5), 
                     (text_x + text_size[0] + 5, text_y + 5), 
                     (0, 0, 0), -1)
        
        # Draw timestamp text
        cv2.putText(frame, timestamp_str, (text_x, text_y), font, font_scale, color, thickness)
        
        # Add frame counter
        frame_counter_text = f"Frame: {frame_count + 1}/{total_frames}"
        counter_size = cv2.getTextSize(frame_counter_text, font, 0.5, 1)[0]
        counter_x = width - counter_size[0] - 10
        counter_y = 30
        
        # Draw background for frame counter
        cv2.rectangle(frame, 
                     (counter_x - 5, counter_y - counter_size[1] - 5), 
                     (counter_x + counter_size[0] + 5, counter_y + 5), 
                     (0, 0, 0), -1)
        
        # Draw frame counter
        cv2.putText(frame, frame_counter_text, (counter_x, counter_y), font, 0.5, color, 1)
        
        # Write frame to output video
        out.write(frame)
        
        frame_count += 1
        
        # Progress update every 100 frames
        if frame_count % 100 == 0:
            progress = (frame_count / total_frames) * 100
            logger.info(f"Progress: {progress:.1f}% ({frame_count}/{total_frames} frames)")
    
    # Release everything
    cap.release()
    out.release()
    
    logger.info(f"Video processing complete!")
    logger.info(f"Output saved to: {output_path}")
    logger.info(f"Total frames processed: {frame_count}")
    
    return True

def main():
    """Main function."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Source video path (from openfilter-heroku-demo assets)
    source_video = os.path.join(script_dir, "..", "openfilter-heroku-demo", "assets", "sample-video.mp4")
    
    # Output video path
    output_video = os.path.join(script_dir, "data", "sample-video-with-timestamp.mp4")
    
    # Check if source video exists
    if not os.path.exists(source_video):
        logger.error(f"Source video not found: {source_video}")
        logger.error("Please ensure the openfilter-heroku-demo assets are available")
        return False
    
    logger.info("Adding timestamp to video...")
    logger.info(f"Source: {source_video}")
    logger.info(f"Output: {output_video}")
    
    # Process video
    success = add_timestamp_to_video(source_video, output_video)
    
    if success:
        logger.info(" Video with timestamp created successfully!")
        logger.info(f" Output file: {output_video}")
        logger.info(" You can now use this video with the webvis examples")
    else:
        logger.error(" Failed to create video with timestamp")
        return False
    
    return True

if __name__ == '__main__':
    main()
