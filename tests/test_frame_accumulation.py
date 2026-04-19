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

    def test_watcher_started_on_partial_batch(self):
        f = self._make_filter(batch_size=2, timeout_ms=50.0)

        f.process_frames({"main": Frame({"val": 1})})
        self.assertIsNotNone(f._batch_watcher)
        self.assertTrue(f._batch_watcher.is_alive())

        f.process_frames({"main": Frame({"val": 2})})
        # Watcher thread stays alive — it's reused across batches.
        self.assertIsNotNone(f._batch_watcher)

    def test_watcher_stopped_on_cleanup(self):
        f = self._make_filter(batch_size=5, timeout_ms=1000.0)

        f.process_frames({"main": Frame({"val": 1})})
        self.assertTrue(f._batch_watcher.is_alive())

        f._stop_batch_watcher()
        f._batch_watcher.join(timeout=1.0)
        self.assertFalse(f._batch_watcher.is_alive())

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

    def test_no_watcher_started_for_single_mode(self):
        f = self._make_filter()
        f.process_frames({"main": Frame({"val": 1})})
        self.assertIsNone(f._batch_watcher)


class TestLoopOnceTimeoutFlush(unittest.TestCase):
    """Integration test: partial batch flushed via timeout inside loop_once."""

    def test_partial_batch_flushed_by_timeout(self):
        """loop_once should flush a partial batch when the watcher timeout fires."""
        config = FilterConfig(
            id="test-loop-flush",
            batch_size=3,
            accumulate_timeout_ms=100.0,
        )
        stop_evt = threading.Event()
        f = CountingBatchFilter(config, stop_evt)

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

        f.mq.send = MagicMock(return_value=True)

        # Set generous source/output timeouts so loop_once doesn't exit early.
        f.sources_timeout = 5000.0
        f.outputs_timeout = 5000.0
        f.exit_after_t = None

        # First two loop_once calls each receive a frame and accumulate it.
        f.mq.recv = MagicMock(return_value={"main": Frame({"val": 1})})
        f.loop_once()
        f.mq.recv = MagicMock(return_value={"main": Frame({"val": 2})})
        f.loop_once()

        # Batch not full yet (need 3), so nothing sent.
        self.assertEqual(len(f.received_batches), 0)
        self.assertFalse(f.mq.send.called)

        # Third loop_once: recv returns None (slow source). The watcher timeout
        # (100ms) fires _batch_flush_event, and loop_once flushes the partial batch.
        f.mq.recv = MagicMock(return_value=None)
        f.loop_once()

        # The partial batch of 2 frames should have been flushed.
        self.assertEqual(len(f.received_batches), 1)
        self.assertEqual(len(f.received_batches[0]), 2)

        # Results should have been sent downstream via mq.send.
        self.assertTrue(f.mq.send.called)

        # Clean up watcher thread.
        f._stop_batch_watcher()


class TestTimerReset(unittest.TestCase):
    """Verify that _reset_batch_timer correctly extends the accumulation window."""

    def _make_filter(self, batch_size, timeout_ms):
        config = FilterConfig(
            id="test-timer-reset",
            batch_size=batch_size,
            accumulate_timeout_ms=timeout_ms,
        )
        stop_evt = threading.Event()
        f = CountingBatchFilter(config, stop_evt)
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

    def test_timer_reset_extends_accumulation_window(self):
        """A new frame arriving mid-sleep must restart the watcher timeout.

        Regression guard for _batch_watcher_loop lines:
            if self._batch_wakeup.is_set():
                self._batch_wakeup.clear()
                continue
        Removing those lines causes a premature flush at the original deadline.
        """
        # batch_size=5 so the batch never completes via accumulation in this test
        f = self._make_filter(batch_size=5, timeout_ms=100.0)

        # Frame 1 at t≈0ms: starts the 100ms watcher timer
        f.process_frames({"main": Frame({"val": 1})})

        # Sleep ~60ms, well inside the original 100ms window
        time.sleep(0.06)

        # Frame 2 at t≈60ms: _reset_batch_timer() sets _batch_wakeup, watcher restarts
        # The new flush deadline is ~60ms + 100ms = ~160ms from start
        f.process_frames({"main": Frame({"val": 2})})

        # At t≈100ms (original deadline): flush must NOT have fired yet.
        # The watcher's first sleep expires here; seeing _batch_wakeup set it restarts
        # for another full timeout rather than flushing immediately.
        time.sleep(0.04)
        self.assertFalse(
            f._batch_flush_event.is_set(),
            "flush fired at the original deadline; timer reset is not working",
        )

        # Watcher restarts at t≈100ms; expected flush at t≈200ms.  Wait up to
        # 500ms so the test tolerates scheduler jitter on loaded CI runners.
        fired = f._batch_flush_event.wait(timeout=0.5)
        self.assertTrue(fired, "flush never fired after the reset deadline")

        f._stop_batch_watcher()
        f._batch_watcher.join(timeout=1.0)


class TestFiniShutdownFlush(unittest.TestCase):
    """Verify fini() drains _batch_pending_results before shutting down."""

    def _make_filter(self, batch_size=2):
        config = FilterConfig(
            id="test-fini-flush",
            batch_size=batch_size,
            accumulate_timeout_ms=1000.0,
        )
        stop_evt = threading.Event()
        f = CountingBatchFilter(config, stop_evt)
        f.mq = MagicMock()
        f.mq.metrics = {}
        f.mq.sender = None
        f.mq.send = MagicMock(return_value=True)
        f.mq.destroy = MagicMock()
        f.logger = MagicMock()
        f.logger.enabled = False
        f._is_last_filter = False
        f._metadata_queue = MagicMock()
        f._metadata_queue.put_nowait = MagicMock()
        f.emitter = None
        f.setup(config)
        return f

    def test_fini_drains_pending_results(self):
        """fini() must send every result stashed in _batch_pending_results.

        Regression guard for fini() lines:
            if self._batch_pending_results:
                for pending in self._batch_pending_results:
                    self.mq.send(pending, POLL_TIMEOUT_MS)
                self._batch_pending_results.clear()
        Removing that block causes processed results to be silently dropped on shutdown.
        """
        f = self._make_filter(batch_size=2)

        # Simulate state: two processed results are waiting to be sent (as would
        # happen if loop_once was interrupted between _execute_batch and draining).
        pending1 = {"main": Frame({"val": 10})}
        pending2 = {"main": Frame({"val": 20})}
        f._batch_pending_results.extend([pending1, pending2])

        f.fini()

        # Both pending results must have been handed to mq.send.
        # _frame_buffer is empty, so no additional sends from the partial-batch path.
        self.assertEqual(
            f.mq.send.call_count,
            2,
            f"expected 2 send calls for pending results; got {f.mq.send.call_count}",
        )
        sent_frames = [call.args[0] for call in f.mq.send.call_args_list]
        self.assertIn(pending1, sent_frames)
        self.assertIn(pending2, sent_frames)

        # List must be cleared after fini so results are not double-sent.
        self.assertEqual(len(f._batch_pending_results), 0)


class TestLoopOncePendingResultsDrain(unittest.TestCase):
    """Verify loop_once sends all N results from a full batch, not just the last."""

    def _make_filter(self, batch_size):
        config = FilterConfig(
            id="test-pending-drain",
            batch_size=batch_size,
            accumulate_timeout_ms=1000.0,
        )
        stop_evt = threading.Event()
        f = CountingBatchFilter(config, stop_evt)
        f.mq = MagicMock()
        f.mq.metrics = {}
        f.mq.sender = None
        f.mq.send = MagicMock(return_value=True)
        f.logger = MagicMock()
        f.logger.enabled = False
        f._is_last_filter = False
        f._metadata_queue = MagicMock()
        f._metadata_queue.put_nowait = MagicMock()
        f.emitter = None
        f.sources_timeout = 5000.0
        f.outputs_timeout = 5000.0
        f.exit_after_t = None
        f.setup(config)
        return f

    def test_loop_once_sends_all_batch_results(self):
        """loop_once must drain _batch_pending_results so every batch result reaches mq.

        When _execute_batch returns N results for a full batch of size N,
        _process_frames_batched stashes results[:-1] in _batch_pending_results and
        returns results[-1]. loop_once must send the stashed results before sending
        the final one.

        Regression guard for loop_once lines:
            if self._batch_pending_results:
                for pending in self._batch_pending_results:
                    self._send_frames(pending, outputs_timeout)
                self._batch_pending_results.clear()
        Removing that block silently drops intermediate batch results.
        """
        # batch_size=3: CountingBatchFilter.process_batch returns one result per
        # input frame, so a full batch of 3 produces 3 results: r1 and r2 stashed
        # in _batch_pending_results, r3 returned directly to loop_once.
        f = self._make_filter(batch_size=3)

        # First two loop_once calls accumulate frames without triggering the batch.
        f.mq.recv = MagicMock(return_value={"main": Frame({"val": 1})})
        f.loop_once()
        f.mq.recv = MagicMock(return_value={"main": Frame({"val": 2})})
        f.loop_once()
        self.assertEqual(
            f.mq.send.call_count, 0, "no results should be sent before the batch is full"
        )

        # Third loop_once fills the batch.  All three results must be sent.
        f.mq.recv = MagicMock(return_value={"main": Frame({"val": 3})})
        f.loop_once()

        self.assertEqual(
            f.mq.send.call_count,
            3,
            f"expected 3 sends (r1 + r2 via _batch_pending_results drain, r3 direct); "
            f"got {f.mq.send.call_count}",
        )

        f._stop_batch_watcher()


if __name__ == "__main__":
    unittest.main()
