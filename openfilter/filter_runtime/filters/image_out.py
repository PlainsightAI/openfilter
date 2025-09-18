import logging
import os
import re
from pathlib import Path
from time import strftime
from typing import Any, Literal

import cv2

from openfilter.filter_runtime.utils import json_getval, dict_without, split_commas_maybe, hide_uri_users_and_pwds, once

__all__ = ['ImageWriter']

logger = logging.getLogger(__name__)

# Environment variables
IMAGE_OUT_BGR = bool(json_getval((os.getenv('IMAGE_OUT_BGR') or 'true').lower()))
IMAGE_OUT_QUALITY = int(os.getenv('IMAGE_OUT_QUALITY') or '95')  # JPEG quality 1-100
IMAGE_OUT_COMPRESSION = int(os.getenv('IMAGE_OUT_COMPRESSION') or '6')  # PNG compression 0-9

# File extension patterns
re_file = re.compile(r'^file://')
is_file = lambda name: bool(re_file.match(name))

# Supported image formats
SUPPORTED_FORMATS = {'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'}


class ImageWriter:
    def __init__(self,
        output: str,
        *,
        bgr: bool | None = None,
        format: str | None = None,
        quality: int | None = None,
        compression: int | None = None
    ):
        """Write images to files in various formats.

        Args:
            output: Destination file path, can include strftime formatting and %d for frame numbers.
                   Examples: 'file:///path/to/image_%Y%m%d_%H%M%S_%d.png'
            
            bgr: True means images are in BGR mode, False means RGB. Default from env var.
            
            format: Image format override. If None, determined from file extension.
                    Supported: 'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'
            
            quality: JPEG quality (1-100). Only used for JPEG format. Default from env var.
            
            compression: PNG compression level (0-9). Only used for PNG format. Default from env var.
        """
        
        if not is_file(output):
            raise ValueError(f'ImageWriter only supports file:// outputs, not {output!r}')
        
        self.output = output[7:]  # Remove 'file://' prefix
        self.is_bgr = bool(IMAGE_OUT_BGR if bgr is None else bgr)
        self.quality = IMAGE_OUT_QUALITY if quality is None else quality
        self.compression = IMAGE_OUT_COMPRESSION if compression is None else compression
        
        # Determine format from file extension if not specified
        if format is None:
            ext = Path(self.output).suffix.lower().lstrip('.')
            if ext not in SUPPORTED_FORMATS:
                raise ValueError(f'Unsupported file extension: {ext}. Supported: {", ".join(SUPPORTED_FORMATS)}')
            self.format = ext
        else:
            if format.lower() not in SUPPORTED_FORMATS:
                raise ValueError(f'Unsupported format: {format}. Supported: {", ".join(SUPPORTED_FORMATS)}')
            self.format = format.lower()
        
        # Normalize format names
        if self.format in ('jpg', 'jpeg'):
            self.format = 'jpg'
        elif self.format in ('tiff', 'tif'):
            self.format = 'tiff'
        
        self.frame_count = 0
        
        logger.info(f'image writer: {self.output} ({self.format})')

    def start(self):  # idempotent and safe to call whenever
        pass

    def stop(self):  # idempotent and safe to call whenever
        pass

    def write(self, image, frame_id: str | None = None):
        """Write an image to file.
        
        Args:
            image: numpy array image data
            frame_id: Optional frame identifier for logging
        """
        if image is None:
            raise RuntimeError('cannot write None image')
        
        # Convert RGB to BGR if needed
        if not self.is_bgr and len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        
        # Generate filename with formatting
        filename = self._generate_filename(frame_id)
        
        # Ensure directory exists
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        
        # Write image based on format
        success = False
        if self.format == 'jpg':
            success = cv2.imwrite(filename, image, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        elif self.format == 'png':
            success = cv2.imwrite(filename, image, [cv2.IMWRITE_PNG_COMPRESSION, self.compression])
        elif self.format == 'bmp':
            success = cv2.imwrite(filename, image)
        elif self.format == 'tiff':
            success = cv2.imwrite(filename, image)
        elif self.format == 'webp':
            success = cv2.imwrite(filename, image, [cv2.IMWRITE_WEBP_QUALITY, self.quality])
        else:
            success = cv2.imwrite(filename, image)
        
        if not success:
            raise RuntimeError(f'failed to write image to {filename}')
        
        self.frame_count += 1
        logger.debug(f'wrote image: {filename} ({frame_id or "unknown"})')

    def _generate_filename(self, frame_id: str | None = None):
        """Generate filename with timestamp and frame number formatting."""
        filename = strftime(self.output)
        
        # Replace %d with frame count if present
        if '%d' in filename:
            filename = filename.replace('%d', f'{self.frame_count:06d}')
        
        # Add frame_id to filename if provided and no %d was used
        elif frame_id is not None and '%d' not in self.output:
            name, ext = os.path.splitext(filename)
            filename = f'{name}_{frame_id}{ext}'
        
        return filename


# --- CUT HERE ---------------------------------------------------------------------------------------------------------

from openfilter.filter_runtime.filter import FilterConfig, Filter
from openfilter.filter_runtime.utils import adict, split_commas_maybe

__all__ = __all__ + ['ImageOutConfig', 'ImageOut']


class ImageOutConfig(FilterConfig):
    class Output(adict):
        class Options(adict):
            bgr: bool | None
            format: str | None
            quality: int | None
            compression: int | None

        output: str
        topic: str | None
        options: Options | None

    outputs: str | list[str | Output]

    # setting these will make them default for all images (overridable individually)
    bgr: bool | None
    format: str | None
    quality: int | None
    compression: int | None


class ImageOut(Filter):
    """Single or multiple image output filter. Images are assigned to topics via the ';' mapping character in `outputs`.
    The default topic mapping if nothing specified is 'main'. Topics can be sent to multiple image outputs, so the same
    topic can appear multiple times in the outputs. '!' allows setting options directly in the output string.

    config:
        outputs:
            The destination(s) of the image(s), comma delimited, must be file://. The filename can include strftime
            formatting and %d for frame numbers.

            Examples:
                'file:///path/to/images_%Y%m%d_%H%M%S_%d.png!format=png!quality=95, file:///other/path;camera2'

                    is the same as

                ['file:///path/to/images_%Y%m%d_%H%M%S_%d.png!format=png!quality=95', 'file:///other/path;camera2']

                    is the same as

                [{'output': 'file:///path/to/images_%Y%m%d_%H%M%S_%d.png', 'topic'?: 'main', 
                  'options'?: {'format': 'png', 'quality': 95}},
                 {'output': 'file:///other/path', 'topic'?: 'camera2'}]

            `outputs` individual options (text appended after output, e.g. 'file:///myimage.png!no-bgr!quality=80'):
                '!bgr', '!no-bgr':
                    Set `bgr` option for this output.

                '!format=png', '!format=jpg':
                    Set `format` option for this output.

                '!quality=95':
                    Set `quality` option for this output (JPEG only, 1-100).

                '!compression=6':
                    Set `compression` option for this output (PNG only, 0-9).

        bgr:
            True means images are in BGR format, False means RGB. Set here to apply to all outputs or
            can be set individually per output. Global env var default IMAGE_OUT_BGR.

        format:
            Image format override. If None, determined from file extension. Set here to apply to all outputs or
            can be set individually per output. Supported: 'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'

        quality:
            JPEG quality (1-100). Only used for JPEG format. Set here to apply to all outputs or
            can be set individually per output. Global env var default IMAGE_OUT_QUALITY.

        compression:
            PNG compression level (0-9). Only used for PNG format. Set here to apply to all outputs or
            can be set individually per output. Global env var default IMAGE_OUT_COMPRESSION.

    Environment variables:
        IMAGE_OUT_BGR
        IMAGE_OUT_QUALITY
        IMAGE_OUT_COMPRESSION
    """

    FILTER_TYPE = 'Output'

    @classmethod
    def normalize_config(cls, config):
        outputs = split_commas_maybe(config.get('outputs'))  # we do not assume how Filter will normalize sources/outputs in the future
        config  = ImageOutConfig(super().normalize_config(dict_without(config, 'outputs')))

        if outputs is not None:
            config.outputs = outputs

        if not config.sources:
            raise ValueError('must specify at least one source')
        if not outputs:
            raise ValueError('must specify at least one output')

        for idx, output in enumerate(outputs):
            if isinstance(output, dict):
                if not isinstance(output, ImageOutConfig.Output):
                    outputs[idx] = ImageOutConfig.Output(output)  # because silly user might have passed in dicts

            else:
                output, topic   = Filter.parse_topics(output, 1, False)
                output, options = Filter.parse_options(output)
                # Allow wildcard topics for ImageOut (e.g., 'face_*')
                topic_name = topic and topic[0]
                outputs[idx]    = ImageOutConfig.Output(output=output, topic=topic_name,
                    options=ImageOutConfig.Output.Options(options))

        for output in outputs:
            if (topic := output.topic) is None:
                output.topic = 'main'
            if not isinstance(options := output.options, ImageOutConfig.Output.Options):
                output.options = options = ImageOutConfig.Output.Options() if options is None else ImageOutConfig.Output.Options(options)

            for option, value in list(options.items()):
                if option not in ('bgr', 'format', 'quality', 'compression'):
                    once(logger.warning, f'unknown image output option: {option}', t=60*60)
                    del options[option]

        if not all(is_file(o := output.output) for output in outputs):
            raise ValueError(f'this filter only accepts file:// outputs, not {o!r}')

        return config

    def init(self, config):
        super().init(FilterConfig(config, outputs=None))

    def create_writers(self):
        self.tops_n_writers = [(top, ImageWriter(out, **opts)) for top, out, opts in self.tops_n_outs_n_opts]

    def setup(self, config):
        default_options = {'bgr': config.bgr, 'format': config.format, 'quality': config.quality, 'compression': config.compression}
        self.tops_n_outs_n_opts = tops_n_outs_n_opts = []

        for output in config.outputs:
            topic   = output.get('topic') or 'main'
            options = output.options
            options = adict({**default_options, **(options or {})})
            output  = output.output

            tops_n_outs_n_opts.append((topic, output, options))

        self.create_writers()

        for _, writer in self.tops_n_writers:
            writer.start()

    def shutdown(self):
        if self.tops_n_writers is not None:
            for _, writer in self.tops_n_writers:
                writer.stop()

    def process(self, frames):
        for topic, writer in self.tops_n_writers:
            # Support wildcard topic filtering for ImageOut
            matching_frames = {}
            if '*' in topic:
                # Handle wildcard topics (e.g., 'face_*')
                import fnmatch
                for frame_topic, frame in frames.items():
                    if fnmatch.fnmatch(frame_topic, topic):
                        matching_frames[frame_topic] = frame
            else:
                # Handle exact topic match
                if topic in frames:
                    matching_frames[topic] = frames[topic]
            
            # Process all matching frames
            for frame_topic, frame in matching_frames.items():
                if (image := frame.bgr.image) is None:
                    once(logger.warning, f'image topic {frame_topic!r} has no image data', t=60*15)
                    continue
                
                # Use frame data to generate a unique identifier if available
                frame_id = None
                if frame.data:
                    # Try to get frame ID from metadata
                    meta = frame.data.get('meta', {})
                    frame_id = meta.get('frame_id') or meta.get('id') or str(meta.get('timestamp', ''))
                
                # Add topic info to frame_id to make filenames unique
                if frame_id is None:
                    frame_id = frame_topic
                else:
                    frame_id = f"{frame_topic}_{frame_id}"
                
                writer.write(image, frame_id)
            
            # Warning if no frames matched (only for non-wildcard topics)
            if '*' not in topic and not matching_frames:
                once(logger.warning, f'expected image topic {topic!r} not found or empty among: {", ".join(frames.keys())}', t=60*15)


if __name__ == '__main__':
    ImageOut.run()
