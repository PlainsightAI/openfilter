"""Filter that resizes frames to a target resolution."""

import logging
import os

import cv2

from openfilter.filter_runtime.filter import Filter, Frame

logger = logging.getLogger(__name__)


class ResizeFilter(Filter):
    """Resizes each frame to RESIZE_WIDTH x RESIZE_HEIGHT (default 320x240)."""

    def setup(self, config):
        self._width = int(os.environ.get('RESIZE_WIDTH', 320))
        self._height = int(os.environ.get('RESIZE_HEIGHT', 240))
        logger.info(f"ResizeFilter: target size {self._width}x{self._height}")

    def process(self, frames: dict[str, Frame]) -> dict[str, Frame]:
        for topic, frame in list(frames.items()):
            if not topic.startswith('_') and frame.has_image:
                resized = cv2.resize(frame.image, (self._width, self._height))
                frames[topic] = Frame(resized, frame)
        return frames


if __name__ == '__main__':
    ResizeFilter.run()
