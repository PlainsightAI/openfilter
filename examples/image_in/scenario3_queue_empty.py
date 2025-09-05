#!/usr/bin/env python3
"""
ImageIn Filter Demo - Scenario 3: Queue Empty Behavior

This script demonstrates the ImageIn filter behavior when:
1. Pipeline processes all available images
2. Queue becomes empty (no more images)
3. Shows what happens - does it crash? Does it wait?
4. Then adds more images to show recovery

Usage:
    python scenario3_queue_empty.py

Then:
1. Open http://localhost:8000 in your browser
2. Watch pipeline process initial images
3. See pipeline go idle when queue is empty
4. Watch recovery when new images are added

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

def create_test_directory_with_initial_images():
    """Create test directory with a few initial images."""
    test_dir = "test_images"
    
    # Remove directory if it exists and recreate it
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    os.makedirs(test_dir, exist_ok=True)
    print(f"Created test directory: {test_dir}")
    
    # Create 3 initial images
    for i in range(3):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Draw initial image content
        colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255)]
        color = colors[i]
        text = f"Initial Image {i+1}"
        
        cv2.rectangle(img, (50 + i*30, 50), (200 + i*30, 150), color, 3)
        cv2.circle(img, (400, 200 + i*40), 60, color, -1)
        cv2.putText(img, text, (50, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(img, "Scenario 3: Queue Empty", (50, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(img, "Pre-loaded images", (50, 400), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Save the image
        image_path = os.path.join(test_dir, f"initial_image_{i+1}.jpg")
        cv2.imwrite(image_path, img)
        print(f"Created initial image: {image_path}")
    
    return test_dir

def create_recovery_image(test_dir, image_num, phase="Recovery"):
    """Create a recovery image to show pipeline recovery."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Draw recovery image content
    colors = [(255, 255, 0), (255, 0, 255), (0, 255, 255)]
    color = colors[image_num % len(colors)]
    text = f"Recovery Image {image_num}"
    
    cv2.rectangle(img, (50 + image_num*20, 50), (250 + image_num*20, 150), color, 3)
    cv2.circle(img, (400, 250 + image_num*30), 80, color, -1)
    cv2.putText(img, text, (50, 300), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(img, f"Phase: {phase}", (50, 350), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(img, f"Added at: {time.strftime('%H:%M:%S')}", (50, 400), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(img, "Pipeline RECOVERY!", (50, 450), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    # Save the image
    image_path = os.path.join(test_dir, f"recovery_image_{image_num}.jpg")
    cv2.imwrite(image_path, img)
    print(f"Created recovery image: {image_path}")
    return image_path

def queue_empty_demonstration_thread(test_dir, stop_event):
    """Thread function to demonstrate queue empty behavior."""
    
    print("\n" + "="*60)
    print("QUEUE EMPTY DEMONSTRATION TIMELINE:")
    print("="*60)
    print("Initial: 3 images will be processed (takes ~6 seconds at 0.5 FPS)")
    print("10s: Queue becomes EMPTY - what happens?")
    print("20s: Add recovery image 1 - pipeline should resume")
    print("30s: Add recovery image 2 - continue processing")
    print("40s: Add recovery image 3 - show sustained operation")
    print("="*60)
    
    try:
        # Wait for initial processing to complete
        print(f"\n[{time.strftime('%H:%M:%S')}] Waiting for initial images to process...")
        time.sleep(10)  # Initial 3 images at 0.5 FPS = 6 seconds + buffer
        
        print(f"\n[{time.strftime('%H:%M:%S')}] *** QUEUE SHOULD BE EMPTY NOW ***")
        print("Pipeline status: IDLE but ALIVE (not crashed)")
        print("Waiting 10 seconds to demonstrate empty queue behavior...")
        time.sleep(10)
        
        # Add recovery images
        recovery_times = [20, 30, 40]  # Total elapsed time
        for i, total_time in enumerate(recovery_times):
            if stop_event.is_set():
                break
            
            # We've already waited 20 seconds, so adjust sleep time
            if i == 0:
                sleep_time = 0  # We already waited 20 seconds total
            else:
                sleep_time = 10  # 10 seconds between recovery images
            
            if sleep_time > 0:
                time.sleep(sleep_time)
            
            if not stop_event.is_set():
                create_recovery_image(test_dir, i+1, "Recovery")
                print(f"\n[{time.strftime('%H:%M:%S')}] *** ADDED RECOVERY IMAGE {i+1} ***")
                print("Pipeline should AUTOMATICALLY resume processing!")
                
    except Exception as e:
        print(f"Error in demonstration thread: {e}")

def simulate_queue_empty_scenario(test_dir):
    """Simulate the queue empty scenario."""
    print("\n" + "="*80)
    print("SCENARIO 3: Queue Empty Behavior Demonstration")
    print("="*80)
    print("This demonstrates what happens when ImageIn runs out of images:")
    print("1. Pipeline starts with 3 pre-loaded images")
    print("2. Processes them at 0.5 FPS (1 image every 2 seconds)")
    print("3. Queue becomes EMPTY after ~6 seconds")
    print("4. Shows pipeline remains ALIVE and responsive")
    print("5. Demonstrates automatic recovery when new images appear")
    print("\nOpen http://localhost:8000 to watch the demonstration")
    
    # Create stop event for thread control
    stop_event = threading.Event()
    
    # Start demonstration thread
    demo_thread = threading.Thread(
        target=queue_empty_demonstration_thread, 
        args=(test_dir, stop_event),
        daemon=True
    )
    demo_thread.start()
    
    print("\nStarting pipeline...")
    print("*** Watch the console for timing annotations ***")
    
    try:
        # Start the pipeline with NO LOOPING
        Filter.run_multi([
            # ImageIn: Read images with NO looping
            (ImageIn, dict(
                sources=f'file://{test_dir}!maxfps=2',  # No loop - process once only
                outputs='tcp://*:5550',
                loop=False,  # KEY: No looping - process each image once
                poll_interval=1.0,  # Check for new images every 1 second
            )),
            
            # Util: Apply some transformations to the images
            (Util, dict(
                sources='tcp://127.0.0.1:5550',
                outputs='tcp://*:5552',
                xforms='resize 640x480, box 0.1+0.1x0.3x0.2#ffff00',  # Resize and add yellow box
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
        demo_thread.join(timeout=2)
        print("Pipeline stopped.")

def main():
    """Run the queue empty scenario."""
    print("ImageIn Filter Demo - Scenario 3: Queue Empty Behavior")
    print("="*60)
    
    # Create test directory with initial images
    test_dir = create_test_directory_with_initial_images()
    
    print(f"\nCreated {test_dir}/ with 3 initial images")
    print("Pipeline will process these, then queue becomes empty")
    print("Key question: What happens when there are no more images?")
    print("Answer: Pipeline stays ALIVE and automatically resumes when new images appear!")
    
    # Start simulation
    simulate_queue_empty_scenario(test_dir)

if __name__ == '__main__':
    main()
