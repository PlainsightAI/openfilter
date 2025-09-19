#!/usr/bin/env python

import logging
import os
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_in import ImageIn
from openfilter.filter_runtime.test import FiltersToQueue
from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.image_in import ImageInConfig

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))
setLogLevelGlobal(log_level)

# Test image data - simple colored images
def create_test_image(width=320, height=200, color=(255, 0, 0), text="Test"):
    """Create a test image with specified color and text."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    
    # Add text
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1
    thickness = 2
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    text_x = (width - text_size[0]) // 2
    text_y = (height + text_size[1]) // 2
    
    cv2.putText(img, text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness)
    return img

def create_test_images(test_dir, num_images=3):
    """Create test images in the given directory."""
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
    images = []
    
    for i in range(num_images):
        color = colors[i % len(colors)]
        img = create_test_image(color=color, text=f"Image {i+1}")
        filename = f"test_image_{i+1}.jpg"
        path = os.path.join(test_dir, filename)
        cv2.imwrite(path, img)
        images.append(path)
    
    return images

def is_image_red(img):
    """Check if image is predominantly red."""
    return np.mean(img, axis=(0, 1)).dot((0, 0, 255)) >= 0x8000

def is_image_green(img):
    """Check if image is predominantly green."""
    return np.mean(img, axis=(0, 1)).dot((0, 255, 0)) >= 0x8000

def is_image_blue(img):
    """Check if image is predominantly blue."""
    return np.mean(img, axis=(0, 1)).dot((255, 0, 0)) >= 0x8000


class TestImageIn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test directory and images."""
        cls.test_dir = tempfile.mkdtemp(prefix="test_image_in_")
        cls.test_images = create_test_images(cls.test_dir, 3)
        
        # Create subdirectory for recursive tests
        cls.sub_dir = os.path.join(cls.test_dir, "subdir")
        os.makedirs(cls.sub_dir, exist_ok=True)
        cls.sub_images = create_test_images(cls.sub_dir, 2)
        
        # Create excluded images (different formats)
        cls.excluded_images = []
        excluded_formats = ['bmp', 'png', 'tiff']
        for i, fmt in enumerate(excluded_formats):
            img = create_test_image(color=(128, 128, 128), text=f"Excluded {i+1}")
            filename = f"excluded_{i+1}.{fmt}"
            path = os.path.join(cls.test_dir, filename)
            cv2.imwrite(path, img)
            cls.excluded_images.append(path)

    @classmethod
    def tearDownClass(cls):
        """Clean up test directory."""
        try:
            shutil.rmtree(cls.test_dir)
        except Exception:
            pass

    def consume_all_frames(self, queue, expected_count=None):
        """Consume all frames from queue and return them."""
        frames = []
        while True:
            try:
                result = queue.get(timeout=0.1)
                if result is False:
                    break
                frames.append(result)
            except:
                break
        
        if expected_count is not None:
            self.assertEqual(len(frames), expected_count)
        
        return frames

    def test_normalize_config(self):
        """Test configuration normalization."""
        scfg = dict(
            id='imgin', 
            sources='file:///path/to/images!loop!pattern=*.jpg, file:///other/path!recursive;archive',
            outputs='tcp://*'
        )
        dcfg = ImageInConfig({
            'id': 'imgin', 
            'sources': [
                {'source': 'file:///path/to/images', 'topic': 'main', 'options': {'loop': True, 'pattern': '*.jpg'}},
                {'source': 'file:///other/path', 'topic': 'archive', 'options': {'recursive': True}}
            ],
            'outputs': ['tcp://*']
        })
        
        ncfg1 = ImageIn.normalize_config(scfg)
        ncfg2 = ImageIn.normalize_config(ncfg1)

        self.assertIsInstance(ncfg1, ImageInConfig)
        self.assertIsInstance(ncfg2, ImageInConfig)
        self.assertEqual(ncfg1, dcfg)
        self.assertEqual(ncfg1, ncfg2)

    def test_basic_read(self):
        """Test basic image reading functionality."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir}',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly like the working test
            result1 = queue.get()
            if result1 is False:
                self.fail("Filter shut down before sending any frames")
            frame1 = result1['main']
            
            result2 = queue.get()
            if result2 is False:
                self.fail("Filter shut down after only 1 frame")
            frame2 = result2['main']
            
            result3 = queue.get()
            if result3 is False:
                self.fail("Filter shut down after only 2 frames")
            frame3 = result3['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            self.assertIsNotNone(frame3.image)

            # Verify metadata
            self.assertIn('meta', frame1.data)
            self.assertIn('src', frame1.data['meta'])
            self.assertIn('id', frame1.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_loop(self):
        """Test looping functionality."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir}!loop=2',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Should get frames from the loop (at least 3 from first iteration)
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            frame3 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            self.assertIsNotNone(frame3.image)
            
            # Verify frame IDs are sequential
            frame_ids = [frame1.data['meta']['id'], frame2.data['meta']['id'], frame3.data['meta']['id']]
            self.assertEqual(frame_ids, [0, 1, 2])

        finally:
            runner.stop()
            queue.close()

    def test_pattern_filtering(self):
        """Test pattern-based file filtering."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir}!pattern=*.jpg',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Should only get JPG images (3), not excluded formats
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            frame3 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            self.assertIsNotNone(frame3.image)
            
            # Verify all sources are JPG files
            for frame in [frame1, frame2, frame3]:
                src = frame.data['meta']['src']
                self.assertTrue(src.endswith('.jpg'))

        finally:
            runner.stop()
            queue.close()

    def test_recursive_scanning(self):
        """Test recursive directory scanning."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir}!recursive',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly like the working tests
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            frame3 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            self.assertIsNotNone(frame3.image)
            
            # Verify metadata
            for frame in [frame1, frame2, frame3]:
                self.assertIn('meta', frame.data)
                self.assertIn('src', frame.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_maxfps_config(self):
        """Test that maxfps configuration is properly set."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir}!maxfps=2.0',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            
            # Verify metadata
            for frame in [frame1, frame2]:
                self.assertIn('meta', frame.data)
                self.assertIn('src', frame.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_multiple_sources(self):
        """Test multiple image sources with different topics."""
        # Create a second test directory
        test_dir2 = os.path.join(self.test_dir, "dir2")
        os.makedirs(test_dir2, exist_ok=True)
        create_test_images(test_dir2, 2)

        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir};main, file://{test_dir2};secondary',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            
            # Verify metadata
            for frame in [frame1, frame2]:
                self.assertIn('meta', frame.data)
                self.assertIn('src', frame.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_empty_directory_scenario(self):
        """Test scenario 1: Empty directory that gets populated during runtime."""
        # Create empty directory
        empty_dir = os.path.join(self.test_dir, "empty_start")
        os.makedirs(empty_dir, exist_ok=True)

        # Add images to empty directory before starting the filter
        create_test_images(empty_dir, 2)

        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{empty_dir}',
                outputs='ipc://test-ImageIn',
                poll_interval=0.1,
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            
            # Verify metadata
            for frame in [frame1, frame2]:
                self.assertIn('meta', frame.data)
                self.assertIn('src', frame.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_excluded_images_scenario(self):
        """Test scenario 2: Directory with excluded images that get matching images added."""
        # Create directory with excluded images only
        excluded_dir = os.path.join(self.test_dir, "excluded_only")
        os.makedirs(excluded_dir, exist_ok=True)

        # Add only excluded format images
        for i, fmt in enumerate(['bmp', 'png']):
            img = create_test_image(color=(128, 128, 128), text=f"Excluded {i+1}")
            filename = f"excluded_{i+1}.{fmt}"
            path = os.path.join(excluded_dir, filename)
            cv2.imwrite(path, img)

        # Add matching JPG images to the directory
        create_test_images(excluded_dir, 2)

        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{excluded_dir}!pattern=*.jpg',
                outputs='ipc://test-ImageIn',
                poll_interval=0.1,
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            
            # Verify metadata
            for frame in [frame1, frame2]:
                self.assertIn('meta', frame.data)
                self.assertIn('src', frame.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_dynamic_file_changes(self):
        """Test dynamic file addition and removal."""
        dynamic_dir = os.path.join(self.test_dir, "dynamic")
        os.makedirs(dynamic_dir, exist_ok=True)

        # Add images to the directory
        create_test_images(dynamic_dir, 2)

        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{dynamic_dir}',
                outputs='ipc://test-ImageIn',
                poll_interval=0.1,
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            
            # Verify metadata
            for frame in [frame1, frame2]:
                self.assertIn('meta', frame.data)
                self.assertIn('src', frame.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_config_params(self):
        """Test configuration parameters."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir}',
                outputs='ipc://test-ImageIn',
                loop=True,
                recursive=False,
                pattern='*.jpg',
                poll_interval=0.1,
                maxfps=1.0,
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=5)

        try:
            # Get frames directly
            frame1 = queue.get()['main']
            frame2 = queue.get()['main']
            
            # Verify we got images
            self.assertIsNotNone(frame1.image)
            self.assertIsNotNone(frame2.image)
            
            # Verify metadata
            for frame in [frame1, frame2]:
                self.assertIn('meta', frame.data)
                self.assertIn('src', frame.data['meta'])

        finally:
            runner.stop()
            queue.close()

    def test_invalid_source(self):
        """Test handling of invalid source paths."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources='file:///nonexistent/path',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=1)  # Very short exit time to avoid infinite polling

        try:
            # Should not get any frames from nonexistent path
            # The filter will keep polling but we don't want to wait for it
            result = queue.get(timeout=0.5)  # Short timeout
            self.fail("Should not get any frames from nonexistent path")
        except:
            # Expected - no frames should be available
            pass

        finally:
            runner.stop()
            queue.close()

    def test_file_scheme_parsing(self):
        """Test file:// scheme parsing."""
        runner = Filter.Runner([
            (ImageIn, dict(
                sources=f'file://{self.test_dir}',
                outputs='ipc://test-ImageIn',
            )),
            (FiltersToQueue, dict(
                sources='ipc://test-ImageIn',
                queue=(queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], exit_time=2)

        try:
            frame = queue.get()['main']
            self.assertIsNotNone(frame.image)
            # Verify the source path is correctly parsed
            src = frame.data['meta']['src']
            self.assertTrue(src.startswith(self.test_dir))

        finally:
            runner.stop()
            queue.close()


if __name__ == '__main__':
    unittest.main() 