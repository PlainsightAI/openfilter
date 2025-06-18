#!/usr/bin/env python

import unittest

from openfilter.filter_runtime.filters.video_in import is_video_s3, parse_s3_uri


class TestS3Functions(unittest.TestCase):
    
    def test_is_video_s3(self):
        """Test S3 URL detection"""
        # Valid S3 URLs
        self.assertTrue(is_video_s3('s3://test-bucket/key'))
        self.assertTrue(is_video_s3('s3://test-bucket/path/to/video.mp4'))
        
        # Invalid URLs
        self.assertFalse(is_video_s3('https://example.com/video.mp4'))
        self.assertFalse(is_video_s3('http://example.com/video.mp4'))
        self.assertFalse(is_video_s3('file://video.mp4'))
        self.assertFalse(is_video_s3('rtsp://stream.mp4'))
        self.assertFalse(is_video_s3('webcam://0'))
        self.assertFalse(is_video_s3('/local/path/video.mp4'))
    
    def test_parse_s3_uri(self):
        """Test S3 URI parsing"""
        # Valid S3 URIs
        bucket, key = parse_s3_uri('s3://test-bucket/test-video.mp4')
        self.assertEqual(bucket, 'test-bucket')
        self.assertEqual(key, 'test-video.mp4')
        
        bucket, key = parse_s3_uri('s3://my-bucket/path/to/my-video.mp4')
        self.assertEqual(bucket, 'my-bucket')
        self.assertEqual(key, 'path/to/my-video.mp4')
        
        # Edge cases
        bucket, key = parse_s3_uri('s3://bucket/single-file.mp4')
        self.assertEqual(bucket, 'bucket')
        self.assertEqual(key, 'single-file.mp4')
        
        # Invalid URIs should raise ValueError
        with self.assertRaises(ValueError):
            parse_s3_uri('https://example.com/video.mp4')
        
        with self.assertRaises(ValueError):
            parse_s3_uri('s3://')
        
        with self.assertRaises(ValueError):
            parse_s3_uri('s3://bucket')
        
        with self.assertRaises(ValueError):
            parse_s3_uri('s3://bucket/')


if __name__ == '__main__':
    unittest.main()
