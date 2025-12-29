#!/usr/bin/env python3
"""ScreenIn Filter Demo - Basic screen capture to web browser

This example demonstrates the basic usage of the ScreenIn filter to capture
the primary monitor and display it in a web browser.

Usage:
    python main.py

Then open http://localhost:8000 in your browser to view the screen capture.
Press Ctrl+C to stop.
"""

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.screen_in import ScreenIn
from openfilter.filter_runtime.filters.webvis import Webvis


def main():
    print("=" * 60)
    print("ScreenIn Filter - Basic Demo")
    print("=" * 60)
    print()
    print("Capturing primary monitor at 10 FPS")
    print("Open one of these URLs to view the screen capture:")
    print("  - Local:   http://localhost:8000")
    print("  - Network: http://192.168.80.95:8000")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    try:
        Filter.run_multi([
            (ScreenIn, dict(
                sources='screen://-1!maxfps=10!backend=pil',  # Try PIL backend for macOS
                outputs='tcp://*:5550',
            )),
            (Webvis, dict(
                sources='tcp://127.0.0.1:5550',
                host='0.0.0.0',  # Accept connections from any network interface
                port=8000,
            )),
        ])
    except KeyboardInterrupt:
        print("\nStopping screen capture...")


if __name__ == '__main__':
    main()
