#!/usr/bin/env python3
"""
ImageOut Filter Demo

This example demonstrates how to use the ImageOut filter to save frames as images
in various formats (PNG, JPG, etc.) with different options.

Usage:
    python main.py

The example reads a video file using VideoIn, visualizes it with WebVis, and saves 
frames as images using the ImageOut filter with different configurations.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import openfilter
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from openfilter.filter_runtime.filter import Filter, FilterConfig
from openfilter.filter_runtime.filters.image_out import ImageOut
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis


def main():
    """Run the ImageOut filter demo."""
    
    # Get the sample video path
    sample_video_path = Path(__file__).parent.parent / 'openfilter-heroku-demo' / 'assets' / 'sample-video.mp4'
    
    # Create output directory
    output_dir = Path(__file__).parent / 'output'
    output_dir.mkdir(exist_ok=True)
    
    print("ImageOut Filter Demo")
    print("=" * 50)
    print(f"Video source: {sample_video_path}")
    print(f"Output directory: {output_dir}")
    print(f"WebVis URL: http://localhost:8000")
    print()
    
    # Check if sample video exists
    if not sample_video_path.exists():
        print(f"Error: Sample video not found at {sample_video_path}")
        print("Please make sure the sample-video.mp4 file exists in the assets directory.")
        return
    
    # Run the filters
    try:
        print("Starting pipeline...")
        print("Pipeline: VideoIn -> WebVis -> ImageOut")
        print()
        print("Open your browser and go to: http://localhost:8000")
        print("Press Ctrl+C to stop the demo")
        print()
        
        Filter.run_multi([
            # VideoIn: Read sample video and output to both WebVis and ImageOut
            (VideoIn, FilterConfig({
                'id': 'video-input',
                'sources': f'file://{sample_video_path}',
                'outputs': 'tcp://127.0.0.1:5550',  # Split to both filters
                'sync': False,  # Process as fast as possible
                'loop': False   # Play once
            })),
            
            # ImageOut: Save frames in multiple formats
            (ImageOut, FilterConfig({
                'id': 'image-output',
                'sources': 'tcp://127.0.0.1:5550',
                'outputs': [
                    # PNG output with high quality (lossless)
                    f'file://{output_dir}/frames_%Y%m%d_%H%M%S_%d.png!format=png!compression=0',
                    
                    # JPG output with medium quality (smaller files)
                    f'file://{output_dir}/frames_%Y%m%d_%H%M%S_%d.jpg!format=jpg!quality=85',
                    
                    # WebP output (modern format)
                    f'file://{output_dir}/frames_%Y%m%d_%H%M%S_%d.webp!format=webp!quality=90',
                    
                    # BMP output (uncompressed)
                    f'file://{output_dir}/frames_%Y%m%d_%H%M%S_%d.bmp!format=bmp'
                ],
                
                # Global settings (can be overridden per output)
                'bgr': True,
                'quality': 95,
                'compression': 6
            })),
            
            # WebVis: Visualize video stream in browser (no outputs - just serves HTTP)
            (Webvis, FilterConfig({
                'id': 'web-visualization',
                'sources': 'tcp://127.0.0.1:5550',
                'port': 8000
            }))
        ])
        
        print("\nDemo completed successfully!")
        print(f"Check the output directory: {output_dir}")
        
        # List generated files
        output_files = list(output_dir.glob('*'))
        if output_files:
            print(f"\nGenerated {len(output_files)} files:")
            for file in sorted(output_files):
                print(f"  {file.name}")
        
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    except Exception as e:
        print(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
