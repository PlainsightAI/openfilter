#!/usr/bin/env python3
"""
Test script for the video pipeline demo.

This script runs a quick test to verify that all filters can be imported
and configured correctly before running the full pipeline.
"""

import sys
import os
import logging

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all required modules can be imported."""
    try:
        from openfilter.filter_runtime.filter import Filter
        from openfilter.filter_runtime.filters.video_in import VideoIn
        from openfilter.filter_runtime.filters.webvis import Webvis
        from filter_frame_dedup.filter import FilterFrameDedup
        from filter_faceblur.filter import FilterFaceblur
        from filter_crop.filter import FilterCrop
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_video_files():
    """Test that video files exist."""
    video1 = "sample_video1.mp4"
    video2 = "sample_video2.mp4"
    
    if os.path.exists(video1):
        print(f"✓ {video1} found")
    else:
        print(f"✗ {video1} not found")
        return False
        
    if os.path.exists(video2):
        print(f"✓ {video2} found")
    else:
        print(f"✗ {video2} not found")
        return False
        
    return True

def test_filter_configs():
    """Test that filter configurations are valid."""
    try:
        from filter_frame_dedup.filter import FilterFrameDedupConfig
        from filter_faceblur.filter import FilterFaceblurConfig
        from filter_crop.filter import FilterCropConfig
        
        # Test FilterFrameDedup config
        dedup_config = FilterFrameDedupConfig(
            sources="tcp://localhost:5550",
            outputs="tcp://*:5552",
            hash_threshold=5,
            motion_threshold=1200,
            min_time_between_frames=1.0,
            ssim_threshold=0.90,
            output_folder="./output/deduped_frames",
            forward_deduped_frames=True,
            debug=False,
        )
        print("✓ FilterFrameDedup config valid")
        
        # Test FilterFaceblur config
        faceblur_config = FilterFaceblurConfig(
            sources="tcp://localhost:5552",
            outputs="tcp://*:5553",
            detector_name="yunet",
            blurrer_name="gaussian",
            blur_strength=2.0,
            detection_confidence_threshold=0.3,
            include_face_coordinates=True,
            forward_upstream_data=True,
            debug=False,
        )
        print("✓ FilterFaceblur config valid")
        
        # Test FilterCrop config
        crop_config = FilterCropConfig(
            sources="tcp://localhost:5553",
            outputs="tcp://*:5555",
            detection_key="face_coordinates",
            detection_class_field="class",
            detection_roi_field="bbox",
            output_prefix="face_crop_1_",
            mutate_original_frames=False,
            topic_mode="main_only",
        )
        print("✓ FilterCrop config valid")
        
        return True
    except Exception as e:
        print(f"✗ Config validation error: {e}")
        return False

def main():
    """Run all tests."""
    print("Testing Video Pipeline Demo...")
    print("=" * 40)
    
    tests = [
        ("Import Test", test_imports),
        ("Video Files Test", test_video_files),
        ("Filter Configs Test", test_filter_configs),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if test_func():
            passed += 1
        else:
            print(f"  {test_name} failed!")
    
    print("\n" + "=" * 40)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All tests passed! Pipeline is ready to run.")
        print("\nTo run the pipeline:")
        print("  python main.py")
        print("  # or")
        print("  make run")
        return 0
    else:
        print("✗ Some tests failed. Please fix the issues before running the pipeline.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
