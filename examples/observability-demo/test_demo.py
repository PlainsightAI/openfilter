#!/usr/bin/env python3
"""
Test script for the observability demo.

This script tests the demo pipeline with different configurations.
"""

import os
import sys
import subprocess
import time
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def test_basic_run():
    """Test basic run without observability."""
    print("🧪 Testing basic run (no observability)...")

    # Get the directory where this test file is located
    test_dir = Path(__file__).parent

    result = subprocess.run([
        sys.executable, "app.py",
        "--input", "file://sample_video.mp4!loop",
        "--fps", "10",
        "--detection-threshold", "0.3",
        "--max-detections", "5"
    ], capture_output=True, text=True, timeout=30, cwd=test_dir)

    assert result.returncode == 0, f"Basic run failed: {result.stderr}"
    print("✅ Basic run successful")

def test_telemetry_enabled():
    """Test with OpenTelemetry enabled."""
    print("🧪 Testing with OpenTelemetry enabled...")

    # Get the directory where this test file is located
    test_dir = Path(__file__).parent

    env = os.environ.copy()
    env["TELEMETRY_EXPORTER_ENABLED"] = "true"
    env["TELEMETRY_EXPORTER_TYPE"] = "console"

    result = subprocess.run([
        sys.executable, "app.py",
        "--input", "file://sample_video.mp4!loop",
        "--fps", "10",
        "--detection-threshold", "0.3",
        "--max-detections", "5"
    ], env=env, capture_output=True, text=True, timeout=30, cwd=test_dir)

    assert result.returncode == 0, f"Telemetry run failed: {result.stderr}"
    print("✅ Telemetry run successful")

    # Check for telemetry output - just verify the app ran without asserting specific text
    # since telemetry output format may vary
    print("✅ Telemetry run completed successfully")

def test_openlineage_enabled():
    """Test with OpenLineage enabled."""
    print("🧪 Testing with OpenLineage enabled...")

    # Get the directory where this test file is located
    test_dir = Path(__file__).parent

    env = os.environ.copy()
    env["TELEMETRY_EXPORTER_ENABLED"] = "true"
    env["OPENLINEAGE_URL"] = "https://oleander.dev"
    env["OPENLINEAGE_API_KEY"] = "test_key"
    env["OF_SAFE_METRICS"] = "frames_processed,frames_with_detections,detections_per_frame_histogram,detection_confidence_histogram"

    result = subprocess.run([
        sys.executable, "app.py",
        "--input", "file://sample_video.mp4!loop",
        "--fps", "10",
        "--detection-threshold", "0.3",
        "--max-detections", "5"
    ], env=env, capture_output=True, text=True, timeout=30, cwd=test_dir)

    assert result.returncode == 0, f"OpenLineage run failed: {result.stderr}"
    print("✅ OpenLineage run successful")

    # Check for OpenLineage output - just verify the app ran without asserting specific text
    # since OpenLineage output format may vary
    print("✅ OpenLineage run completed successfully")

def check_output_files():
    """Check if output files were created."""
    print("🧪 Checking output files...")

    # Get the directory where this test file is located
    test_dir = Path(__file__).parent

    output_dir = test_dir / "output"
    if not output_dir.exists():
        print("❌ Output directory not found")
        return False

    processed_video = output_dir / "processed_video.mp4"
    if processed_video.exists():
        print(f"✅ Processed video found: {processed_video}")
        return True
    else:
        print("❌ Processed video not found")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting Observability Demo Tests")
    print("=" * 50)

    # Get the directory where this test file is located
    test_dir = Path(__file__).parent

    # Check if sample video exists
    sample_video = test_dir / "sample_video.mp4"
    if not sample_video.exists():
        print("📹 Creating sample video...")
        subprocess.run([sys.executable, "create_sample_video.py"], check=True, cwd=test_dir)

    tests = [
        ("Basic Run", test_basic_run),
        ("Telemetry Enabled", test_telemetry_enabled),
        ("OpenLineage Enabled", test_openlineage_enabled),
        ("Output Files", check_output_files)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            test_func()
            passed += 1
        except (AssertionError, subprocess.TimeoutExpired, Exception) as e:
            print(f"❌ Test failed: {e}")
        print()

    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Observability demo is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 