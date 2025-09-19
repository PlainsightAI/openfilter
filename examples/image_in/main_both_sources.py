#!/usr/bin/env python3
"""
ImageIn Filter Demo with Both Local and GCS Sources

This script demonstrates the ImageIn filter with multiple sources:
1. Local images (created dynamically)
2. Google Cloud Storage images
3. Both sources processed in the same pipeline with different topics

Usage:
    python main_both_sources.py [gcs_path]
    
    Examples:
        python main_both_sources.py
        python main_both_sources.py gs://my-bucket/images
        python main_both_sources.py gs://protege-artifacts-development/labelled-data/demo_ocr/data

Then open http://127.0.0.1:8000 in your browser to see images from both sources.
"""

import os, cv2
import numpy as np
import sys
import argparse
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn
from openfilter.filter_runtime.filters.util import Util
from openfilter.filter_runtime.filters.webvis import Webvis

def create_sample_images():
    """Create sample images for local testing with more images to see FPS effect."""
    # Create test directory
    test_dir = "test_images"
    os.makedirs(test_dir, exist_ok=True)
    
    # Create 6 test images to make FPS effect more visible
    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]
    formats = ['jpg', 'png', 'bmp']
    
    for i in range(6):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Draw different shapes and text for each image - LOCAL theme
        color = colors[i]
        text = f"LOCAL {i+1}/6"
        
        cv2.rectangle(img, (50 + (i%3)*50, 50 + (i//3)*100), (200 + (i%3)*50, 150 + (i//3)*100), color, 3)
        cv2.circle(img, (400, 200 + i*20), 60, color, -1)
        cv2.putText(img, text, (50, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(img, "LOCAL SOURCE", (50, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(img, f"FPS: FAST (1.0)", (50, 400), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f"Topic: local", (50, 430), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Save the image in different formats
        format_ext = formats[i % len(formats)]
        image_path = os.path.join(test_dir, f"local_sample_{i+1:02d}.{format_ext}")
        cv2.imwrite(image_path, img)
        print(f"Created local sample image: {image_path}")
    
    return test_dir

def main():
    """Run the ImageIn filter demo with both local and GCS sources."""
    parser = argparse.ArgumentParser(description='ImageIn Filter Demo with Both Local and GCS Sources')
    parser.add_argument('gcs_path', nargs='?', 
                       default="gs://protege-artifacts-development/labelled-data/demo_ocr/data",
                       help='GCS path to images (default: demo OCR data)')
    
    args = parser.parse_args()
    
    print("ImageIn Filter Demo with Both Local and GCS Sources")
    print("="*55)
    
    # Create local sample images
    test_dir = create_sample_images()
    
    print(f"\nConfigured sources:")
    print(f"• LOCAL: {test_dir}/ (topic: local) - 1.0 FPS (1 image per second)")
    print(f"• GCS: {args.gcs_path} (topic: cloud) - 0.5 FPS (1 image every 2 seconds)")
    print("\nYou should see:")
    print("• Local images appearing every 1 second")
    print("• Cloud images appearing every 2 seconds")
    print("• Mixed stream showing both sources at different rates")
    print("\nOpen http://127.0.0.1:8000 to see images from both sources")
    print("Press Ctrl+C to stop the pipeline")
    
    # Run the pipeline
    Filter.run_multi([
        # ImageIn: Read images from BOTH local and GCS sources with different topics
        (ImageIn, dict(
            sources=[
                f'file://{test_dir}!loop!maxfps=2.0;local', 
                f'{args.gcs_path}!loop!maxfps=1.0;cloud'
            ],
            outputs='tcp://*:5550',
            poll_interval=3.0,  # Check for new images every 3 seconds
        )),
        
        # Util: Apply transformations - add different colored borders for each topic
        (Util, dict(
            sources='tcp://127.0.0.1:5550',
            outputs='tcp://*:5552',
            xforms='resize 640x480',  # Just resize, images already have identifying text
        )),
        
        # Webvis: Display mixed images from both sources
        (Webvis, dict(
            sources='tcp://127.0.0.1:5552',
            host='127.0.0.1',
            port=8000,
        )),
    ])

if __name__ == '__main__':
    main() 