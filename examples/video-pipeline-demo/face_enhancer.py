#!/usr/bin/env python3
"""
Face Enhancer Filter

This filter takes face crops and enhances them by:
1. Resizing to 800x600 frame
2. Adding a random name
3. Adding timestamp
4. Adding a border and background
"""

import cv2
import numpy as np
import random
import time
from datetime import datetime
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.frame import Frame

class FaceEnhancer(Filter):
    """Filter to enhance face crops with larger frame, random name, and timestamp."""
        
    def setup(self, config):
        """Initialize the filter."""
        self.names = [
            "Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Prince", "Eve Wilson",
            "Frank Miller", "Grace Lee", "Henry Davis", "Ivy Chen", "Jack Wilson",
            "Kate Anderson", "Liam O'Connor", "Maya Patel", "Noah Kim", "Olivia Taylor",
            "Paul Rodriguez", "Quinn Murphy", "Rachel Green", "Sam Wilson", "Tina Turner"
        ]
        self.frame_count = 0
        self.emitter = None  # Initialize emitter attribute
        print("Face Enhancer: Initialized")
        
    def cleanup(self):
        """Cleanup the filter."""
        print("Face Enhancer: Cleaned up")
        
    def process(self, frames):
        """Process frames and enhance face crops."""
        output_frames = {}
        
        for topic, frame in frames.items():
            if not frame.has_image:
                # Forward non-image frames as-is
                output_frames[topic] = frame
                continue
                
            # Get the image - frame has image attribute directly
            img = frame.image
            
            # Create enhanced frame
            enhanced_img = self.enhance_face(img, topic)
            
            # Create new frame with enhanced image (BGR format)
            enhanced_frame = Frame(enhanced_img, {}, 'BGR')
            
            # Copy metadata from original frame
            if hasattr(frame, 'data') and 'meta' in frame.data:
                enhanced_frame.data['meta'] = frame.data['meta'].copy()
            else:
                enhanced_frame.data['meta'] = {}
            
            # Add enhancement metadata
            enhanced_frame.data['meta']['enhanced'] = True
            enhanced_frame.data['meta']['enhancement_time'] = datetime.now().isoformat()
            enhanced_frame.data['meta']['frame_count'] = self.frame_count
            
            output_frames[topic] = enhanced_frame
            self.frame_count += 1
            
        return output_frames
    
    def enhance_face(self, face_img, topic):
        """Enhance a face image by putting it in a larger frame with name and timestamp."""
        # Get random name
        random_name = random.choice(self.names)
        
        # Get current timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create 800x600 background (white)
        enhanced_img = np.ones((600, 800, 3), dtype=np.uint8) * 255
        
        # Resize face image to fit in the frame (with some padding)
        face_height, face_width = face_img.shape[:2]
        
        # Calculate scaling to fit face in the frame with padding
        max_face_width = 400
        max_face_height = 300
        
        scale = min(max_face_width / face_width, max_face_height / face_height)
        new_width = int(face_width * scale)
        new_height = int(face_height * scale)
        
        # Resize face image
        resized_face = cv2.resize(face_img, (new_width, new_height))
        
        # Calculate position to center the face
        start_x = (800 - new_width) // 2
        start_y = (600 - new_height) // 2 - 50  # Move up a bit to leave space for text
        
        # Place face in the center
        enhanced_img[start_y:start_y + new_height, start_x:start_x + new_width] = resized_face
        
        # Add border around the face
        cv2.rectangle(enhanced_img, 
                     (start_x - 5, start_y - 5), 
                     (start_x + new_width + 5, start_y + new_height + 5), 
                     (0, 0, 0), 2)
        
        # Add name at the top
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.2
        color = (0, 0, 0)
        thickness = 2
        
        # Get text size for centering
        (text_width, text_height), _ = cv2.getTextSize(random_name, font, font_scale, thickness)
        text_x = (800 - text_width) // 2
        text_y = 50
        
        # Add text background
        cv2.rectangle(enhanced_img, 
                     (text_x - 10, text_y - text_height - 10), 
                     (text_x + text_width + 10, text_y + 10), 
                     (255, 255, 255), -1)
        cv2.rectangle(enhanced_img, 
                     (text_x - 10, text_y - text_height - 10), 
                     (text_x + text_width + 10, text_y + 10), 
                     (0, 0, 0), 2)
        
        # Add name text
        cv2.putText(enhanced_img, random_name, (text_x, text_y), font, font_scale, color, thickness)
        
        # Add timestamp at the bottom
        timestamp_text = f"Captured: {timestamp}"
        (ts_width, ts_height), _ = cv2.getTextSize(timestamp_text, font, 0.8, 1)
        ts_x = (800 - ts_width) // 2
        ts_y = 550
        
        # Add timestamp background
        cv2.rectangle(enhanced_img, 
                     (ts_x - 10, ts_y - ts_height - 10), 
                     (ts_x + ts_width + 10, ts_y + 10), 
                     (240, 240, 240), -1)
        cv2.rectangle(enhanced_img, 
                     (ts_x - 10, ts_y - ts_height - 10), 
                     (ts_x + ts_width + 10, ts_y + 10), 
                     (0, 0, 0), 1)
        
        # Add timestamp text
        cv2.putText(enhanced_img, timestamp_text, (ts_x, ts_y), font, 0.8, (0, 0, 0), 1)
        
        # Add topic info
        topic_text = f"Topic: {topic}"
        cv2.putText(enhanced_img, topic_text, (20, 580), font, 0.6, (100, 100, 100), 1)
        
        return enhanced_img
