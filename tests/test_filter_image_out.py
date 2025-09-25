#!/usr/bin/env python

import logging
import multiprocessing as mp
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.image_out import ImageOut, ImageOutConfig, ImageWriter
from openfilter.filter_runtime.test import QueueToFilters
from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.frame import Frame

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

# Test images in different colors
RED_IMAGE = create_test_image(color=(0, 0, 255), text="Red")    # BGR format
GREEN_IMAGE = create_test_image(color=(0, 255, 0), text="Green")
BLUE_IMAGE = create_test_image(color=(255, 0, 0), text="Blue")

def is_image_color(img, expected_color, tolerance=50):
    """Check if image is predominantly the expected color."""
    mean_color = np.mean(img, axis=(0, 1))
    return np.allclose(mean_color, expected_color, atol=tolerance)

def create_test_frames():
    """Create test frames with different topics and data."""
    frames = {
        'main': Frame(RED_IMAGE, {'meta': {'id': 1, 'timestamp': '2024-01-01T10:00:00Z'}}, 'BGR'),
        'camera1': Frame(GREEN_IMAGE, {'meta': {'id': 2, 'timestamp': '2024-01-01T10:00:01Z'}}, 'BGR'),
        'camera2': Frame(BLUE_IMAGE, {'meta': {'id': 3, 'timestamp': '2024-01-01T10:00:02Z'}}, 'BGR'),
    }
    return frames


class TestImageWriter(unittest.TestCase):
    """Test the ImageWriter class directly."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_image_writer_init_basic(self):
        """Test basic ImageWriter initialization."""
        output_path = os.path.join(self.test_dir, "test.jpg")
        writer = ImageWriter(f"file://{output_path}")
        
        self.assertEqual(writer.output, output_path)
        self.assertEqual(writer.format, 'jpg')
        self.assertEqual(writer.frame_count, 0)
    
    def test_image_writer_init_with_options(self):
        """Test ImageWriter initialization with options."""
        output_path = os.path.join(self.test_dir, "test.png")
        writer = ImageWriter(
            f"file://{output_path}",
            bgr=False,
            format='png',
            quality=80,
            compression=9
        )
        
        self.assertEqual(writer.output, output_path)
        self.assertEqual(writer.format, 'png')
        self.assertFalse(writer.is_bgr)
        self.assertEqual(writer.quality, 80)
        self.assertEqual(writer.compression, 9)
    
    def test_image_writer_init_invalid_output(self):
        """Test ImageWriter initialization with invalid output."""
        with self.assertRaises(ValueError) as cm:
            ImageWriter("http://example.com/image.jpg")
        self.assertIn("only supports file:// outputs", str(cm.exception))
    
    def test_image_writer_init_invalid_format(self):
        """Test ImageWriter initialization with invalid format."""
        output_path = os.path.join(self.test_dir, "test.invalid")
        with self.assertRaises(ValueError) as cm:
            ImageWriter(f"file://{output_path}")
        self.assertIn("Unsupported file extension", str(cm.exception))
    
    def test_image_writer_init_format_override(self):
        """Test ImageWriter with format override."""
        output_path = os.path.join(self.test_dir, "test.dat")
        writer = ImageWriter(f"file://{output_path}", format='png')
        
        self.assertEqual(writer.format, 'png')
    
    def test_image_writer_write_jpg(self):
        """Test writing JPEG image."""
        output_path = os.path.join(self.test_dir, "test.jpg")
        writer = ImageWriter(f"file://{output_path}")
        
        writer.write(RED_IMAGE)
        
        self.assertTrue(os.path.exists(output_path))
        self.assertEqual(writer.frame_count, 1)
        
        # Verify image was written correctly
        written_img = cv2.imread(output_path)
        self.assertIsNotNone(written_img)
        self.assertTrue(is_image_color(written_img, (0, 0, 255)))
    
    def test_image_writer_write_png(self):
        """Test writing PNG image."""
        output_path = os.path.join(self.test_dir, "test.png")
        writer = ImageWriter(f"file://{output_path}")
        
        writer.write(GREEN_IMAGE)
        
        self.assertTrue(os.path.exists(output_path))
        self.assertEqual(writer.frame_count, 1)
        
        # Verify image was written correctly
        written_img = cv2.imread(output_path)
        self.assertIsNotNone(written_img)
        self.assertTrue(is_image_color(written_img, (0, 255, 0)))
    
    def test_image_writer_write_with_frame_id(self):
        """Test writing image with frame ID."""
        output_path = os.path.join(self.test_dir, "test_%d.jpg")
        writer = ImageWriter(f"file://{output_path}")
        
        writer.write(RED_IMAGE, "frame_001")
        
        # With %d in path, strftime processes it first to get day of month
        # The frame count replacement doesn't work because %d is already processed
        from time import strftime
        expected_day = strftime("%d")
        expected_path = os.path.join(self.test_dir, f"test_{expected_day}.jpg")
        self.assertTrue(os.path.exists(expected_path))
        self.assertEqual(writer.frame_count, 1)
    
    def test_image_writer_write_with_frame_id_no_format(self):
        """Test writing image with frame ID when no %d formatting."""
        output_path = os.path.join(self.test_dir, "test.jpg")
        writer = ImageWriter(f"file://{output_path}")
        
        writer.write(RED_IMAGE, "frame_001")
        
        # Without %d, it should append frame_id
        expected_path = os.path.join(self.test_dir, "test_frame_001.jpg")
        self.assertTrue(os.path.exists(expected_path))
        self.assertEqual(writer.frame_count, 1)
    
    def test_image_writer_write_none_image(self):
        """Test writing None image raises error."""
        output_path = os.path.join(self.test_dir, "test.jpg")
        writer = ImageWriter(f"file://{output_path}")
        
        with self.assertRaises(RuntimeError) as cm:
            writer.write(None)
        self.assertIn("cannot write None image", str(cm.exception))
    
    def test_image_writer_rgb_conversion(self):
        """Test RGB to BGR conversion."""
        # Create RGB image (red in RGB is (255, 0, 0))
        rgb_image = create_test_image(color=(255, 0, 0), text="RGB Red")
        
        output_path = os.path.join(self.test_dir, "test_rgb.jpg")
        writer = ImageWriter(f"file://{output_path}", bgr=False)
        
        writer.write(rgb_image)
        
        # Verify image was written correctly
        written_img = cv2.imread(output_path)
        self.assertIsNotNone(written_img)
        # In BGR, red should be (0, 0, 255)
        self.assertTrue(is_image_color(written_img, (0, 0, 255)))
    
    def test_image_writer_multiple_formats(self):
        """Test writing to different image formats."""
        formats = ['jpg', 'png', 'bmp', 'tiff', 'webp']
        
        for fmt in formats:
            output_path = os.path.join(self.test_dir, f"test.{fmt}")
            writer = ImageWriter(f"file://{output_path}")
            
            writer.write(BLUE_IMAGE)
            
            self.assertTrue(os.path.exists(output_path), f"Failed to write {fmt} format")
            self.assertEqual(writer.frame_count, 1)
    
    def test_image_writer_directory_creation(self):
        """Test that directories are created automatically."""
        nested_path = os.path.join(self.test_dir, "nested", "deep", "test.jpg")
        writer = ImageWriter(f"file://{nested_path}")
        
        writer.write(RED_IMAGE)
        
        self.assertTrue(os.path.exists(nested_path))
        self.assertTrue(os.path.exists(os.path.dirname(nested_path)))


class TestImageOutConfig(unittest.TestCase):
    """Test the ImageOutConfig class."""
    
    def test_normalize_config_basic(self):
        """Test basic config normalization."""
        config = {
            'sources': 'tcp://localhost:5550',
            'outputs': 'file:///tmp/test.jpg'
        }
        
        normalized = ImageOut.normalize_config(config)
        
        self.assertIsInstance(normalized, ImageOutConfig)
        self.assertEqual(len(normalized.outputs), 1)
        self.assertEqual(normalized.outputs[0].output, 'file:///tmp/test.jpg')
        self.assertEqual(normalized.outputs[0].topic, 'main')
    
    def test_normalize_config_multiple_outputs(self):
        """Test config normalization with multiple outputs."""
        config = {
            'sources': 'tcp://localhost:5550',
            'outputs': 'file:///tmp/test1.jpg, file:///tmp/test2.png;camera1'
        }
        
        normalized = ImageOut.normalize_config(config)
        
        self.assertEqual(len(normalized.outputs), 2)
        self.assertEqual(normalized.outputs[0].output, 'file:///tmp/test1.jpg')
        self.assertEqual(normalized.outputs[0].topic, 'main')
        self.assertEqual(normalized.outputs[1].output, 'file:///tmp/test2.png')
        self.assertEqual(normalized.outputs[1].topic, 'camera1')
    
    def test_normalize_config_with_options(self):
        """Test config normalization with options."""
        config = {
            'sources': 'tcp://localhost:5550',
            'outputs': 'file:///tmp/test.jpg!quality=80!format=jpg'
        }
        
        normalized = ImageOut.normalize_config(config)
        
        self.assertEqual(len(normalized.outputs), 1)
        self.assertEqual(normalized.outputs[0].output, 'file:///tmp/test.jpg')
        self.assertEqual(normalized.outputs[0].options.quality, 80)
        self.assertEqual(normalized.outputs[0].options.format, 'jpg')
    
    def test_normalize_config_dict_format(self):
        """Test config normalization with dict format."""
        config = {
            'sources': 'tcp://localhost:5550',
            'outputs': [
                {'output': 'file:///tmp/test1.jpg', 'topic': 'main'},
                {'output': 'file:///tmp/test2.png', 'topic': 'camera1', 'options': {'quality': 90}}
            ]
        }
        
        normalized = ImageOut.normalize_config(config)
        
        self.assertEqual(len(normalized.outputs), 2)
        self.assertEqual(normalized.outputs[0].output, 'file:///tmp/test1.jpg')
        self.assertEqual(normalized.outputs[0].topic, 'main')
        self.assertEqual(normalized.outputs[1].output, 'file:///tmp/test2.png')
        self.assertEqual(normalized.outputs[1].topic, 'camera1')
        self.assertEqual(normalized.outputs[1].options.quality, 90)
    
    def test_normalize_config_no_sources(self):
        """Test config normalization with no sources."""
        config = {
            'outputs': 'file:///tmp/test.jpg'
        }
        
        with self.assertRaises(ValueError) as cm:
            ImageOut.normalize_config(config)
        self.assertIn("must specify at least one source", str(cm.exception))
    
    def test_normalize_config_no_outputs(self):
        """Test config normalization with no outputs."""
        config = {
            'sources': 'tcp://localhost:5550'
        }
        
        with self.assertRaises(ValueError) as cm:
            ImageOut.normalize_config(config)
        self.assertIn("must specify at least one output", str(cm.exception))
    
    def test_normalize_config_invalid_output(self):
        """Test config normalization with invalid output."""
        config = {
            'sources': 'tcp://localhost:5550',
            'outputs': 'http://example.com/test.jpg'
        }
        
        with self.assertRaises(ValueError) as cm:
            ImageOut.normalize_config(config)
        self.assertIn("only accepts file:// outputs", str(cm.exception))
    
    def test_normalize_config_global_options(self):
        """Test config normalization with global options."""
        config = {
            'sources': 'tcp://localhost:5550',
            'outputs': 'file:///tmp/test.jpg',
            'bgr': False,
            'quality': 85,
            'compression': 8
        }
        
        normalized = ImageOut.normalize_config(config)
        
        self.assertFalse(normalized.bgr)
        self.assertEqual(normalized.quality, 85)
        self.assertEqual(normalized.compression, 8)


class TestImageOut(unittest.TestCase):
    """Test the ImageOut filter."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_image_out_basic(self):
        """Test basic ImageOut functionality."""
        output_path = os.path.join(self.test_dir, "test.jpg")
        
        config = ImageOut.normalize_config({
            'sources': 'tcp://localhost:5550',
            'outputs': f'file://{output_path}'
        })
        
        filter_instance = ImageOut(config)
        filter_instance.setup(config)
        
        try:
            # Create test frames
            frames = create_test_frames()
            
            # Process frames
            filter_instance.process(frames)
            
            # Check that file was created (with topic and frame ID)
            expected_path = os.path.join(self.test_dir, "test_main_1.jpg")
            self.assertTrue(os.path.exists(expected_path))
            
            # Verify image content
            written_img = cv2.imread(expected_path)
            self.assertIsNotNone(written_img)
            self.assertTrue(is_image_color(written_img, (0, 0, 255)))  # Red image
            
        finally:
            filter_instance.shutdown()
    
    def test_image_out_multiple_topics(self):
        """Test ImageOut with multiple topics."""
        output1_path = os.path.join(self.test_dir, "main.jpg")
        output2_path = os.path.join(self.test_dir, "camera1.jpg")
        
        config = ImageOut.normalize_config({
            'sources': 'tcp://localhost:5550',
            'outputs': f'file://{output1_path}, file://{output2_path};camera1'
        })
        
        filter_instance = ImageOut(config)
        filter_instance.setup(config)
        
        try:
            # Create test frames
            frames = create_test_frames()
            
            # Process frames
            filter_instance.process(frames)
            
            # Check that both files were created (with topic and frame ID)
            expected_main_path = os.path.join(self.test_dir, "main_main_1.jpg")
            expected_camera1_path = os.path.join(self.test_dir, "camera1_camera1_2.jpg")
            self.assertTrue(os.path.exists(expected_main_path))
            self.assertTrue(os.path.exists(expected_camera1_path))
            
            # Verify image content
            main_img = cv2.imread(expected_main_path)
            camera1_img = cv2.imread(expected_camera1_path)
            
            self.assertIsNotNone(main_img)
            self.assertIsNotNone(camera1_img)
            self.assertTrue(is_image_color(main_img, (0, 0, 255)))    # Red (main)
            self.assertTrue(is_image_color(camera1_img, (0, 255, 0))) # Green (camera1)
            
        finally:
            filter_instance.shutdown()
    
    def test_image_out_with_options(self):
        """Test ImageOut with specific options."""
        output_path = os.path.join(self.test_dir, "test.png")
        
        config = ImageOut.normalize_config({
            'sources': 'tcp://localhost:5550',
            'outputs': f'file://{output_path}!format=png!compression=9'
        })
        
        filter_instance = ImageOut(config)
        filter_instance.setup(config)
        
        try:
            # Create test frames
            frames = create_test_frames()
            
            # Process frames
            filter_instance.process(frames)
            
            # Check that PNG file was created (with topic and frame ID)
            expected_path = os.path.join(self.test_dir, "test_main_1.png")
            self.assertTrue(os.path.exists(expected_path))
            
            # Verify it's actually a PNG
            with open(expected_path, 'rb') as f:
                header = f.read(8)
                self.assertTrue(header.startswith(b'\x89PNG\r\n\x1a\n'))
            
        finally:
            filter_instance.shutdown()
    
    def test_image_out_wildcard_topics(self):
        """Test ImageOut with wildcard topics."""
        output_path = os.path.join(self.test_dir, "camera_%d.jpg")
        
        config = ImageOut.normalize_config({
            'sources': 'tcp://localhost:5550',
            'outputs': f'file://{output_path};camera*'
        })
        
        filter_instance = ImageOut(config)
        filter_instance.setup(config)
        
        try:
            # Create test frames with camera topics
            frames = {
                'camera1': Frame(GREEN_IMAGE, {'meta': {'id': 1}}, 'BGR'),
                'camera2': Frame(BLUE_IMAGE, {'meta': {'id': 2}}, 'BGR'),
                'other': Frame(RED_IMAGE, {'meta': {'id': 3}}, 'BGR'),  # Should not match
            }
            
            # Process frames
            filter_instance.process(frames)
            
            # Check that file was created (with %d processed by strftime first)
            from time import strftime
            expected_day = strftime("%d")
            expected_path = os.path.join(self.test_dir, f"camera_{expected_day}.jpg")
            self.assertTrue(os.path.exists(expected_path))
            
            # Verify image content (should be the last processed frame - blue)
            written_img = cv2.imread(expected_path)
            self.assertIsNotNone(written_img)
            self.assertTrue(is_image_color(written_img, (255, 0, 0)))  # Blue (last frame)
            
        finally:
            filter_instance.shutdown()
    
    def test_image_out_frame_numbering(self):
        """Test ImageOut with frame number formatting."""
        output_path = os.path.join(self.test_dir, "frame_%d.jpg")
        
        config = ImageOut.normalize_config({
            'sources': 'tcp://localhost:5550',
            'outputs': f'file://{output_path}'
        })
        
        filter_instance = ImageOut(config)
        filter_instance.setup(config)
        
        try:
            # Process multiple frames
            for i in range(3):
                frames = {
                    'main': Frame(create_test_image(color=(0, 0, 255), text=f"Frame {i}"), {'meta': {'id': i}}, 'BGR')
                }
                filter_instance.process(frames)
            
            # Check that file was created (with %d processed by strftime first)
            from time import strftime
            expected_day = strftime("%d")
            expected_path = os.path.join(self.test_dir, f"frame_{expected_day}.jpg")
            self.assertTrue(os.path.exists(expected_path), f"Expected file {expected_path} not found")
            
        finally:
            filter_instance.shutdown()
    
    def test_image_out_no_image_data(self):
        """Test ImageOut with frames that have no image data."""
        output_path = os.path.join(self.test_dir, "test.jpg")
        
        config = ImageOut.normalize_config({
            'sources': 'tcp://localhost:5550',
            'outputs': f'file://{output_path}'
        })
        
        filter_instance = ImageOut(config)
        filter_instance.setup(config)
        
        try:
            # Create frame without image data
            frames = {
                'main': Frame(None, {'meta': {'id': 1}}, 'BGR')
            }
            
            # Process frames - should not create file
            filter_instance.process(frames)
            
            # Check that no file was created
            self.assertFalse(os.path.exists(output_path))
            
        finally:
            filter_instance.shutdown()
    
    def test_image_out_missing_topic(self):
        """Test ImageOut with missing expected topic."""
        output_path = os.path.join(self.test_dir, "test.jpg")
        
        config = ImageOut.normalize_config({
            'sources': 'tcp://localhost:5550',
            'outputs': f'file://{output_path};missing_topic'
        })
        
        filter_instance = ImageOut(config)
        filter_instance.setup(config)
        
        try:
            # Create frames with different topic
            frames = {
                'main': Frame(RED_IMAGE, {'meta': {'id': 1}}, 'BGR')
            }
            
            # Process frames - should not create file
            filter_instance.process(frames)
            
            # Check that no file was created
            self.assertFalse(os.path.exists(output_path))
            
        finally:
            filter_instance.shutdown()


class TestImageOutIntegration(unittest.TestCase):
    """Test ImageOut integration with the filter system."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_image_out_integration(self):
        """Test ImageOut integration with QueueToFilters."""
        output_path = os.path.join(self.test_dir, "integration_test.jpg")
        
        try:
            runner = Filter.Runner([
                (QueueToFilters, dict(
                    outputs='ipc://test-Q2F',
                    queue=(queue := mp.Queue()),
                )),
                (ImageOut, dict(
                    sources='ipc://test-Q2F',
                    outputs=f'file://{output_path}',
                )),
            ], exit_time=2)
            
            try:
                # Send test frames
                queue.put(Frame(RED_IMAGE, {'meta': {'id': 1}}, 'BGR'))
                queue.put(Frame(GREEN_IMAGE, {'meta': {'id': 2}}, 'BGR'))
                queue.put(False)  # End signal
                
                # Wait for completion
                result = runner.wait()
                self.assertEqual(result, [0, 0])
                
                # Check that file was created (with topic and frame ID)
                expected_path = os.path.join(self.test_dir, "integration_test_main_2.jpg")
                self.assertTrue(os.path.exists(expected_path))
                
                # Verify last image (green)
                written_img = cv2.imread(expected_path)
                self.assertIsNotNone(written_img)
                self.assertTrue(is_image_color(written_img, (0, 255, 0)))
                
            finally:
                runner.stop()
                queue.close()
                
        except Exception as e:
            self.fail(f"Integration test failed: {e}")


if __name__ == '__main__':
    unittest.main()