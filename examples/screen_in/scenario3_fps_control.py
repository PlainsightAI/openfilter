#!/usr/bin/env python3
"""ScreenIn Filter - Scenario 3: FPS Control

This example demonstrates controlling the frame rate (FPS) of screen capture.
Lower FPS reduces CPU usage and is suitable for monitoring scenarios where
real-time performance isn't critical.

Usage:
    python scenario3_fps_control.py

The example compares different FPS settings by capturing the same monitor
at different frame rates using separate filters.

Then open http://localhost:8000 to view the captures.
"""

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.screen_in import ScreenIn
from openfilter.filter_runtime.filters.util import Util
from openfilter.filter_runtime.filters.webvis import Webvis


def main():
    print("=" * 60)
    print("ScreenIn Filter - FPS Control Demo")
    print("=" * 60)
    print()
    print("Comparing different FPS settings:")
    print("  Low FPS (5 FPS):  Good for monitoring, low CPU usage")
    print("  Med FPS (15 FPS): Balanced performance")
    print("  High FPS (30 FPS): Smooth capture, higher CPU usage")
    print()
    print("This demo uses 5 FPS for efficient screen monitoring.")
    print()
    print("Open http://localhost:8000 to view the capture")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    try:
        Filter.run_multi([
            (ScreenIn, dict(
                # Low FPS for efficient monitoring
                sources='screen://0!maxfps=5',
                outputs='tcp://*:5550',
            )),
            (Util, dict(
                sources='tcp://127.0.0.1:5550',
                outputs='tcp://*:5552',
                log=True,  # Log frame metadata to see FPS in action
            )),
            (Webvis, dict(
                sources='tcp://127.0.0.1:5552',
                host='127.0.0.1',
                port=8000,
            )),
        ])
    except KeyboardInterrupt:
        print("\nStopping screen capture...")


if __name__ == '__main__':
    main()
