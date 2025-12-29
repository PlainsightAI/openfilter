#!/usr/bin/env python3
"""ScreenIn Filter - Scenario 1: Region Capture

This example demonstrates capturing a specific region of the screen instead of
the full monitor. This is useful for monitoring specific applications or areas.

Usage:
    python scenario1_region_capture.py

The example captures a 800x600 region starting at coordinates (100, 100).
Adjust the x, y, width, height values to match your desired region.

Then open http://localhost:8000 to view the captured region.
"""

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.screen_in import ScreenIn
from openfilter.filter_runtime.filters.webvis import Webvis


def main():
    print("=" * 60)
    print("ScreenIn Filter - Region Capture Demo")
    print("=" * 60)
    print()
    print("Capturing region: x=100, y=100, width=800, height=600")
    print("Monitor: 0 (primary)")
    print("FPS: 15")
    print()
    print("Open http://localhost:8000 to view the captured region")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    try:
        Filter.run_multi([
            (ScreenIn, dict(
                # Capture specific region using query parameters
                sources='screen://0?x=100&y=100&w=800&h=600!maxfps=15',
                outputs='tcp://*:5550',
            )),
            (Webvis, dict(
                sources='tcp://127.0.0.1:5550',
                host='127.0.0.1',
                port=8000,
            )),
        ])
    except KeyboardInterrupt:
        print("\nStopping screen capture...")


if __name__ == '__main__':
    main()
