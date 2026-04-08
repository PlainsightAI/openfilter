#!/usr/bin/env python
"""Unit tests for Filter frame accumulation (batch_size > 1) support."""

import logging
import os
import threading
import time
import unittest
from unittest.mock import MagicMock

from openfilter.filter_runtime import Filter, FilterConfig, Frame
from openfilter.filter_runtime.utils import setLogLevelGlobal

logger = logging.getLogger(__name__)
log_level = int(getattr(logging, (os.getenv("LOG_LEVEL") or "CRITICAL").upper()))
setLogLevelGlobal(log_level)


class CountingBatchFilter(Filter):
    """Filter that collects batches and records what process_batch receives."""

    def setup(self, config):
        self.received_batches = []

    def process(self, frames):
        return frames

    def process_batch(self, batch):
        self.received_batches.append(batch)
        results = []
        for frames in batch:
            merged_data = {}
            for topic, frame in frames.items():
                if hasattr(frame, "data") and isinstance(frame.data, dict):
                    merged_data.update(frame.data)
            results.append(Frame(merged_data) if merged_data else None)
        return results


class FallbackBatchFilter(Filter):
    """Filter that does NOT override process_batch — tests default fallback."""

    def setup(self, config):
        self.process_calls = []

    def process(self, frames):
        self.process_calls.append(frames)
        return frames


class TestFilterConfigValidation(unittest.TestCase):
    def test_batch_size_default_is_1(self):
        config = FilterConfig(id="test")
        normalized = Filter.normalize_config(config)
        self.assertIsNone(normalized.get("batch_size"))

    def test_batch_size_valid(self):
        config = FilterConfig(id="test", batch_size=4)
        normalized = Filter.normalize_config(config)
        self.assertEqual(normalized.batch_size, 4)

    def test_batch_size_string_coerced(self):
        config = FilterConfig(id="test", batch_size="8")
        normalized = Filter.normalize_config(config)
        self.assertEqual(normalized.batch_size, 8)

    def test_batch_size_invalid_zero(self):
        config = FilterConfig(id="test", batch_size=0)
        with self.assertRaises(ValueError):
            Filter.normalize_config(config)

    def test_batch_size_invalid_negative(self):
        config = FilterConfig(id="test", batch_size=-1)
        with self.assertRaises(ValueError):
            Filter.normalize_config(config)

    def test_accumulate_timeout_valid(self):
        config = FilterConfig(id="test", accumulate_timeout_ms=200.0)
        normalized = Filter.normalize_config(config)
        self.assertEqual(normalized.accumulate_timeout_ms, 200.0)

    def test_accumulate_timeout_invalid_zero(self):
        config = FilterConfig(id="test", accumulate_timeout_ms=0)
        with self.assertRaises(ValueError):
            Filter.normalize_config(config)

    def test_accumulate_timeout_invalid_negative(self):
        config = FilterConfig(id="test", accumulate_timeout_ms=-50)
        with self.assertRaises(ValueError):
            Filter.normalize_config(config)


class TestBatchAccumulation(unittest.TestCase):
    """Test the accumulation logic directly via process_frames."""

    def _make_filter(
        self, batch_size=1, timeout_ms=100.0, filter_cls=CountingBatchFilter
    ):
        config = FilterConfig(
            id="test-batch",
            batch_size=batch_size,
            accumulate_timeout_ms=timeout_ms,
        )
        stop_evt = threading.Event()
        f = filter_cls(config, stop_evt)

        f.mq = MagicMock()
        f.mq.metrics = {}
        f.mq.sender = None
        f.logger = MagicMock()
        f.logger.enabled = False
        f._is_last_filter = False
        f._metadata_queue = MagicMock()
        f._metadata_queue.put_nowait = MagicMock()
        f.emitter = None
        f.setup(config)
        return f

    def test_batch_size_1_passthrough(self):
        f = self._make_filter(batch_size=1, filter_cls=FallbackBatchFilter)
        frames = {"main": Frame({"val": 1})}

        result = f.process_frames(frames)

        self.assertIsNotNone(result)
        self.assertIn("main", result)
        self.assertEqual(len(f.process_calls), 1)

    def test_accumulate_returns_none_until_full(self):
        f = self._make_filter(batch_size=3)
        frame1 = {"main": Frame({"val": 1})}
        frame2 = {"main": Frame({"val": 2})}

        self.assertIsNone(f.process_frames(frame1))
        self.assertIsNone(f.process_frames(frame2))
        self.assertEqual(len(f.received_batches), 0)

    def test_accumulate_fires_on_full_batch(self):
        f = self._make_filter(batch_size=3)

        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        result = f.process_frames({"main": Frame({"val": 3})})

        self.assertIsNotNone(result)
        self.assertEqual(len(f.received_batches), 1)
        self.assertEqual(len(f.received_batches[0]), 3)

    def test_accumulate_multiple_batches(self):
        f = self._make_filter(batch_size=2)

        f.process_frames({"main": Frame({"val": 1})})
        result1 = f.process_frames({"main": Frame({"val": 2})})
        self.assertIsNotNone(result1)
        self.assertEqual(len(f.received_batches), 1)

        f.process_frames({"main": Frame({"val": 3})})
        result2 = f.process_frames({"main": Frame({"val": 4})})
        self.assertIsNotNone(result2)
        self.assertEqual(len(f.received_batches), 2)

    def test_default_process_batch_calls_process_individually(self):
        f = self._make_filter(batch_size=2, filter_cls=FallbackBatchFilter)

        f.process_frames({"main": Frame({"val": 1})})
        result = f.process_frames({"main": Frame({"val": 2})})

        self.assertIsNotNone(result)
        self.assertEqual(len(f.process_calls), 2)

    def test_timeout_sets_flush_flag(self):
        f = self._make_filter(batch_size=5, timeout_ms=50.0)

        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})

        self.assertEqual(len(f._frame_buffer), 2)
        self.assertFalse(f._batch_flush_event.is_set())

        time.sleep(0.1)

        self.assertTrue(f._batch_flush_event.is_set())

    def test_flush_returns_partial_batch(self):
        f = self._make_filter(batch_size=5, timeout_ms=50.0)

        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})

        time.sleep(0.1)

        result = f._process_batch_flush()
        self.assertIsNotNone(result)
        self.assertEqual(len(f.received_batches), 1)
        self.assertEqual(len(f.received_batches[0]), 2)
        self.assertEqual(len(f._frame_buffer), 0)

    def test_flush_returns_none_when_empty(self):
        f = self._make_filter(batch_size=5, timeout_ms=50.0)

        result = f._process_batch_flush()
        self.assertIsNone(result)

    def test_timer_cancelled_on_full_batch(self):
        f = self._make_filter(batch_size=2, timeout_ms=50.0)

        f.process_frames({"main": Frame({"val": 1})})
        self.assertIsNotNone(f._batch_timer)

        f.process_frames({"main": Frame({"val": 2})})
        self.assertIsNone(f._batch_timer)

    def test_timer_cancelled_on_cleanup(self):
        f = self._make_filter(batch_size=5, timeout_ms=1000.0)

        f.process_frames({"main": Frame({"val": 1})})
        self.assertIsNotNone(f._batch_timer)

        f._cancel_batch_timer()
        self.assertIsNone(f._batch_timer)

    def test_batch_with_none_results_skipped(self):
        """process_batch returning [None, Frame, None] should use the last non-None."""

        class SelectiveBatchFilter(Filter):
            def setup(self, config):
                pass

            def process_batch(self, batch):
                return [None, Frame({"selected": True}), None]

            def process(self, frames):
                return frames

        f = self._make_filter(batch_size=3, filter_cls=SelectiveBatchFilter)

        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        result = f.process_frames({"main": Frame({"val": 3})})

        self.assertIsNotNone(result)
        self.assertIn("main", result)

    def test_batch_all_none_results(self):
        """process_batch returning all Nones should return None (sink)."""

        class SinkBatchFilter(Filter):
            def setup(self, config):
                pass

            def process_batch(self, batch):
                return [None] * len(batch)

            def process(self, frames):
                return frames

        f = self._make_filter(batch_size=2, filter_cls=SinkBatchFilter)

        f.process_frames({"main": Frame({"val": 1})})
        result = f.process_frames({"main": Frame({"val": 2})})

        self.assertIsNone(result)

    def test_thread_safety_concurrent_accumulation(self):
        f = self._make_filter(batch_size=10, timeout_ms=500.0)
        errors = []

        def add_frame(idx):
            try:
                f.process_frames({"main": Frame({"val": idx})})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_frame, args=(i,)) for i in range(9)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        with f._batch_lock:
            self.assertEqual(len(f._frame_buffer), 9)


class TestBatchSizeOneBackwardCompat(unittest.TestCase):
    """Verify batch_size=1 (default) preserves exact existing behavior."""

    def _make_filter(self):
        config = FilterConfig(id="test-compat")
        stop_evt = threading.Event()
        f = FallbackBatchFilter(config, stop_evt)

        f.mq = MagicMock()
        f.mq.metrics = {}
        f.mq.sender = None
        f.logger = MagicMock()
        f.logger.enabled = False
        f._is_last_filter = False
        f._metadata_queue = MagicMock()
        f._metadata_queue.put_nowait = MagicMock()
        f.emitter = None
        f.setup(config)
        return f

    def test_no_accumulation_state_used(self):
        f = self._make_filter()
        self.assertEqual(f._batch_size, 1)
        self.assertEqual(len(f._frame_buffer), 0)

    def test_process_called_directly(self):
        f = self._make_filter()
        frames = {"main": Frame({"val": 42})}
        result = f.process_frames(frames)

        self.assertIsNotNone(result)
        self.assertEqual(len(f.process_calls), 1)
        self.assertIs(f.process_calls[0], frames)

    def test_no_timer_started(self):
        f = self._make_filter()
        f.process_frames({"main": Frame({"val": 1})})
        self.assertIsNone(f._batch_timer)


if __name__ == "__main__":
    unittest.main()
