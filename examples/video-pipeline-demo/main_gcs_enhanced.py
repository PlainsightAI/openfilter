#!/usr/bin/env python3
"""
ImageIn Filter Demo with GCS - Enhanced Version

This script demonstrates an enhanced ImageIn filter with Google Cloud Storage by:
1. Setting up a pipeline: ImageIn -> FaceEnhancer -> Webvis
2. Reading images from GCS bucket
3. Enhancing face crops with larger frame, random name, and timestamp
4. Running the pipeline to display enhanced images in a web browser

Usage:
    python main_gcs_enhanced.py [gcs_path]
    
    Examples:
        python main_gcs_enhanced.py
        python main_gcs_enhanced.py gs://my-bucket/images
        python main_gcs_enhanced.py gs://protege-artifacts-development/video-pipeline-demo/stream2/images

Then open http://127.0.0.1:8004 in your browser to see the enhanced images.
"""

import os
import sys
import argparse
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn
from openfilter.filter_runtime.filters.webvis import Webvis
from face_enhancer import FaceEnhancer

def main():
    """Run the enhanced ImageIn filter demo with GCS."""
    parser = argparse.ArgumentParser(description='ImageIn Filter Demo with GCS - Enhanced Version')
    parser.add_argument('gcs_path', nargs='?', 
                       default="",
                       help='GCS path to images (default:)')
    
    args = parser.parse_args()
    
    print("ImageIn Filter Demo with GCS - Enhanced Version")
    print("===============================================")
    
    print(f"\nStarting pipeline with images from: {args.gcs_path}")
    print("Open http://127.0.0.1:8004 in your browser to view the enhanced images")
    print("Press Ctrl+C to stop the pipeline")
    
    # Run the pipeline
    Filter.run_multi([
        # ImageIn: Read images from GCS with looping
        (ImageIn, dict(
            sources=f'{args.gcs_path}!loop!maxfps=1',  # Slower for better viewing
            outputs='tcp://*:8890',
            loop=True,  # Infinite loop
            poll_interval=3.0,  # Check for new images every 3 seconds
        )),
        
        # FaceEnhancer: Enhance face crops with larger frame, name, and timestamp
        (FaceEnhancer, dict(
            sources='tcp://127.0.0.1:8890',
            outputs='tcp://*:8892',
        )),
        
        # Webvis: Display enhanced images in web browser
        (Webvis, dict(
            sources='tcp://127.0.0.1:8892',
            host='127.0.0.1',
            port=8003,
        )),
    ])

if __name__ == '__main__':
    main()
