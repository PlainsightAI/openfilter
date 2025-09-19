#!/usr/bin/env python3
"""
ImageIn Filter Demo - Scenario 1: Empty Start

This script demonstrates the ImageIn filter behavior when:
1. Pipeline starts with an empty folder
2. Remains idle until images are added
3. Automatically picks up new images when they appear

Usage:
    python scenario1_empty_start.py

Then:
1. Open http://localhost:8000 in your browser
2. Add images to test_images/ folder while pipeline is running
3. Watch as images appear automatically

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

def create_test_directory():
    """Create an empty test directory."""
    test_dir = "test_images"
    
    # Remove directory if it exists and recreate it empty
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    os.makedirs(test_dir, exist_ok=True)
    print(f"Created empty test directory: {test_dir}")
    return test_dir

def create_sample_image(test_dir, image_num):
    """Create a sample image and save it to the test directory."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Draw different shapes and text for each image
    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
    color = colors[image_num % len(colors)]
    text = f"Dynamic Image {image_num}"
    
    cv2.rectangle(img, (50 + image_num*20, 50), (200 + image_num*20, 150), color, 3)
    cv2.circle(img, (400, 200 + image_num*30), 80, color, -1)
    cv2.putText(img, text, (50, 300), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(img, "Scenario 1: Empty Start", (50, 350), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(img, f"Added at: {time.strftime('%H:%M:%S')}", (50, 400), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    # Save the image
    image_path = os.path.join(test_dir, f"dynamic_image_{image_num}.jpg")
    cv2.imwrite(image_path, img)
    print(f"Created image: {image_path}")
    return image_path

def image_addition_thread(test_dir, stop_event):
    """Thread function to add images over time."""
    # Add images at different times
    image_times = [5, 15, 25, 35, 45]  # seconds after start
    
    print("\nTimeline for image addition:")
    for i, delay in enumerate(image_times):
        print(f"  {delay}s: Will add image {i+1}")
    
    try:
        for i, delay in enumerate(image_times):
            if stop_event.is_set():
                break
            time.sleep(delay)
            if not stop_event.is_set():
                create_sample_image(test_dir, i+1)
                print(f"\n[{time.strftime('%H:%M:%S')}] Added image {i+1} - Pipeline should pick it up automatically!")
            
    except Exception as e:
        print(f"Error in image addition thread: {e}")

def simulate_image_addition(test_dir):
    """Simulate adding images to the folder over time."""
    print("\n" + "="*60)
    print("SCENARIO 1: Empty Start Simulation")
    print("="*60)
    print("Pipeline is running with empty folder...")
    print("Images will be added automatically to simulate real-world scenario.")
    print("Open http://localhost:8000 to see the images appear.")
    
    # Create stop event for thread control
    stop_event = threading.Event()
    
    # Start image addition thread
    image_thread = threading.Thread(
        target=image_addition_thread, 
        args=(test_dir, stop_event),
        daemon=True
    )
    image_thread.start()
    
    print("\nStarting pipeline...")
    
    try:
        # Start the pipeline
        Filter.run_multi([
            # ImageIn: Read images from the test directory
            (ImageIn, dict(
                sources=f'file://{test_dir}!loop!maxfps=0.5',  # 1 image every 2 seconds
                outputs='tcp://*:5550',
                loop=True,  # Infinite loop
                poll_interval=1.0,  # Check for new images every 1 second
            )),
            
            # Util: Apply some transformations to the images
            (Util, dict(
                sources='tcp://127.0.0.1:5550',
                outputs='tcp://*:5552',
                xforms='resize 640x480, box 0.1+0.1x0.3x0.2#00ff00',  # Resize and add green box
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
    """Run the empty start scenario."""
    print("ImageIn Filter Demo - Scenario 1: Empty Start")
    print("="*50)
    
    # Create empty test directory
    test_dir = create_test_directory()
    
    # Start simulation
    simulate_image_addition(test_dir)

if __name__ == '__main__':
    main() 