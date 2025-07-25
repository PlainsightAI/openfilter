#!/usr/bin/env python3
"""
ImageIn Filter Demo - Scenario 2: Excluded Images

This script demonstrates the ImageIn filter behavior when:
1. Pipeline starts with images in folder but they are excluded by pattern
2. Remains idle until matching images are added
3. Automatically picks up new images when they appear

Usage:
    python scenario2_excluded_images.py

Then:
1. Open http://localhost:8000 in your browser
2. Watch as excluded images are ignored and new matching images are picked up
3. See the pipeline resume when matching images appear

Press Ctrl+C to stop the pipeline.
"""

import os
import time
import shutil
import cv2
import numpy as np
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn
from openfilter.filter_runtime.filters.util import Util
from openfilter.filter_runtime.filters.webvis import Webvis

def create_test_directory_with_excluded_images():
    """Create test directory with images that will be excluded by pattern."""
    test_dir = "test_images"
    
    # Remove directory if it exists and recreate it
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    os.makedirs(test_dir, exist_ok=True)
    print(f"Created test directory: {test_dir}")
    
    # Create images that will be EXCLUDED (don't match the pattern)
    excluded_formats = ['bmp', 'png', 'tiff']
    for i in range(3):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Draw excluded image content
        color = [(255, 0, 0), (0, 255, 0), (0, 0, 255)][i]
        text = f"EXCLUDED Image {i+1}"
        
        cv2.rectangle(img, (50, 50), (200, 150), color, 3)
        cv2.circle(img, (400, 200), 80, color, -1)
        cv2.putText(img, text, (50, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(img, "This image will be IGNORED", (50, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(img, "Pattern: *.jpg only", (50, 400), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Save in excluded format
        format_ext = excluded_formats[i % len(excluded_formats)]
        image_path = os.path.join(test_dir, f"excluded_image_{i+1}.{format_ext}")
        cv2.imwrite(image_path, img)
        print(f"Created EXCLUDED image: {image_path}")
    
    return test_dir

def create_matching_image(test_dir, image_num):
    """Create a sample image that matches the pattern (*.jpg)."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Draw different shapes and text for each image
    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
    color = colors[image_num % len(colors)]
    text = f"MATCHING Image {image_num}"
    
    cv2.rectangle(img, (50 + image_num*20, 50), (200 + image_num*20, 150), color, 3)
    cv2.circle(img, (400, 200 + image_num*30), 80, color, -1)
    cv2.putText(img, text, (50, 300), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(img, "Scenario 2: Pattern Matching", (50, 350), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(img, f"Added at: {time.strftime('%H:%M:%S')}", (50, 400), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(img, "Pattern: *.jpg - WILL BE PROCESSED", (50, 450), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    # Save as JPG (matches pattern)
    image_path = os.path.join(test_dir, f"matching_image_{image_num}.jpg")
    cv2.imwrite(image_path, img)
    print(f"Created MATCHING image: {image_path}")
    return image_path

def simulate_pattern_matching_scenario(test_dir):
    """Simulate the pattern matching scenario."""
    print("\n" + "="*70)
    print("SCENARIO 2: Excluded Images Simulation")
    print("="*70)
    print("Pipeline is running with pattern '*.jpg' only")
    print("Current folder contains EXCLUDED images (.bmp, .png, .tiff)")
    print("Pipeline will remain idle until .jpg images are added")
    print("Open http://localhost:8000 to see the matching images appear.")
    print("\nTimeline:")
    
    # Add matching images at different times
    image_times = [8, 18, 28, 38, 48]  # seconds after start
    
    for i, delay in enumerate(image_times):
        print(f"  {delay}s: Will add matching image {i+1} (.jpg)")
    
    print("\nStarting pipeline with pattern='*.jpg'...")
    print("Note: Pipeline will be idle until .jpg files appear!")
    
    # Start the pipeline with pattern restriction
    pipeline_process = Filter.run_multi([
        # ImageIn: Read images from the test directory with pattern restriction
        (ImageIn, dict(
            sources=f'file://{test_dir}!loop!pattern=*.jpg!maxfps=0.5',  # Only .jpg files, 1 image every 2 seconds
            outputs='tcp://*:5550',
            loop=True,  # Infinite loop
            poll_interval=1.0,  # Check for new images every 1 second
        )),
        
        # Util: Apply some transformations to the images
        (Util, dict(
            sources='tcp://127.0.0.1:5550',
            outputs='tcp://*:5552',
            xforms='resize 640x480, box 0.1+0.1x0.3x0.2#ff00ff',  # Resize and add magenta box
        )),
        
        # Webvis: Display images in web browser
        (Webvis, dict(
            sources='tcp://127.0.0.1:5552',
            host='127.0.0.1',
            port=8000,
        )),
    ])
    
    # Simulate adding matching images over time
    try:
        for i, delay in enumerate(image_times):
            time.sleep(delay)
            create_matching_image(test_dir, i+1)
            print(f"\n[{time.strftime('%H:%M:%S')}] Added matching image {i+1} (.jpg) - Pipeline should pick it up!")
            
    except KeyboardInterrupt:
        print("\nStopping pipeline...")
        return pipeline_process

def main():
    """Run the excluded images scenario."""
    print("ImageIn Filter Demo - Scenario 2: Excluded Images")
    print("="*55)
    
    # Create test directory with excluded images
    test_dir = create_test_directory_with_excluded_images()
    
    print(f"\nCreated {test_dir}/ with 3 EXCLUDED images (.bmp, .png, .tiff)")
    print("Pipeline will use pattern='*.jpg' and ignore these files")
    print("Pipeline will remain idle until .jpg files are added...")
    
    # Start simulation
    simulate_pattern_matching_scenario(test_dir)

if __name__ == '__main__':
    main() 