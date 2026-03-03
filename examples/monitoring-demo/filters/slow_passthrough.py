"""Filter with configurable delay, for testing parallel/fan-out topologies."""

import logging
import os
import time

from openfilter.filter_runtime.filter import Filter, Frame

logger = logging.getLogger(__name__)


class SlowPassthrough(Filter):
    """Pass frames through with a configurable sleep.

    Using the same class for two parallel branches triggers Bug 1
    (metric label collision) because filter_name is identical.

    Config:
        sleep_ms: delay in milliseconds (default 50). Also settable
                  via the SLEEP_MS environment variable.
    """

    def setup(self, config):
        self._sleep_sec = float(os.environ.get('SLEEP_MS', config.get('sleep_ms', 50))) / 1000.0
        logger.info(f"SlowPassthrough: sleep_ms={self._sleep_sec * 1000:.0f}")

    def process(self, frames: dict[str, Frame]) -> dict[str, Frame]:
        time.sleep(self._sleep_sec)
        return frames


if __name__ == '__main__':
    SlowPassthrough.run()
