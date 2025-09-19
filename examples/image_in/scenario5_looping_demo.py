#!/usr/bin/env python3
"""
ImageIn Filter Demo - Scenario 5: Looping vs Non-Looping Comparison

This script demonstrates the difference between:
1. Non-looping: Process images once then stop
2. Infinite looping: Process images repeatedly forever
3. Finite looping: Process images N times then stop

Usage:
    python scenario5_looping_demo.py

The demo will run three phases:
1. Non-looping (3 images, processed once)
2. Finite looping (3 images, processed 2 times)  
3. Infinite looping (3 images, processed forever)

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

def create_demo_images():
    """Create 3 simple demo images."""
    test_dir = "loop_demo_images"
    
    # Remove directory if it exists and recreate it
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    os.makedirs(test_dir, exist_ok=True)
    
    # Create 3 distinct images
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # Red, Green, Blue
    names = ["RED", "GREEN", "BLUE"]
    
    for i in range(3):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        color = colors[i]
        name = names[i]
        
        # Draw colored content
        cv2.rectangle(img, (100, 100), (540, 300), color, -1)
        cv2.rectangle(img, (80, 80), (560, 320), (255, 255, 255), 5)
        
        # Add text
        cv2.putText(img, name, (250, 200), 
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
        cv2.putText(img, f"Image {i+1}/3", (250, 250), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(img, "Loop Demo", (250, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        image_path = os.path.join(test_dir, f"demo_image_{i+1}.jpg")
        cv2.imwrite(image_path, img)
        print(f"Created demo image: {image_path}")
    
    return test_dir

def run_demo_phase(phase_name, sources_config, expected_duration):
    """Run one phase of the demo."""
    print(f"\n{'='*60}")
    print(f"PHASE: {phase_name}")
    print(f"Configuration: {sources_config}")
    print(f"Expected duration: {expected_duration}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        # Start the pipeline for this phase
        Filter.run_multi([
            # ImageIn: With specific looping configuration
            (ImageIn, dict(
                sources=sources_config,
                outputs='tcp://*:5550',
                poll_interval=1.0,
            )),
            
            # Util: Add phase indicator
            (Util, dict(
                sources='tcp://127.0.0.1:5550',
                outputs='tcp://*:5552',
                xforms='resize 640x480',
            )),
            
            # Webvis: Display images
            (Webvis, dict(
                sources='tcp://127.0.0.1:5552',
                host='127.0.0.1',
                port=8000,
            )),
        ])
        
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\nPhase interrupted after {elapsed:.1f} seconds")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\nPhase completed after {elapsed:.1f} seconds")
        print(f"Reason: {e}")
        return True

def simulate_looping_demo(test_dir):
    """Run all three looping demo phases."""
    print("\n" + "="*80)
    print("SCENARIO 5: Looping vs Non-Looping Demonstration")
    print("="*80)
    print("This demo shows different looping behaviors:")
    print("1. Non-looping: Process 3 images once (3 images total)")
    print("2. Finite looping: Process 3 images 2 times (6 images total)")  
    print("3. Infinite looping: Process 3 images forever (until Ctrl+C)")
    print("\nEach image is shown for 1 second (1.0 FPS)")
    print("Open http://localhost:8000 to watch the demonstration")
    
    phases = [
        {
            "name": "NON-LOOPING",
            "config": f'file://{test_dir}!maxfps=1.0',  # No loop specified
            "duration": "~3 seconds (3 images × 1 sec each)"
        },
        {
            "name": "FINITE LOOPING (2 times)",
            "config": f'file://{test_dir}!maxfps=1.0!loop=2',  # Loop 2 times
            "duration": "~6 seconds (3 images × 2 loops × 1 sec each)"
        },
        {
            "name": "INFINITE LOOPING", 
            "config": f'file://{test_dir}!maxfps=1.0!loop',  # Infinite loop
            "duration": "Forever (until Ctrl+C) - 3 images repeating"
        }
    ]
    
    for i, phase in enumerate(phases):
        print(f"\n🔄 Starting Phase {i+1}/3...")
        time.sleep(2)  # Brief pause between phases
        
        completed = run_demo_phase(
            phase["name"], 
            phase["config"], 
            phase["duration"]
        )
        
        if not completed:  # User interrupted
            break
            
        if i < len(phases) - 1:  # Not the last phase
            print(f"\nPhase {i+1} completed! Starting next phase in 3 seconds...")
            time.sleep(3)
    
    print("\nDemo completed!")

def main():
    """Run the looping demonstration."""
    print("ImageIn Filter Demo - Scenario 5: Looping vs Non-Looping")
    print("="*60)
    
    # Create demo images
    test_dir = create_demo_images()
    
    print(f"\nCreated {test_dir}/ with 3 demo images")
    print("Demo will show three different looping behaviors:")
    print("• Phase 1: No looping (process once)")
    print("• Phase 2: Finite looping (process 2 times)")
    print("• Phase 3: Infinite looping (process forever)")
    
    input("\nPress Enter to start the demo (Ctrl+C to stop anytime)...")
    
    # Start demo
    simulate_looping_demo(test_dir)

if __name__ == '__main__':
    main()
