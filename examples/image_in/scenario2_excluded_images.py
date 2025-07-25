#!/usr/bin/env python3
"""
ImageIn Filter Demo - Scenario 2: Excluded Images with Dynamic Changes

This script demonstrates the ImageIn filter behavior when:
1. Pipeline starts with images in folder but they are excluded by pattern
2. Matching images are added, then removed, then added back
3. Shows how pipeline handles dynamic file changes

Usage:
    python scenario2_excluded_images.py

Then:
1. Open http://localhost:8000 in your browser
2. Watch as excluded images are ignored
3. See matching images appear, disappear, then reappear
4. Observe pipeline's ability to handle dynamic changes

Press Ctrl+C to stop the pipeline.
"""

import os
import time
import shutil
import threading
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

def create_matching_image(test_dir, image_num, phase=""):
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
    cv2.putText(img, "Scenario 2: Dynamic Changes", (50, 350), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(img, f"Phase: {phase}", (50, 400), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(img, f"Added at: {time.strftime('%H:%M:%S')}", (50, 450), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(img, "Pattern: *.jpg - WILL BE PROCESSED", (50, 500), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    # Save as JPG (matches pattern)
    image_path = os.path.join(test_dir, f"matching_image_{image_num}.jpg")
    cv2.imwrite(image_path, img)
    print(f"Created MATCHING image: {image_path} (Phase: {phase})")
    return image_path

def remove_matching_image(test_dir, image_num):
    """Remove a matching image from the test directory."""
    image_path = os.path.join(test_dir, f"matching_image_{image_num}.jpg")
    if os.path.exists(image_path):
        os.remove(image_path)
        print(f"Removed MATCHING image: {image_path}")
        return True
    return False

def image_dynamic_changes_thread(test_dir, stop_event):
    """Thread function to add, remove, and re-add matching images over time."""
    
    # Timeline: (action, time, image_num, description)
    timeline = [
        ("add", 8, 1, "First batch - Add image 1"),
        ("add", 12, 2, "First batch - Add image 2"),
        ("add", 16, 3, "First batch - Add image 3"),
        ("remove", 25, 1, "Remove image 1"),
        ("remove", 28, 2, "Remove image 2"),
        ("remove", 31, 3, "Remove image 3"),
        ("add", 40, 1, "Second batch - Re-add image 1"),
        ("add", 44, 2, "Second batch - Re-add image 2"),
        ("add", 48, 3, "Second batch - Re-add image 3"),
        ("remove", 55, 1, "Final remove - image 1"),
        ("add", 60, 4, "Final add - New image 4"),
    ]
    
    print("\nDynamic Timeline:")
    for action, delay, image_num, description in timeline:
        print(f"  {delay}s: {description}")
    
    try:
        for action, delay, image_num, description in timeline:
            if stop_event.is_set():
                break
            time.sleep(delay)
            if not stop_event.is_set():
                if action == "add":
                    create_matching_image(test_dir, image_num, f"Phase {action}")
                    print(f"\n[{time.strftime('%H:%M:%S')}] {description} - Pipeline should pick it up!")
                elif action == "remove":
                    if remove_matching_image(test_dir, image_num):
                        print(f"\n[{time.strftime('%H:%M:%S')}] {description} - Pipeline should stop showing it!")
                    else:
                        print(f"\n[{time.strftime('%H:%M:%S')}] {description} - Image not found to remove")
            
    except Exception as e:
        print(f"Error in image changes thread: {e}")

def simulate_pattern_matching_scenario(test_dir):
    """Simulate the pattern matching scenario with dynamic changes."""
    print("\n" + "="*80)
    print("SCENARIO 2: Excluded Images with Dynamic Changes")
    print("="*80)
    print("Pipeline is running with pattern '*.jpg' only")
    print("Current folder contains EXCLUDED images (.bmp, .png, .tiff)")
    print("Pipeline will remain idle until .jpg images are added")
    print("Then images will be removed and re-added to show dynamic behavior")
    print("Open http://localhost:8000 to see the dynamic changes.")
    
    # Create stop event for thread control
    stop_event = threading.Event()
    
    # Start image changes thread
    image_thread = threading.Thread(
        target=image_dynamic_changes_thread, 
        args=(test_dir, stop_event),
        daemon=True
    )
    image_thread.start()
    
    print("\nStarting pipeline with pattern='*.jpg'...")
    print("Note: Pipeline will be idle until .jpg files appear!")
    print("Then it will demonstrate dynamic add/remove behavior...")
    
    try:
        # Start the pipeline with pattern restriction
        Filter.run_multi([
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
        
    except KeyboardInterrupt:
        print("\nStopping pipeline...")
        stop_event.set()
        image_thread.join(timeout=2)
        print("Pipeline stopped.")

def main():
    """Run the excluded images scenario with dynamic changes."""
    print("ImageIn Filter Demo - Scenario 2: Excluded Images with Dynamic Changes")
    print("="*70)
    
    # Create test directory with excluded images
    test_dir = create_test_directory_with_excluded_images()
    
    print(f"\nCreated {test_dir}/ with 3 EXCLUDED images (.bmp, .png, .tiff)")
    print("Pipeline will use pattern='*.jpg' and ignore these files")
    print("Pipeline will remain idle until .jpg files are added...")
    print("Then it will demonstrate dynamic add/remove behavior...")
    
    # Start simulation
    simulate_pattern_matching_scenario(test_dir)

if __name__ == '__main__':
    main() 