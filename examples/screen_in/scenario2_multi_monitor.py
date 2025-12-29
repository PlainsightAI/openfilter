#!/usr/bin/env python3
"""ScreenIn Filter - Scenario 2: Multi-Monitor Capture

This example demonstrates capturing from multiple monitors simultaneously.
Each monitor is assigned to a different topic, allowing independent processing
and display.

Usage:
    python scenario2_multi_monitor.py

Note: This example requires at least 2 monitors connected to your system.
If you only have one monitor, the second source will fail gracefully.

Then open:
- http://localhost:8000/monitor0 to view the first monitor
- http://localhost:8000/monitor1 to view the second monitor
"""

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.screen_in import ScreenIn
from openfilter.filter_runtime.filters.webvis import Webvis


def main():
    print("=" * 60)
    print("ScreenIn Filter - Multi-Monitor Demo")
    print("=" * 60)
    print()
    print("Capturing from two monitors:")
    print("  Monitor 0 (primary)   -> topic 'monitor0' at 10 FPS")
    print("  Monitor 1 (secondary) -> topic 'monitor1' at 10 FPS")
    print()
    print("Open your browser:")
    print("  http://localhost:8000/monitor0  (primary monitor)")
    print("  http://localhost:8000/monitor1  (secondary monitor)")
    print()
    print("Note: Requires 2 monitors connected to your system")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    try:
        Filter.run_multi([
            (ScreenIn, dict(
                # Capture two monitors with different topics
                sources='screen://0!maxfps=10;monitor0, screen://1!maxfps=10;monitor1',
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
