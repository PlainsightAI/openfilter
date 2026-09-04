#!/usr/bin/env python3
"""
Directory Pipeline Demo

This example demonstrates using the directory traversal feature in VideoIn to sequentialize
a directory of video files and run them through a processing pipeline.
"""

import os
import sys
import shutil
import tempfile
import argparse
from pathlib import Path

import cv2
import numpy as np

from openfilter.filter_runtime.filter import Filter, FilterConfig
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.image_out import ImageOut


class InfoPrinter(Filter):
    """Prints frame metadata in real-time to show directory sequential playback."""
    FILTER_TYPE = 'Processor'

    def process(self, frames):
        for topic, frame in frames.items():
            meta = frame.data.get('meta', {})
            src = meta.get('src', 'N/A')
            frame_idx = meta.get('src_frame', 'N/A')
            pts = meta.get('src_seconds', 'N/A')
            
            print(f"[InfoPrinter] Topic: {topic} | Active Source: {src} | Frame In Video: {frame_idx} | Offset Secs: {pts}")
            
        return frames


def create_sample_video(p: str, color: str):
    """Generate a lightweight 3-frame MP4 video of a solid color using cv2.VideoWriter."""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(p, fourcc, 30.0, (100, 100))
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    if color == 'red':
        img[:, :, 2] = 255
    elif color == 'green':
        img[:, :, 1] = 255
    elif color == 'blue':
        img[:, :, 0] = 255
    for _ in range(3):
        out.write(img)
    out.release()
    print(f"Created sample video: {p}")


def main():
    parser = argparse.ArgumentParser(description="Run the directory pipeline demo.")
    parser.add_argument("--directory", type=str, help="Directory of video files to read. If not provided, a temporary one with sample videos will be created.")
    parser.add_argument("--loop", type=int, default=1, help="Number of times to loop (0 for infinite loop, 1 for once, etc.)")
    args = parser.parse_args()

    temp_dir = None
    if not args.directory:
        print("No directory provided. Creating a temporary directory with sample videos...")
        temp_dir = tempfile.mkdtemp()
        
        # Create three separate video clips dynamically
        vid_a = os.path.join(temp_dir, "01_autumn.mp4")
        vid_b = os.path.join(temp_dir, "02_winter.mp4")
        vid_c = os.path.join(temp_dir, "03_spring.mp4")
        
        create_sample_video(vid_a, 'red')
        create_sample_video(vid_b, 'green')
        create_sample_video(vid_c, 'blue')
            
        source_dir = temp_dir
    else:
        source_dir = os.path.abspath(args.directory)
        if not os.path.isdir(source_dir):
            print(f"Error: {source_dir} is not a valid directory.")
            sys.exit(1)

    output_dir = Path(__file__).parent / "output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nDirectory Pipeline Demo")
    print("=" * 60)
    print(f"Source Directory: {source_dir}")
    print(f"Output Frames:    {output_dir}")
    print("=" * 60)
    print("Starting pipeline: VideoIn -> InfoPrinter -> ImageOut")
    print("Press Ctrl+C to exit.")
    print("-" * 60)

    try:
        Filter.run_multi([
            # 1. VideoIn: reads the folder
            (VideoIn, FilterConfig({
                'id': 'video-input',
                'sources': f'file://{source_dir}!sync!maxfps=1',
                'outputs': 'tcp://127.0.0.1:5570',
            })),
            
            # 2. InfoPrinter: custom live printing filter
            (InfoPrinter, FilterConfig({
                'id': 'info-printer',
                'sources': 'tcp://127.0.0.1:5570',
                'outputs': 'tcp://127.0.0.1:5572',
            })),
            
            # 3. ImageOut: saves the frames to disk
            (ImageOut, FilterConfig({
                'id': 'image-output',
                'sources': 'tcp://127.0.0.1:5572',
                'outputs': [
                    f'file://{output_dir}/frame_%Y%m%d_%H%M%S_%d.png!format=png'
                ],
                'bgr': True,
            }))
        ])
        
        print("-" * 60)
        print("Pipeline execution finished successfully.")
        print(f"Output frames saved in: {output_dir}")
        print("List of generated files:")
        for entry in sorted(output_dir.iterdir()):
            print(f"  - {entry.name}")

    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
    except Exception as e:
        print(f"\nPipeline execution failed: {e}")
        sys.exit(1)
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    main()
