#!/usr/bin/env python3
"""
ImageIn Filter Demo

This script demonstrates the ImageIn filter by:
1. Creating sample images in a test directory
2. Setting up a pipeline: ImageIn -> Util -> Webvis
3. Running the pipeline to display images in a web browser

Usage:
    python main.py

Then open http://localhost:8000 in your browser to see the images.
"""

import os, cv2
import numpy as np
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn
from openfilter.filter_runtime.filters.util import Util
from openfilter.filter_runtime.filters.webvis import Webvis

def create_sample_images():
    """Create sample images for testing."""
    # Create test directory
    test_dir = "test_images"
    os.makedirs(test_dir, exist_ok=True)
    
    # Create multiple test images in different formats
    formats = ['jpg', 'png', 'bmp']
    for i in range(3):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Draw different shapes and text for each image
        color = [(0, 255, 0), (255, 0, 0), (0, 0, 255)][i]
        text = f"Image {i+1}"
        
        cv2.rectangle(img, (50 + i*50, 50), (200 + i*50, 150), color, 3)
        cv2.circle(img, (400, 200 + i*30), 80, color, -1)
        cv2.putText(img, text, (50, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(img, "OpenFilter ImageIn Demo", (50, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # Save the image in different formats
        format_ext = formats[i % len(formats)]
        image_path = os.path.join(test_dir, f"sample_image_{i+1}.{format_ext}")
        cv2.imwrite(image_path, img)
        print(f"Created sample image: {image_path}")
    
    return test_dir

def main():
    """Run the ImageIn filter demo."""
    print("ImageIn Filter Demo")
    print("==================")
    
    # Create sample images
    test_dir = create_sample_images()
    
    print(f"\nStarting pipeline with images from: {test_dir}")
    print("Open http://localhost:8000 in your browser to view the images")
    print("Press Ctrl+C to stop the pipeline")
    
    # Run the pipeline
    Filter.run_multi([
        # ImageIn: Read images from the test directory with looping
        (ImageIn, dict(
            sources=f'file://{test_dir}!loop!maxfps=2',
            outputs='tcp://*:5550',
            loop=True,  # Infinite loop
            poll_interval=2.0,  # Check for new images every 2 seconds
        )),
        
        # Util: Apply some transformations to the images
        (Util, dict(
            sources='tcp://127.0.0.1:5550',
            outputs='tcp://*:5552',
            xforms='resize 640x480, box 0.1+0.1x0.3x0.2#ff0000',  # Resize and add red box
        )),
        
        # Webvis: Display images in web browser
        (Webvis, dict(
            sources='tcp://127.0.0.1:5552',
            host='127.0.0.1',
            port=8000,
        )),
    ])

if __name__ == '__main__':
    main()
