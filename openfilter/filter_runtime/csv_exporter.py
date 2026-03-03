"""CSV metrics exporter for the sink (last) filter.

Accumulates raw metric samples per frame and flushes computed statistics
(avg, std, p95, 95% CI) to a CSV file at a configurable interval.

All disk I/O happens in a daemon background thread so the main processing
loop is never blocked.

Enabled via two FILTER_* env vars (parsed by Filter.get_config()):
    FILTER_METRICS_CSV_PATH     - path to CSV file (enables the feature)
    FILTER_METRICS_CSV_INTERVAL - flush interval in seconds (default: 60)
"""

import csv
import logging
import math
import os
import statistics
import threading
from datetime import datetime, timezone

__all__ = ['CSVMetricsExporter']

logger = logging.getLogger(__name__)

# Maximum number of data rows kept in the CSV (rolling window).
# At the default 60s interval this covers the last hour.
_MAX_ROWS = 60

# Metric names and corresponding CSV column families.
# For each metric, 5 columns are emitted: avg, std, p95, ci_lower, ci_upper.
_METRICS = [
    'fps',
    'cpu',
    'mem',
    'lat_in_ms',
    'lat_out_ms',
    'process_time_ms',
    'frame_total_time_ms',
    'frame_avg_time_ms',
    'frame_std_time_ms',
]

_HEADER = ['timestamp', 'pipeline_id', 'filter_id', 'n_samples']
for _m in _METRICS:
    _HEADER += [f'{_m}_avg', f'{_m}_std', f'{_m}_p95', f'{_m}_ci_lower', f'{_m}_ci_upper']


def _compute_stats(values: list[float]) -> tuple:
    """Return (avg, std, p95, ci_lower, ci_upper) for a list of floats.

    If fewer than 2 samples are available, std/p95/ci fields are empty string
    so the CSV stays clean to open in Excel.
    """
    n = len(values)
    if n == 0:
        return ('', '', '', '', '')

    avg = statistics.mean(values)

    if n < 2:
        return (avg, '', '', '', '')

    std = statistics.stdev(values)
    sorted_vals = sorted(values)
    p95 = sorted_vals[int(0.95 * (n - 1))]
    margin = 1.96 * std / math.sqrt(n)
    ci_lower = avg - margin
    ci_upper = avg + margin

    return (avg, std, p95, ci_lower, ci_upper)


class CSVMetricsExporter:
    """Accumulate per-frame metric samples and periodically flush statistics to CSV.

    Usage:
        exporter = CSVMetricsExporter(path='/tmp/metrics.csv', interval_s=60,
                                      pipeline_id='my-pipeline', filter_id='webvis')
        exporter.start()
        # in the frame processing loop:
        exporter.add_sample({'fps': 5.0, 'cpu': 12.3, ...})
        # on shutdown:
        exporter.stop()
    """

    def __init__(self, path: str, interval_s: float, pipeline_id: str, filter_id: str):
        self._path = path
        self._interval_s = interval_s
        self._pipeline_id = pipeline_id
        self._filter_id = filter_id

        self._lock = threading.Lock()
        self._buffer: list[dict] = []
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Create parent directories and start the background flush thread."""
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        self._thread = threading.Thread(target=self._run, daemon=True, name='csv-metrics-exporter')
        self._thread.start()

    def add_sample(self, sample: dict) -> None:
        """Append a per-frame sample dict to the buffer (called from the main thread)."""
        with self._lock:
            self._buffer.append(sample)

    def stop(self) -> None:
        """Signal the background thread to stop and perform a final flush."""
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_s + 5)
        # Final flush in case the thread did not get to run after stop was set.
        self._flush()

    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Background daemon loop: sleep interval_s, flush, repeat."""
        while not self._stop_evt.wait(timeout=self._interval_s):
            self._flush()

    def _flush(self) -> None:
        """Swap the buffer, compute statistics, and append one CSV row."""
        with self._lock:
            if not self._buffer:
                return
            samples, self._buffer = self._buffer, []

        n = len(samples)
        row: list = [
            datetime.now(tz=timezone.utc).isoformat(timespec='seconds'),
            self._pipeline_id,
            self._filter_id,
            n,
        ]

        for metric in _METRICS:
            values = [s[metric] for s in samples if metric in s and s[metric] is not None]
            stats = _compute_stats([float(v) for v in values]) if values else ('', '', '', '', '')
            row.extend(stats)

        try:
            # Read existing rows, append new one, keep only the last _MAX_ROWS.
            existing: list[list] = []
            if os.path.exists(self._path):
                with open(self._path, newline='') as fh:
                    reader = csv.reader(fh)
                    next(reader, None)  # skip header
                    existing = list(reader)
            existing.append(row)
            existing = existing[-_MAX_ROWS:]

            with open(self._path, 'w', newline='') as fh:
                writer = csv.writer(fh)
                writer.writerow(_HEADER)
                writer.writerows(existing)
            logger.debug(f'[csv_exporter] flushed {n} samples -> {self._path!r} ({len(existing)} rows kept)')
        except Exception as exc:
            logger.error(f'[csv_exporter] failed to write {self._path!r}: {exc}')
