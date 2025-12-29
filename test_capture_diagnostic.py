#!/usr/bin/env python3
"""Diagnostic test to see what ScreenGear is actually capturing"""

from vidgear.gears import ScreenGear
import cv2
import numpy as np

print("ScreenGear Capture Diagnostic Test")
print("=" * 60)

# Test with different configurations
configs = [
    ("Monitor 1 with MSS", {'monitor': 1, 'backend': 'mss'}),
    ("Monitor 1 with PIL", {'monitor': 1, 'backend': 'pil'}),
    ("Monitor 0 (all) with MSS", {'monitor': 0, 'backend': 'mss'}),
]

for name, config in configs:
    print(f"\nTesting: {name}")
    print(f"Config: {config}")

    try:
        stream = ScreenGear(**config)
        stream.start()

        frame = stream.read()

        if frame is None:
            print("  ❌ Frame is None")
        else:
            print(f"  ✓ Frame captured: {frame.shape}")
            print(f"  ✓ Data type: {frame.dtype}")

            # Check if frame is all black (would indicate capture failure)
            mean_value = np.mean(frame)
            max_value = np.max(frame)
            min_value = np.min(frame)

            print(f"  ✓ Pixel values - Mean: {mean_value:.1f}, Min: {min_value}, Max: {max_value}")

            if mean_value < 1.0:
                print("  ⚠️  WARNING: Frame appears to be completely black!")
            elif max_value == min_value:
                print("  ⚠️  WARNING: Frame has no variation (solid color)!")
            else:
                print("  ✓ Frame contains data (not blank)")

            # Save a sample
            filename = f"/tmp/screen_test_{name.replace(' ', '_')}.png"
            cv2.imwrite(filename, frame)
            print(f"  ✓ Saved sample to: {filename}")

        stream.stop()

    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 60)
print("Check the saved images in /tmp/ to see what's being captured")
print("=" * 60)
