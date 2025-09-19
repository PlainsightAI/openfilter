#!/usr/bin/env python3
"""
ImageIn Filter Demo - Scenario 4: Multiple Topics with Different FPS

This script demonstrates the ImageIn filter behavior with:
1. Multiple sources assigned to different topics
2. Each topic has independent FPS settings
3. Shows how different streams process at different rates
4. Demonstrates mixed-rate output

Usage:
    python scenario4_multi_fps.py

Then:
1. Open http://localhost:8000 in your browser
2. Watch FAST stream (green box) - 2 FPS
3. Watch SLOW stream (red box) - 0.5 FPS
4. See how they mix in the output

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

def create_fast_images(fast_dir):
    """Create images for the fast stream."""
    os.makedirs(fast_dir, exist_ok=True)
    
    for i in range(8):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Fast stream - green theme
        color = (0, 255, 0)  # Green
        text = f"FAST #{i+1}"
        
        cv2.rectangle(img, (50, 50), (300, 200), color, 3)
        cv2.circle(img, (400, 300), 80, color, -1)
        cv2.putText(img, text, (50, 250), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        cv2.putText(img, "FAST STREAM: 2.0 FPS", (50, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(img, "Topic: fast", (50, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(img, "1 image every 0.5 seconds", (50, 400), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        image_path = os.path.join(fast_dir, f"fast_image_{i+1}.jpg")
        cv2.imwrite(image_path, img)
        print(f"Created fast image: {image_path}")

def create_slow_images(slow_dir):
    """Create images for the slow stream."""
    os.makedirs(slow_dir, exist_ok=True)
    
    for i in range(4):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Slow stream - red theme
        color = (0, 0, 255)  # Red
        text = f"SLOW #{i+1}"
        
        cv2.rectangle(img, (50, 50), (300, 200), color, 3)
        cv2.circle(img, (400, 300), 80, color, -1)
        cv2.putText(img, text, (50, 250), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        cv2.putText(img, "SLOW STREAM: 1.0 FPS", (50, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(img, "Topic: slow", (50, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(img, "1 image every 1 second", (50, 400), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        image_path = os.path.join(slow_dir, f"slow_image_{i+1}.jpg")
        cv2.imwrite(image_path, img)
        print(f"Created slow image: {image_path}")

def create_test_directories():
    """Create separate directories for fast and slow streams."""
    # Clean up and create directories
    for dir_name in ["fast_images", "slow_images"]:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
    
    fast_dir = "fast_images"
    slow_dir = "slow_images"
    
    create_fast_images(fast_dir)
    create_slow_images(slow_dir)
    
    return fast_dir, slow_dir

def timing_explanation_thread(stop_event):
    """Thread to explain timing as demo runs."""
    
    print("\n" + "="*80)
    print("MULTI-FPS TIMING EXPLANATION:")
    print("="*80)
    print("FAST stream (green): 2.0 FPS = 1 image every 0.5 seconds")
    print("SLOW stream (red):   1.0 FPS = 1 image every 1.0 second")
    print("="*80)
    print("Expected pattern:")
    print("0.0s: FAST #1")
    print("0.5s: FAST #2")  
    print("1.0s: FAST #3 + SLOW #1")  # Both streams coincide
    print("1.5s: FAST #4")
    print("2.0s: FAST #5 + SLOW #2")  # Both streams coincide
    print("2.5s: FAST #6")
    print("3.0s: FAST #7 + SLOW #3")  # Both streams coincide
    print("3.5s: FAST #8")
    print("4.0s: SLOW #4")  # Fast stream finished, only slow continues
    print("="*80)
    
    timeline = [
        (1, "Both FAST and SLOW should appear together"),
        (2, "Both FAST and SLOW should appear together again"),
        (3, "Both FAST and SLOW should appear together again"),
        (4, "FAST stream finished, only SLOW continues"),
        (5, "Both streams finished - demonstrating independent FPS control")
    ]
    
    for delay, message in timeline:
        if stop_event.is_set():
            break
        time.sleep(delay)
        if not stop_event.is_set():
            print(f"\n[{time.strftime('%H:%M:%S')}] {message}")

def simulate_multi_fps_scenario(fast_dir, slow_dir):
    """Simulate the multi-FPS scenario."""
    print("\n" + "="*80)
    print("SCENARIO 4: Multiple Topics with Different FPS")
    print("="*80)
    print("This demonstrates independent FPS control per topic:")
    print("• FAST topic: 8 images at 2.0 FPS (green boxes)")
    print("• SLOW topic: 4 images at 0.5 FPS (red boxes)")
    print("• Each topic processes independently")
    print("• Output shows mixed stream from both topics")
    print("\nOpen http://localhost:8000 to watch both streams")
    
    # Create stop event for thread control
    stop_event = threading.Event()
    
    # Start timing explanation thread
    timing_thread = threading.Thread(
        target=timing_explanation_thread, 
        args=(stop_event,),
        daemon=True
    )
    timing_thread.start()
    
    print("\nStarting multi-FPS pipeline...")
    print("*** Watch console for timing explanations ***")
    
    try:
        # Start the pipeline with multiple topics and different FPS
        Filter.run_multi([
            # ImageIn: Multiple sources with different FPS settings
            (ImageIn, dict(
                sources=f'file://{fast_dir}!maxfps=2.0!loop;fast, file://{slow_dir}!maxfps=1.0!loop;slow',
                outputs='tcp://*:5550',
                poll_interval=1.0,
            )),
            
            # Util: Add different colored boxes to distinguish streams
            (Util, dict(
                sources='tcp://127.0.0.1:5550',
                outputs='tcp://*:5552',
                xforms='resize 640x480',  # Just resize, images already have colored content
            )),
            
            # Webvis: Display mixed stream
            (Webvis, dict(
                sources='tcp://127.0.0.1:5552',
                host='127.0.0.1',
                port=8000,
            )),
        ])
        
    except KeyboardInterrupt:
        print("\nStopping pipeline...")
        stop_event.set()
        timing_thread.join(timeout=2)
        print("Pipeline stopped.")

def main():
    """Run the multi-FPS scenario."""
    print("ImageIn Filter Demo - Scenario 4: Multiple Topics with Different FPS")
    print("="*70)
    
    # Create test directories with images
    fast_dir, slow_dir = create_test_directories()
    
    print(f"\nCreated:")
    print(f"• {fast_dir}/ with 8 images (FAST stream)")
    print(f"• {slow_dir}/ with 4 images (SLOW stream)")
    print("\nKey demonstration points:")
    print("• Each topic has independent FPS control")
    print("• Topics can finish at different times")
    print("• Output is mixed stream from all active topics")
    print("• No topic blocks another topic")
    
    # Start simulation
    simulate_multi_fps_scenario(fast_dir, slow_dir)

if __name__ == '__main__':
    main()
