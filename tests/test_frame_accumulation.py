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

        # Frame 2 at t≈60ms: _reset_batch_timer() sets _batch_wakeup mid-sleep.
        # The watcher only observes that signal when its initial ~100ms sleep
        # completes, then restarts for another full timeout, so the effective
        # flush deadline is ~original deadline + 100ms (~200ms), not ~160ms.
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
        sent_vals = [
            call.args[0]["main"].data["val"] for call in f.mq.send.call_args_list
        ]
        self.assertEqual(
            sent_vals,
            [1, 2, 3],
            "batch results should reach mq.send in input order (r1, r2, r3)",
        )

        f._stop_batch_watcher()
        f._batch_watcher.join(timeout=1.0)


class TestBatchDeferredCallable(unittest.TestCase):
    """process_batch() may return Callable slots that the runtime invokes later via
    mq.send's existing Callable polling. Mirrors the deferred-result path that
    process() already supports.
    """

    def _make_filter(self, filter_cls, batch_size=3, timeout_ms=1000.0):
        config = FilterConfig(
            id="test-deferred",
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

    def test_all_callable_slots_returned_to_send_path(self):
        """A batch where every slot is a Callable: process_frames returns the last
        Callable, earlier Callables land in _batch_pending_results. Each is still
        callable() at the point loop_once would hand it to mq.send."""

        class DeferredFilter(Filter):
            def setup(self, config):
                pass

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                # Capture each frame by value so each closure resolves to the right input.
                return [(lambda fs=fs: fs) for fs in batch]

        f = self._make_filter(DeferredFilter, batch_size=3)

        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        last = f.process_frames({"main": Frame({"val": 3})})

        self.assertTrue(callable(last))
        self.assertEqual(len(f._batch_pending_results), 2)
        for pending in f._batch_pending_results:
            self.assertTrue(callable(pending))

    def test_callable_slot_resolves_to_dict_on_invocation(self):
        """Invoking a returned closure resolves it: dict comes out, EMA updates,
        metadata is queued, _inject_timings stamps the frame.

        Calls _execute_batch directly to keep the assertion focused on the
        closure's resolution semantics (process_frames only goes through the
        batched path at batch_size > 1).
        """

        class DeferredFilter(Filter):
            def setup(self, config):
                pass

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                return [lambda: {"main": Frame({"resolved": True})}]

        f = self._make_filter(DeferredFilter, batch_size=2)
        prior_ema = f._process_time_ema
        results = f._execute_batch([{"main": Frame({"val": 1})}])
        self.assertEqual(len(results), 1)
        closure = results[0]
        self.assertTrue(callable(closure))

        # EMA should NOT have been touched by the synchronous _execute_batch when
        # any slot is a Callable — matches _process_frames_single's behavior.
        self.assertEqual(f._process_time_ema, prior_ema)

        resolved = closure()
        self.assertIsInstance(resolved, dict)
        self.assertIn("main", resolved)
        self.assertTrue(resolved["main"].data["resolved"])

        # Closure resolution should have updated the EMA and queued metadata.
        self.assertNotEqual(f._process_time_ema, prior_ema)
        f._metadata_queue.put_nowait.assert_called()

    def test_mixed_dict_and_callable_batch(self):
        """A batch where some slots are dicts and some are Callables: dicts emerge
        finalized at submission time, Callables emerge as closures that finalize
        on invocation. The list order is preserved.
        """

        class MixedFilter(Filter):
            def setup(self, config):
                pass

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                # Slot 0 immediate, slot 1 deferred, slot 2 immediate.
                return [
                    {"main": Frame({"slot": 0})},
                    lambda: {"main": Frame({"slot": 1, "deferred": True})},
                    {"main": Frame({"slot": 2})},
                ]

        f = self._make_filter(MixedFilter, batch_size=3)
        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        last = f.process_frames({"main": Frame({"val": 3})})

        # Order: slot 0 dict, slot 1 closure, slot 2 dict — last is slot 2 (dict).
        self.assertIsInstance(last, dict)
        self.assertEqual(last["main"].data["slot"], 2)

        self.assertEqual(len(f._batch_pending_results), 2)
        first, middle = f._batch_pending_results
        self.assertIsInstance(first, dict)
        self.assertEqual(first["main"].data["slot"], 0)
        self.assertTrue(callable(middle))
        resolved_middle = middle()
        self.assertEqual(resolved_middle["main"].data["slot"], 1)
        self.assertTrue(resolved_middle["main"].data["deferred"])

    def test_callable_slot_resolving_to_none(self):
        """A Callable that returns None on resolution behaves as a sink for that
        slot. mq.send already handles a None return from a Callable.
        """

        class DeferredSinkFilter(Filter):
            def setup(self, config):
                pass

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                return [lambda: None]

        f = self._make_filter(DeferredSinkFilter, batch_size=2)
        results = f._execute_batch([{"main": Frame({"val": 1})}])
        self.assertEqual(len(results), 1)
        closure = results[0]
        self.assertTrue(callable(closure))
        self.assertIsNone(closure())

    def test_ema_not_updated_when_any_slot_callable(self):
        """If ANY slot is a Callable, the synchronous EMA update in _execute_batch
        is skipped — each Callable does its own EMA update on resolution. Mirrors
        _process_frames_single's behavior.
        """

        class PartialDeferFilter(Filter):
            def setup(self, config):
                pass

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                # Two dicts and one Callable: the presence of a Callable should
                # suppress the batch-level EMA update.
                return [
                    {"main": Frame({"slot": 0})},
                    {"main": Frame({"slot": 1})},
                    lambda: {"main": Frame({"slot": 2})},
                ]

        f = self._make_filter(PartialDeferFilter, batch_size=3)
        prior_ema = f._process_time_ema
        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        f.process_frames({"main": Frame({"val": 3})})

        self.assertEqual(f._process_time_ema, prior_ema)


class TestAccumulateWindow(unittest.TestCase):
    """Sliding-window mode: keep accumulate_window frames in a deque, dispatch
    every batch_size new frames, route through Filter.select_batch().
    """

    def _make_filter(self, filter_cls, batch_size, window=None, timeout_ms=1000.0):
        kwargs = {
            "id": "test-window",
            "batch_size": batch_size,
            "accumulate_timeout_ms": timeout_ms,
        }
        if window is not None:
            kwargs["accumulate_window"] = window
        config = FilterConfig(**kwargs)
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

    def test_window_default_is_one_shot_list(self):
        """Unset accumulate_window: buffer stays a list, sliding mode off."""
        f = self._make_filter(CountingBatchFilter, batch_size=2)
        self.assertFalse(f._sliding_window)
        self.assertEqual(f._accumulate_window, 2)
        # list, not deque — so the original drain-on-dispatch contract holds.
        self.assertIsInstance(f._frame_buffer, list)

    def test_window_set_uses_bounded_deque(self):
        f = self._make_filter(CountingBatchFilter, batch_size=2, window=8)
        self.assertTrue(f._sliding_window)
        self.assertEqual(f._accumulate_window, 8)
        from collections import deque as _deque
        self.assertIsInstance(f._frame_buffer, _deque)
        self.assertEqual(f._frame_buffer.maxlen, 8)

    def test_invalid_window_smaller_than_batch_size(self):
        config = FilterConfig(id="bad", batch_size=4, accumulate_window=2)
        with self.assertRaises(ValueError) as ctx:
            Filter.normalize_config(config)
        self.assertIn("accumulate_window", str(ctx.exception))

    def test_default_select_batch_returns_last_batch_size(self):
        """select_batch's default keeps tail semantics — preserves current
        contract when accumulate_window is unset."""
        f = self._make_filter(CountingBatchFilter, batch_size=2)
        window = [
            {"main": Frame({"val": i})} for i in range(5)
        ]
        picked = f.select_batch(window)
        self.assertEqual(len(picked), 2)
        self.assertEqual(picked[0]["main"].data["val"], 3)
        self.assertEqual(picked[1]["main"].data["val"], 4)

    def test_sliding_window_does_not_clear_on_dispatch(self):
        """With accumulate_window set, the ring persists across dispatches —
        a frame appended for dispatch K is still present for dispatch K+1."""
        f = self._make_filter(CountingBatchFilter, batch_size=2, window=4)
        # Feed batch_size frames → dispatch fires.
        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        self.assertEqual(len(f.received_batches), 1)
        # Ring should still hold both frames.
        self.assertEqual(len(f._frame_buffer), 2)
        # Feeding two more triggers the next dispatch; ring grows to 4.
        f.process_frames({"main": Frame({"val": 3})})
        f.process_frames({"main": Frame({"val": 4})})
        self.assertEqual(len(f.received_batches), 2)
        self.assertEqual(len(f._frame_buffer), 4)

    def test_sliding_window_evicts_oldest_at_maxlen(self):
        """When window is full and new frame arrives, deque drops the oldest."""
        f = self._make_filter(CountingBatchFilter, batch_size=2, window=4)
        for i in range(6):
            f.process_frames({"main": Frame({"val": i})})
        # Ring capped at 4; last four values present.
        vals = [f._frame_buffer[i]["main"].data["val"] for i in range(len(f._frame_buffer))]
        self.assertEqual(vals, [2, 3, 4, 5])

    def test_custom_select_batch_routed_through_dispatch(self):
        """Overriding select_batch lets a filter pick non-tail frames."""

        class StridedFilter(CountingBatchFilter):
            def select_batch(self, window):
                # Every other frame, capped at batch_size.
                return list(window)[::2][: self._batch_size]

        f = self._make_filter(StridedFilter, batch_size=2, window=4)
        for i in range(4):
            f.process_frames({"main": Frame({"val": i})})
        # 4 frames in ring: indices [0, 2] picked.
        self.assertEqual(len(f.received_batches), 2)
        # Look at the LAST batch dispatched: should be strided picks from the
        # then-current ring.
        last_batch = f.received_batches[-1]
        picked_vals = [b["main"].data["val"] for b in last_batch]
        # After 4 frames in a window of 4: ring = [0,1,2,3], stride picks [0,2].
        self.assertEqual(picked_vals, [0, 2])

    def test_window_frames_since_dispatch_counter_resets(self):
        """The trigger counter (not the ring) is what advances toward batch_size."""
        f = self._make_filter(CountingBatchFilter, batch_size=3, window=8)
        # First two frames: counter at 2, no dispatch yet.
        f.process_frames({"main": Frame({"val": 0})})
        f.process_frames({"main": Frame({"val": 1})})
        self.assertEqual(f._frames_since_last_dispatch, 2)
        self.assertEqual(len(f.received_batches), 0)
        # Third frame: counter hits 3 → dispatch, counter resets.
        f.process_frames({"main": Frame({"val": 2})})
        self.assertEqual(f._frames_since_last_dispatch, 0)
        self.assertEqual(len(f.received_batches), 1)
        # Next batch_size frames again → second dispatch.
        f.process_frames({"main": Frame({"val": 3})})
        f.process_frames({"main": Frame({"val": 4})})
        f.process_frames({"main": Frame({"val": 5})})
        self.assertEqual(f._frames_since_last_dispatch, 0)
        self.assertEqual(len(f.received_batches), 2)


class TestManualBatchTrigger(unittest.TestCase):
    """batch_trigger='manual' disables auto count/timeout triggers; only
    Filter.flush_batch() drains.
    """

    def _make_filter(
        self,
        filter_cls,
        batch_size,
        trigger="auto",
        window=None,
        timeout_ms=1000.0,
    ):
        kwargs = {
            "id": "test-manual",
            "batch_size": batch_size,
            "accumulate_timeout_ms": timeout_ms,
            "batch_trigger": trigger,
        }
        if window is not None:
            kwargs["accumulate_window"] = window
        config = FilterConfig(**kwargs)
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

    def test_invalid_batch_trigger(self):
        config = FilterConfig(id="bad", batch_size=2, batch_trigger="sometimes")
        with self.assertRaises(ValueError) as ctx:
            Filter.normalize_config(config)
        self.assertIn("batch_trigger", str(ctx.exception))

    def test_default_trigger_is_auto(self):
        f = self._make_filter(CountingBatchFilter, batch_size=2)
        self.assertEqual(f._batch_trigger, "auto")

    def test_manual_mode_suppresses_count_trigger(self):
        """In manual mode, accumulating batch_size frames does NOT dispatch."""
        f = self._make_filter(CountingBatchFilter, batch_size=2, trigger="manual")
        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        f.process_frames({"main": Frame({"val": 3})})
        self.assertEqual(len(f.received_batches), 0)
        # Frames pile up in the buffer.
        self.assertEqual(len(f._frame_buffer), 3)

    def test_manual_mode_does_not_start_watcher(self):
        """Manual mode skips the timeout watcher entirely."""
        f = self._make_filter(
            CountingBatchFilter, batch_size=5, trigger="manual", timeout_ms=50.0
        )
        f.process_frames({"main": Frame({"val": 1})})
        # No watcher should have been started — _reset_batch_timer isn't called.
        self.assertIsNone(f._batch_watcher)

    def test_flush_batch_triggers_dispatch_on_next_frame(self):
        """flush_batch() sets the event; the next frame append picks it up and
        dispatches."""
        f = self._make_filter(CountingBatchFilter, batch_size=5, trigger="manual")
        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        self.assertEqual(len(f.received_batches), 0)
        f.flush_batch()
        f.process_frames({"main": Frame({"val": 3})})
        self.assertEqual(len(f.received_batches), 1)
        # All three frames should be in the dispatched batch (manual mode without
        # accumulate_window keeps the simple list buffer that drains on dispatch).
        dispatched = f.received_batches[0]
        self.assertEqual(len(dispatched), 3)

    def test_flush_batch_noop_in_non_batch_mode(self):
        """At batch_size == 1, flush_batch is a documented no-op."""
        f = self._make_filter(FallbackBatchFilter, batch_size=1)
        # Should not raise, should not flip the event (event doesn't gate
        # anything in batch_size=1 path, but verify the contract).
        f.flush_batch()
        self.assertFalse(f._batch_flush_event.is_set())

    def test_manual_mode_safety_cap_force_flushes(self):
        """If a manual-mode filter never calls flush_batch(), the runtime
        force-flushes at batch_size * 4 to bound memory."""
        f = self._make_filter(CountingBatchFilter, batch_size=2, trigger="manual")
        # batch_size=2 → safety cap at 8 frames.
        for i in range(8):
            f.process_frames({"main": Frame({"val": i})})
        # 8th frame should have tripped the safety cap and force-dispatched.
        self.assertEqual(len(f.received_batches), 1)
        self.assertEqual(len(f.received_batches[0]), 8)

    def test_auto_mode_count_trigger_still_fires(self):
        """batch_trigger='auto' (default) — count trigger behaves as before."""
        f = self._make_filter(CountingBatchFilter, batch_size=2, trigger="auto")
        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        self.assertEqual(len(f.received_batches), 1)

    def test_manual_mode_with_sliding_window(self):
        """Manual mode composes with accumulate_window: flush_batch() picks
        from the ring via select_batch()."""
        f = self._make_filter(
            CountingBatchFilter, batch_size=2, trigger="manual", window=6
        )
        for i in range(4):
            f.process_frames({"main": Frame({"val": i})})
        self.assertEqual(len(f.received_batches), 0)
        # Ring should hold all 4 frames.
        self.assertEqual(len(f._frame_buffer), 4)
        f.flush_batch()
        f.process_frames({"main": Frame({"val": 4})})
        self.assertEqual(len(f.received_batches), 1)
        # Sliding mode preserves ring; default select_batch returns last batch_size.
        dispatched = f.received_batches[0]
        self.assertEqual(len(dispatched), 2)
        vals = [b["main"].data["val"] for b in dispatched]
        self.assertEqual(vals, [3, 4])
        # Ring should still hold the 5 frames (capped at 6 maxlen).
        self.assertEqual(len(f._frame_buffer), 5)


class TestBatchWorkersPool(unittest.TestCase):
    """batch_workers > 1: process_batch runs on a ThreadPoolExecutor; per-slot
    Callables wait on the future. Backpressure via submission semaphore.
    """

    def _make_filter(
        self,
        filter_cls,
        batch_size,
        workers,
        shutdown_timeout=5.0,
    ):
        config = FilterConfig(
            id="test-pool",
            batch_size=batch_size,
            accumulate_timeout_ms=1000.0,
            batch_workers=workers,
            batch_shutdown_timeout_s=shutdown_timeout,
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

    def test_invalid_batch_workers_zero(self):
        config = FilterConfig(id="bad", batch_size=2, batch_workers=0)
        with self.assertRaises(ValueError):
            Filter.normalize_config(config)

    def test_batch_workers_one_is_inline_path(self):
        """batch_workers=1 keeps the synchronous path — no pool ever created."""
        f = self._make_filter(CountingBatchFilter, batch_size=2, workers=1)
        f.process_frames({"main": Frame({"val": 1})})
        f.process_frames({"main": Frame({"val": 2})})
        self.assertEqual(len(f.received_batches), 1)
        # Pool was never instantiated.
        self.assertIsNone(f._batch_pool)

    def test_pool_returns_callables(self):
        """In pool mode, _execute_batch returns Callables (not dicts)."""
        f = self._make_filter(CountingBatchFilter, batch_size=2, workers=2)
        try:
            results = f._execute_batch([
                {"main": Frame({"val": 1})},
                {"main": Frame({"val": 2})},
            ])
            self.assertEqual(len(results), 2)
            for r in results:
                self.assertTrue(callable(r))
            # Resolve one to verify it returns a real dict.
            resolved = results[0]()
            self.assertIsInstance(resolved, dict)
        finally:
            f.fini()

    def test_pool_batches_overlap_in_wall_clock(self):
        """Two batches submitted back-to-back actually run in parallel."""

        barrier = threading.Barrier(2, timeout=5.0)

        class OverlapFilter(Filter):
            def setup(self, config):
                self.started_at = []
                self.ended_at = []

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                self.started_at.append(time.time())
                # Wait for both workers to enter before either returns —
                # only possible if they ran concurrently.
                barrier.wait()
                self.ended_at.append(time.time())
                return [{"main": Frame({"slot": 0})}] * len(batch)

        f = self._make_filter(OverlapFilter, batch_size=1, workers=2)
        try:
            r1 = f._execute_batch([{"main": Frame({"a": 1})}])
            r2 = f._execute_batch([{"main": Frame({"a": 2})}])
            # Resolve both — this drives the futures to completion.
            r1[0]()
            r2[0]()
            self.assertEqual(len(f.started_at), 2)
            # Both batches must have entered the barrier at the same time
            # (sequential execution would deadlock at barrier.wait()).
            self.assertLess(abs(f.started_at[1] - f.started_at[0]), 1.0)
        finally:
            f.fini()

    def test_pool_backpressure_blocks_submission_when_full(self):
        """When the pool is full (all batch_workers slots in use),
        _execute_batch_pool blocks on the semaphore until a worker frees."""

        gate = threading.Event()

        class GatedFilter(Filter):
            def setup(self, config):
                pass

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                gate.wait(timeout=5.0)
                return [{"main": Frame({"done": True})}] * len(batch)

        # workers=2 so we can saturate with two submissions before the third
        # backpressures. workers=1 would take the synchronous path entirely.
        f = self._make_filter(GatedFilter, batch_size=1, workers=2)
        try:
            r1 = f._execute_batch([{"main": Frame({"a": 1})}])
            r2 = f._execute_batch([{"main": Frame({"a": 2})}])
            # Pool fully busy at 2/2. Third submit should block.
            blocked = threading.Event()
            released = threading.Event()
            r3_holder = []

            def submit_third():
                blocked.set()
                r3 = f._execute_batch([{"main": Frame({"a": 3})}])
                r3_holder.append(r3)
                released.set()

            t = threading.Thread(target=submit_third)
            t.start()
            blocked.wait(timeout=1.0)
            time.sleep(0.1)
            self.assertFalse(
                released.is_set(),
                "third submit should be blocked while pool is full",
            )
            # Let workers finish — semaphore frees, third submission proceeds.
            gate.set()
            released.wait(timeout=5.0)
            self.assertTrue(released.is_set())
            t.join(timeout=5.0)
            # Drain to release pool workers cleanly.
            r1[0]()
            r2[0]()
            r3_holder[0][0]()
        finally:
            f.fini()

    def test_pool_drains_on_fini(self):
        """fini() waits for in-flight batches up to batch_shutdown_timeout_s."""

        class SlowFilter(Filter):
            def setup(self, config):
                pass

            def process(self, frames):
                return frames

            def process_batch(self, batch):
                time.sleep(0.2)
                return [{"main": Frame({"done": True})}] * len(batch)

        f = self._make_filter(
            SlowFilter, batch_size=1, workers=2, shutdown_timeout=5.0
        )
        # Submit but don't poll the callables — they're in flight.
        f._execute_batch([{"main": Frame({"a": 1})}])
        f._execute_batch([{"main": Frame({"a": 2})}])
        # Fini should wait for both to finish (< 5s timeout).
        t0 = time.time()
        f.fini()
        elapsed = time.time() - t0
        self.assertLess(elapsed, 5.0)
        # All futures should have completed (no warning would fire).
        with f._batch_inflight_lock:
            # add_done_callback fires async — give it a tick to drain.
            time.sleep(0.05)
            self.assertEqual(len(f._batch_inflight), 0)


if __name__ == "__main__":
    unittest.main()
