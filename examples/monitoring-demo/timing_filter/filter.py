"""Passthrough filter that logs timing metadata to verify instrumentation."""

import json
import logging

from openfilter.filter_runtime.filter import Filter, Frame

logger = logging.getLogger(__name__)


class TimingFilter(Filter):
    """Passthrough filter that logs filter_timings metadata every 30 frames."""

    def setup(self, config):
        self._count = 0

    def process(self, frames: dict[str, Frame]) -> dict[str, Frame]:
        self._count += 1
        for topic, frame in frames.items():
            if topic.startswith('_'):
                continue
            timings = frame.data.get('meta', {}).get('filter_timings')
            if timings and self._count % 30 == 0:
                logger.info(
                    f"[frame {self._count}] filter_timings: "
                    f"{json.dumps(timings, default=str)}"
                )
        return frames


if __name__ == '__main__':
    TimingFilter.run()
