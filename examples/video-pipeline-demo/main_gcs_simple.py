#!/usr/bin/env python3
"""
ImageIn Filter Demo with GCS - Simple Version

This script demonstrates a simple ImageIn filter with Google Cloud Storage by:
1. Setting up a pipeline: ImageIn -> Webvis
2. Reading images from GCS bucket
3. Running the pipeline to display images in a web browser

Usage:
    python main_gcs_simple.py [gcs_path]
    
    Examples:
        python main_gcs_simple.py
        python main_gcs_simple.py gs://my-bucket/images
        python main_gcs_simple.py gs://protege-artifacts-development/labelled-data/demo_ocr/data

Then open http://127.0.0.1:8000 in your browser to see the images.
"""

import os
import sys
import argparse
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn
from openfilter.filter_runtime.filters.webvis import Webvis

def main():
    """Run the simple ImageIn filter demo with GCS."""
    parser = argparse.ArgumentParser(description='ImageIn Filter Demo with GCS - Simple Version')
    parser.add_argument('gcs_path', nargs='?', 
                       default="",
                       help='GCS path to images (default:)')
    
    args = parser.parse_args()
    
    print("ImageIn Filter Demo with GCS - Simple Version")
    print("=============================================")
    
    print(f"\nStarting pipeline with images from: {args.gcs_path}")
    print("Open http://127.0.0.1:8000 in your browser to view the images")
    print("Press Ctrl+C to stop the pipeline")
    
    # Run the pipeline
    Filter.run_multi([
        # ImageIn: Read images from GCS with looping
        (ImageIn, dict(
            sources=f'{args.gcs_path}!loop!maxfps=2',
            outputs='tcp://*:8880',
            loop=True,  # Infinite loop
            poll_interval=5.0,  # Check for new images every 5 seconds
        )),
        
        # Webvis: Display images in web browser
        (Webvis, dict(
            sources='tcp://127.0.0.1:8880',
            host='127.0.0.1',
            port=8003,
        )),
    ])

if __name__ == '__main__':
    main()
