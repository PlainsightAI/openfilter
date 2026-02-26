"""Filter that converts frames to grayscale."""

import logging

from openfilter.filter_runtime.filter import Filter, Frame

logger = logging.getLogger(__name__)


class GrayscaleFilter(Filter):
    """Converts each frame to grayscale using Frame.gray property."""

    def setup(self, config):
        self._count = 0

    def process(self, frames: dict[str, Frame]) -> dict[str, Frame]:
        self._count += 1
        for topic, frame in list(frames.items()):
            if not topic.startswith('_') and frame.has_image:
                frames[topic] = frame.gray
        return frames


if __name__ == '__main__':
    GrayscaleFilter.run()
