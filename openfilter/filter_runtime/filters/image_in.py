import logging
import os
import re
import glob
from threading import Thread, Event
from time import time, time_ns, sleep
from typing import Any, List, Optional
from urllib.parse import urlparse

import cv2
import numpy as np

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from google.cloud import storage
    HAS_GCS = True
except ImportError:
    HAS_GCS = False

from openfilter.filter_runtime.filter import Filter, Frame, FilterConfig
from openfilter.filter_runtime.utils import json_getval, split_commas_maybe, dict_without, adict

__all__ = ['ImageInConfig', 'ImageIn']

logger = logging.getLogger(__name__)

# Environment variable defaults (following VideoIn pattern)
IMAGE_IN_POLL_INTERVAL = float(json_getval((os.getenv('IMAGE_IN_POLL_INTERVAL') or '5.0')))
IMAGE_IN_LOOP = json_getval((os.getenv('IMAGE_IN_LOOP') or 'false').lower())
IMAGE_IN_RECURSIVE = bool(json_getval((os.getenv('IMAGE_IN_RECURSIVE') or 'false').lower()))
IMAGE_IN_MAXFPS = None if (_ := json_getval((os.getenv('IMAGE_IN_MAXFPS') or 'null').lower())) is None else float(_)

# Image file extensions
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff', 'gif', 'webp'}

def is_image_file(path: str) -> bool:
    """Check if file is an image based on extension."""
    ext = path.lower().rsplit(".", 1)[-1]
    return ext in IMAGE_EXTENSIONS

def matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches the given pattern (glob or regex)."""
    if not pattern:
        return True
    
    # Try as glob pattern first
    if '*' in pattern or '?' in pattern:
        return glob.fnmatch.fnmatch(os.path.basename(path), pattern)
    
    # Try as regex pattern
    try:
        return bool(re.search(pattern, path))
    except re.error:
        # If regex is invalid, treat as literal string
        return pattern in path

def parse_s3_uri(s3_uri: str):
    """Parse S3 URI into bucket and key components."""
    if not s3_uri.startswith('s3://'):
        raise ValueError(f'Invalid S3 URI: {s3_uri}')
    
    parsed = urlparse(s3_uri)
    if not parsed.netloc:
        raise ValueError(f'Invalid S3 URI: {s3_uri} (missing bucket)')
    
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    
    if not key:
        raise ValueError(f'Invalid S3 URI: {s3_uri} (missing key)')
    
    return bucket, key

def parse_gcs_uri(gcs_uri: str):
    """Parse GCS URI into bucket and key components."""
    if not gcs_uri.startswith('gs://'):
        raise ValueError(f'Invalid GCS URI: {gcs_uri}')
    
    parsed = urlparse(gcs_uri)
    if not parsed.netloc:
        raise ValueError(f'Invalid GCS URI: {gcs_uri} (missing bucket)')
    
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    
    if not key:
        raise ValueError(f'Invalid GCS URI: {gcs_uri} (missing key)')
    
    return bucket, key

class ImageInConfig(FilterConfig):
    """Configuration for the ImageIn filter. Follows the same pattern as VideoInConfig.
    More details in the docstring of the ImageIn filter.
    """
    class Source(adict):
        class Options(adict):
            loop: bool | int | None
            recursive: bool | None
            pattern: str | None
            region: str | None
            maxfps: float | None

        source: str
        topic: str | None
        options: Options | None

    sources: str | list[str | Source]
    
    # setting these here will make them default for all sources (overridable individually)
    loop: bool | int | None
    recursive: bool | None
    pattern: str | None
    poll_interval: float | None
    maxfps: float | None
    

class ImageIn(Filter):
    """Single or multiple image input filter. Images are assigned to topics via the ';' mapping character in `sources`.
    The default topic mapping if nothing specified is 'main'. All image sources must have unique topics. '!' allows
    setting options directly in the source string.

    config:
        sources:
            The source(s) of the image(s), comma delimited, can be file:// directory, s3:// bucket object, 
            or gs:// bucket object.

            Examples:
                'file:///path/to/images!loop!pattern=*.jpg, s3://bucket/images!recursive;archive'

                    is the same as

                ['file:///path/to/images!loop!pattern=*.jpg', 's3://bucket/images!recursive;archive']

                    is the same as

                [{'source': 'file:///path/to/images', 'topic': 'main', 'options': {'loop': True, 'pattern': '*.jpg'}},
                 {'source': 's3://bucket/images', 'topic': 'archive', 'options': {'recursive': True}}]

            `sources` individual options (text appended after source, e.g. 'file:///path!loop!pattern=*.jpg'):
                '!loop', '!no-loop', '!loop=3':
                    Set `loop` option for this source.

                '!recursive', '!no-recursive':
                    Set `recursive` option for this source (local only).

                '!pattern=*.jpg':
                    Set `pattern` option for this source.

                '!region=us-west-2':
                    Set AWS region for S3 sources. Only applies to s3:// sources.

                '!maxfps=1.0':
                    Set `maxfps` option for this source. Controls how many images per second are displayed.
                    For example, maxfps=1.0 means each image is displayed for 1 second.

        loop:
            Only has meaning for file:// sources. True or 0 means infinite loop, False means don't loop and go through
            the images only once, otherwise an int value loops through the images that number of times. Set here to apply
            to all sources or can be set individually per source. Global env var default IMAGE_IN_LOOP.

        recursive:
            Only has meaning for file:// sources. If True then scan subdirectories recursively. Set here to apply
            to all sources or can be set individually per source. Global env var default IMAGE_IN_RECURSIVE.

        pattern:
            Glob or regex pattern to filter files (e.g. "*.jpg", ".*\\.png$"). Set here to apply to all sources
            or can be set individually per source.

        poll_interval:
            Seconds between directory/bucket scans when idle. Set here to apply to all sources or can be set
            individually per source. Global env var default IMAGE_IN_POLL_INTERVAL.
        
        region:
            AWS region for S3 sources. Only applies to s3:// sources.

        maxfps:
            Restrict image display to this FPS. Controls how many images per second are displayed.
            For example, maxfps=1.0 means each image is displayed for 1 second.
            Set here to apply to all sources or can be set individually per source. Global env var default IMAGE_IN_MAXFPS.
            
        Example:
            openfilter run - ImageIn --sources s3://my-bucket/images!pattern=*.jpg - Webvis
            openfilter run - ImageIn --sources file:///path/to/images!loop!pattern=*.jpg - Webvis
            openfilter run - ImageIn --sources file:///path/to/images!recursive!pattern=*.jpg - Webvis
            openfilter run - ImageIn --sources file:///path/to/images!recursive!pattern=*.jpg!loop=3 - Webvis
            openfilter run - ImageIn --sources file:///path/to/images!recursive!pattern=*.jpg!loop=3!poll_interval=10 - Webvis
            openfilter run - ImageIn --sources file:///path/to/images!recursive!pattern=*.jpg!loop=3!poll_interval=10!region=us-west-2 - Webvis
            openfilter run - ImageIn --sources file:///path/to/images!recursive!pattern=*.jpg!loop=3!poll_interval=10!region=us-west-2 - Webvis
            openfilter run - ImageIn --sources file:///path/to/images!maxfps=1.0 - Webvis

    Environment variables:
        IMAGE_IN_LOOP
        IMAGE_IN_RECURSIVE
        IMAGE_IN_POLL_INTERVAL
        IMAGE_IN_MAXFPS

    S3 Configuration:
        For s3:// sources, AWS credentials are required. Set these environment variables:
        
        AWS_ACCESS_KEY_ID - Your AWS access key ID
        AWS_SECRET_ACCESS_KEY - Your AWS secret access key  
        AWS_DEFAULT_REGION - Default AWS region (optional, can be overridden per source)
        AWS_PROFILE - AWS credentials profile to use (alternative to access keys)
        
        Example S3 usage:
            openfilter run - ImageIn --sources s3://my-bucket/images!pattern=*.jpg - Webvis
    """

    FILTER_TYPE = 'Input'

    @classmethod
    def normalize_config(cls, config):
        """Normalize configuration following OpenFilter patterns."""
        sources = split_commas_maybe(config.get('sources'))
        config = ImageInConfig(super().normalize_config(dict_without(config, 'sources')))

        if sources is not None:
            config.sources = sources

        if not sources:
            raise ValueError('must specify at least one source')
        if not config.outputs:
            raise ValueError('must specify at least one output')

        for idx, source in enumerate(sources):
            if isinstance(source, dict):
                if not isinstance(source, ImageInConfig.Source):
                    sources[idx] = ImageInConfig.Source(source)

            else:
                source, topic = Filter.parse_topics(source, 1, False)
                source, options = Filter.parse_options(source)
                sources[idx] = ImageInConfig.Source(source=source, topic=topic and topic[0],
                    options=ImageInConfig.Source.Options(options))

        for source in sources:
            if (topic := source.topic) is None:
                source.topic = 'main'
            if not isinstance(options := source.options, ImageInConfig.Source.Options):
                source.options = options = ImageInConfig.Source.Options() if options is None else ImageInConfig.Source.Options(options)
            if any((option := o) not in ('loop', 'recursive', 'pattern', 'region', 'maxfps') for o in options):
                raise ValueError(f'unknown option {option!r} in {source!r}')

        if len(set(source.topic for source in sources)) != len(sources):
            raise ValueError(f'duplicate image topics in {sources!r}')

        return config

    def init(self, config):
        super().init(FilterConfig(config, sources=None))

    def setup(self, config):
        """Initialize the filter with sources and start polling thread."""
        self.config = config
        self.frame_id = -1
        self.queues = {}                # topic -> list[path]
        self.processed = {}             # topic -> set[path]
        self.loop_counts = {}           # topic -> int (remaining loops)
        self.stop_event = Event()
        
        # FPS control variables
        self.ns_per_maxfps = {}         # topic -> int (nanoseconds per maxfps)
        self.tmaxfps = {}               # topic -> int (last maxfps timestamp)
        
        # Initialize queues and processed sets for each topic
        for source in config.sources:
            topic = source.topic or 'main'
            if topic not in self.queues:
                self.queues[topic] = []
                self.processed[topic] = set()
                self.loop_counts[topic] = source.options.loop if isinstance(source.options.loop, int) else (0 if source.options.loop else 1)
                
                # Initialize FPS control for this topic
                maxfps = source.options.maxfps or config.maxfps or IMAGE_IN_MAXFPS
                if maxfps is not None:
                    self.ns_per_maxfps[topic] = int(1_000_000_000 // maxfps)
                    self.tmaxfps[topic] = time_ns()
                    logger.info(f"ImageIn topic '{topic}' FPS limited to {maxfps:.1f} fps")
        
        # Load initial images
        self._load_initial_images()
        
        # Start polling thread
        self.poll_thread = Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()
        
        logger.info(f"ImageIn initialized with {len(config.sources)} sources")

    def _load_initial_images(self):
        """Load initial images from all sources into queues."""
        for source in self.config.sources:
            topic = source.topic or 'main'
            try:
                images = self._list_images(source)
                self.queues[topic].extend(images)
                logger.info(f"Loaded {len(images)} images from {source.source} for topic '{topic}'")
            except Exception as e:
                logger.error(f"Failed to load images from {source.source}: {e}")

    def _list_images(self, source) -> List[str]:
        """List image files from the given source."""
        if source.source.startswith('file://'):
            return self._list_local_images(source.source[7:], source.options)
        elif source.source.startswith('s3://'):
            return self._list_s3_images(source.source, source.options)
        elif source.source.startswith('gs://'):
            return self._list_gcs_images(source.source, source.options)
        else:
            raise ValueError(f'Unsupported source scheme: {source.source}')

    def _list_local_images(self, path: str, options) -> List[str]:
        """List image files from local filesystem."""
        if not os.path.exists(path):
            logger.warning(f"Path does not exist: {path}")
            return []

        images = []
        if os.path.isfile(path):
            if is_image_file(path) and matches_pattern(path, options.pattern or self.config.pattern):
                images.append(path)
        else:
            # Directory
            pattern = os.path.join(path, '**' if (options.recursive or self.config.recursive) else '*')
            for file_path in glob.glob(pattern, recursive=(options.recursive or self.config.recursive)):
                if os.path.isfile(file_path) and is_image_file(file_path) and matches_pattern(file_path, options.pattern or self.config.pattern):
                    images.append(file_path)

        return sorted(images)

    def _list_s3_images(self, s3_uri: str, options) -> List[str]:
        """List image files from S3 bucket."""
        if not HAS_BOTO3:
            logger.error("boto3 is required for S3 support. Install with: pip install boto3")
            return []

        try:
            bucket, prefix = parse_s3_uri(s3_uri)
            s3_client = boto3.client('s3', region_name=options.region)

            images = []
            paginator = s3_client.get_paginator('list_objects_v2')

            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        if is_image_file(key) and matches_pattern(key, options.pattern or self.config.pattern):
                            images.append(f"s3://{bucket}/{key}")

            return sorted(images)
        except Exception as e:
            logger.error(f"Failed to list S3 images from {s3_uri}: {e}")
            return []

    def _list_gcs_images(self, gs_uri: str, options) -> List[str]:
        """List image files from Google Cloud Storage."""
        if not HAS_GCS:
            logger.error("google-cloud-storage is required for GCS support. Install with: pip install google-cloud-storage")
            return []

        try:
            # Parse GCS URI
            bucket, prefix = parse_gcs_uri(gs_uri)
            
            # Use google-cloud-storage client
            client = storage.Client()
            bucket = client.bucket(bucket)
            
            images = []
            for blob in bucket.list_blobs(prefix=prefix):
                if is_image_file(blob.name) and matches_pattern(blob.name, options.pattern or self.config.pattern):
                    images.append(f"gs://{bucket.name}/{blob.name}")
                            
            return sorted(images)
        except Exception as e:
            logger.error(f"Failed to list GCS images from {gs_uri}: {e}")
            return []

    def _load_image(self, path: str) -> Optional[np.ndarray]:
        """Load image from path (local or cloud)."""
        try:
            if path.startswith("s3://"):
                if not HAS_BOTO3:
                    logger.error("boto3 is required for S3 support")
                    return None
                bucket, key = parse_s3_uri(path)
                s3_client = boto3.client('s3')
                response = s3_client.get_object(Bucket=bucket, Key=key)
                data = response['Body'].read()
                arr = np.frombuffer(data, np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_COLOR)
            elif path.startswith("gs://"):
                if not HAS_GCS:
                    logger.error("google-cloud-storage is required for GCS support")
                    return None
                # Parse GCS URI
                bucket, key = parse_gcs_uri(path)
                
                # Use google-cloud-storage client
                client = storage.Client()
                bucket = client.bucket(bucket)
                blob = bucket.blob(key)
                data = blob.download_as_bytes()
                arr = np.frombuffer(data, np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_COLOR)
            else:
                return cv2.imread(path)
        except Exception as e:
            logger.error(f"Failed to load image {path}: {e}")
            return None

    def _poll_loop(self):
        """Background thread that polls for new images."""
        poll_interval = self.config.poll_interval or IMAGE_IN_POLL_INTERVAL
        
        while not self.stop_event.is_set():
            try:
                for source in self.config.sources:
                    topic = source.topic or 'main'
                    new_images = self._list_images(source)
                    # Add only new images that haven't been processed
                    for img_path in new_images:
                        if img_path not in self.processed[topic]:
                            self.queues[topic].append(img_path)

            except Exception as e:
                logger.error(f"Error in polling loop: {e}")

            # Sleep for poll interval
            self.stop_event.wait(poll_interval)

    def _wait_for_fps(self, topic: str) -> bool:
        """Wait for FPS timing if maxfps is set for this topic. Returns True if frame should be sent."""
        if topic not in self.ns_per_maxfps:
            return True  # No FPS limit for this topic
            
        t = time_ns()
        ns_per_maxfps = self.ns_per_maxfps[topic]
        tmaxfps = self.tmaxfps[topic]
        
        # Check if enough time has passed since last frame
        if (tdiff := t - tmaxfps) < ns_per_maxfps:
            # Not enough time has passed, skip this frame
            return False
            
        # Update the timestamp for next frame
        self.tmaxfps[topic] = tmaxfps + (tdiff // ns_per_maxfps) * ns_per_maxfps
        return True

    def process(self, frames):
        """Return a callable that provides the next frame when called."""
        def get_next_frame():
            out = {}

            for topic, queue in self.queues.items():
                if not queue:
                    # Check if we should loop
                    source = next((s for s in self.config.sources if (s.topic or 'main') == topic), None)
                    if source and (source.options.loop or self.config.loop):
                        if source.options.loop is True or self.config.loop is True:
                            # Infinite loop - reload all images
                            self._reload_images_for_topic(topic)
                        elif self.loop_counts[topic] > 0:
                            # Finite loop - reload and decrement count
                            self._reload_images_for_topic(topic)
                            self.loop_counts[topic] -= 1
                        else:
                            continue
                    else:
                        continue

                if queue:
                    # Check FPS timing before sending frame
                    if not self._wait_for_fps(topic):
                        continue  # Skip this frame due to FPS limit
                        
                    path = queue.pop(0)
                    self.processed[topic].add(path)

                    img = self._load_image(path)
                    if img is None:
                        continue

                    self.frame_id += 1
                    meta = {
                        'id': self.frame_id,
                        'src': path,
                        'ts': time()
                    }
                    out[topic] = Frame(img, {'meta': meta}, format='BGR')

            return out or None

        return get_next_frame

    def _reload_images_for_topic(self, topic: str):
        """Reload all images for a topic (for looping)."""
        for source in self.config.sources:
            if (source.topic or 'main') == topic:
                try:
                    images = self._list_images(source)
                    self.queues[topic].extend(images)
                    # Clear processed set for this topic to allow reprocessing
                    self.processed[topic].clear()
                    logger.info(f"Reloaded {len(images)} images for topic '{topic}'")
                except Exception as e:
                    logger.error(f"Failed to reload images for topic '{topic}': {e}")
                break

    def shutdown(self):
        """Clean up resources."""
        self.stop_event.set()
        if hasattr(self, 'poll_thread'):
            self.poll_thread.join(timeout=5)
        logger.info(f"ImageIn sent {self.frame_id + 1} frames; shutting down.")