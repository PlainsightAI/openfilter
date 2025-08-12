#!/usr/bin/env python3
"""
Create a sample video for the observability demo.

This script creates a simple test video that can be used with the demo.
"""

import cv2
import numpy as np
import os


def create_sample_video(output_path="sample_video.mp4", duration=10, fps=30):
    """Create a sample video with moving shapes for testing."""
    
    # Video dimensions
    width, height = 640, 480
    
    # Create video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    print(f"Creating sample video: {output_path}")
    print(f"Duration: {duration}s, FPS: {fps}, Resolution: {width}x{height}")
    
    # Create frames
    for frame_num in range(duration * fps):
        # Create blank frame
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add moving shapes
        time_sec = frame_num / fps
        
        # Moving circle
        circle_x = int(width * 0.5 + width * 0.3 * np.sin(time_sec * 2))
        circle_y = int(height * 0.5 + height * 0.2 * np.cos(time_sec * 1.5))
        cv2.circle(frame, (circle_x, circle_y), 30, (0, 255, 0), -1)
        
        # Moving rectangle
        rect_x = int(width * 0.3 + width * 0.2 * np.cos(time_sec * 1.8))
        rect_y = int(height * 0.7 + height * 0.15 * np.sin(time_sec * 2.2))
        cv2.rectangle(frame, (rect_x, rect_y), (rect_x + 60, rect_y + 40), (255, 0, 0), -1)
        
        # Moving triangle
        triangle_x = int(width * 0.7 + width * 0.15 * np.sin(time_sec * 1.2))
        triangle_y = int(height * 0.3 + height * 0.25 * np.cos(time_sec * 1.7))
        pts = np.array([[triangle_x, triangle_y], [triangle_x - 25, triangle_y + 40], [triangle_x + 25, triangle_y + 40]], np.int32)
        cv2.fillPoly(frame, [pts], (0, 0, 255))
        
        # Add frame number
        cv2.putText(frame, f"Frame: {frame_num}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, f"Time: {time_sec:.1f}s", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Write frame
        out.write(frame)
        
        # Progress indicator
        if frame_num % fps == 0:
            print(f"Progress: {frame_num // fps}/{duration}s")
    
    # Release video writer
    out.release()
    print(f"Sample video created: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / 1024:.1f} KB")


if __name__ == "__main__":
    create_sample_video() 