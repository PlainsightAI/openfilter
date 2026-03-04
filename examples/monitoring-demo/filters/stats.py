"""Filter that computes brightness statistics and passes frames through."""

import logging

import numpy as np

from openfilter.filter_runtime.filter import Filter, Frame

logger = logging.getLogger(__name__)


class StatsFilter(Filter):
    """Computes mean brightness and logs every 30 frames. Passthrough."""

    def setup(self, config):
        self._count = 0
        self._brightness_sum = 0.0

    def process(self, frames: dict[str, Frame]) -> dict[str, Frame]:
        self._count += 1
        for topic, frame in frames.items():
            if not topic.startswith('_') and frame.has_image:
                brightness = float(np.mean(frame.image))
                self._brightness_sum += brightness
                if self._count % 30 == 0:
                    avg = self._brightness_sum / self._count
                    logger.info(
                        f"[StatsFilter] frame={self._count} "
                        f"brightness={brightness:.1f} avg={avg:.1f}"
                    )
        return frames


if __name__ == '__main__':
    StatsFilter.run()
