"""Unit tests for per-frame, per-filter timing metrics.

Covers _update_process_time_ema, _inject_timings, process_frames timing
for sink/dict/callable returns, _SYSTEM_HEALTH_METRICS/_GAUGE_METRICS sets,
and update_metrics prefix logic in OpenTelemetryClient.
"""

import time
import unittest
from unittest.mock import Mock, patch, MagicMock

import numpy as np

from openfilter.filter_runtime import Filter, Frame
from openfilter.observability.client import OpenTelemetryClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bare_filter(**overrides):
    """Create a Filter instance bypassing __init__ to avoid heavy setup.

    Uses object.__new__() so no logging, MQ, scarf analytics, or thread
    spawning happens. Only timing-related attributes are set.
    """
    f = object.__new__(Filter)
    f._filter_time_in = 0.0
    f._filter_time_out = 0.0
    f._process_time_ema = 0.0
    f._frame_total_time_ema = 0.0
    f._frame_avg_time_ema = 0.0
    f._frame_std_time_ema = 0.0
    f._is_last_filter = False
    f.filter_name = "TestFilter"
    f.pipeline_id = "test-pipeline"
    f.emitter = None
    f._telemetry = None
    for k, v in overrides.items():
        setattr(f, k, v)
    return f


def _make_frame(data=None):
    """Create a minimal Frame with dict data."""
    return Frame(np.zeros((2, 2, 3), dtype=np.uint8), data=data or {}, format="RGB")


# ---------------------------------------------------------------------------
# Inline Filter subclasses
# ---------------------------------------------------------------------------

class SinkFilter(Filter):
    """process() returns None (sink)."""
    def process(self, frames):
        return None


class PassthroughFilter(Filter):
    """process() returns input frames dict."""
    def process(self, frames):
        return frames


class CallableFilter(Filter):
    """process() returns a callable that yields frames."""
    def __init__(self, return_fn, **kw):
        self._return_fn = return_fn

    def process(self, frames):
        return self._return_fn


class CallableNoneFilter(Filter):
    """process() returns a callable that yields None."""
    def process(self, frames):
        return lambda: None


# ===================================================================
# Group 1: _update_process_time_ema
# ===================================================================

class TestUpdateProcessTimeEma(unittest.TestCase):
    """Tests for Filter._update_process_time_ema."""

    def test_ema_from_zero(self):
        """EMA starting from 0 with a single sample: 0.95*0 + 0.05*100 = 5.0."""
        f = make_bare_filter()
        f._update_process_time_ema(100.0)
        self.assertAlmostEqual(f._process_time_ema, 5.0)

    def test_convergence(self):
        """200 constant-input calls converge close to input value."""
        f = make_bare_filter()
        for _ in range(200):
            f._update_process_time_ema(42.0)
        self.assertAlmostEqual(f._process_time_ema, 42.0, places=1)

    def test_step_change_tracking(self):
        """After a step change (100 -> 500), EMA shifts toward new value."""
        f = make_bare_filter()
        for _ in range(100):
            f._update_process_time_ema(100.0)
        ema_before = f._process_time_ema
        for _ in range(100):
            f._update_process_time_ema(500.0)
        # Should be well above the old value and approaching 500
        self.assertGreater(f._process_time_ema, ema_before + 100)
        self.assertLess(f._process_time_ema, 500.0)

    def test_alpha_verification(self):
        """Exact alpha check: from EMA=50, input=100 -> 0.95*50 + 0.05*100 = 52.5."""
        f = make_bare_filter()
        f._process_time_ema = 50.0
        f._update_process_time_ema(100.0)
        self.assertAlmostEqual(f._process_time_ema, 52.5)


# ===================================================================
# Group 2: _inject_timings
# ===================================================================

class TestInjectTimings(unittest.TestCase):
    """Tests for Filter._inject_timings."""

    def test_appends_timing_entry(self):
        """Timing entry is appended to frame.data['meta']['filter_timings']."""
        f = make_bare_filter()
        frame = _make_frame()
        frames = {"main": frame}
        f._inject_timings(frames, 1000.0, 1001.0, 10.0)

        timings = frame.data["meta"]["filter_timings"]
        self.assertEqual(len(timings), 1)
        entry = timings[0]
        self.assertEqual(entry["filter_name"], "TestFilter")
        self.assertEqual(entry["pipeline_id"], "test-pipeline")
        self.assertAlmostEqual(entry["time_in"], 1000.0)
        self.assertAlmostEqual(entry["time_out"], 1001.0)
        self.assertAlmostEqual(entry["duration_ms"], 10.0)

    def test_creates_meta_if_missing(self):
        """meta dict is created when absent from frame.data."""
        f = make_bare_filter()
        frame = _make_frame(data={"some_key": "value"})
        frames = {"main": frame}
        f._inject_timings(frames, 0, 0, 5.0)

        self.assertIn("meta", frame.data)
        self.assertIn("filter_timings", frame.data["meta"])

    def test_appends_to_existing_timings(self):
        """New entry is appended, not clobbering existing timings."""
        f = make_bare_filter()
        existing = {"filter_name": "PrevFilter", "pipeline_id": "", "time_in": 0, "time_out": 0, "duration_ms": 3.0}
        frame = _make_frame(data={"meta": {"filter_timings": [existing]}})
        frames = {"main": frame}
        f._inject_timings(frames, 1, 2, 7.0)

        timings = frame.data["meta"]["filter_timings"]
        self.assertEqual(len(timings), 2)
        self.assertEqual(timings[0]["filter_name"], "PrevFilter")
        self.assertEqual(timings[1]["filter_name"], "TestFilter")

    def test_skips_underscore_topics(self):
        """Frames under _-prefixed topics are skipped."""
        f = make_bare_filter()
        frame = _make_frame()
        frames = {"_internal": frame}
        f._inject_timings(frames, 0, 0, 5.0)
        self.assertNotIn("meta", frame.data)

    def test_skips_non_dict_data(self):
        """Frames with non-dict data are skipped without error."""
        f = make_bare_filter()
        # Use a mock with non-dict data since Frame.data always returns dict
        mock_frame = Mock()
        mock_frame.data = "not a dict"
        frames = {"main": mock_frame}
        # Should not raise
        f._inject_timings(frames, 0, 0, 5.0)
        # data should remain unchanged
        self.assertEqual(mock_frame.data, "not a dict")

    def test_last_filter_computes_aggregates(self):
        """Last filter computes total/avg/std EMA from all filter durations."""
        f = make_bare_filter(_is_last_filter=True)
        # Simulate two previous filters already recorded
        prev1 = {"filter_name": "A", "pipeline_id": "", "time_in": 0, "time_out": 0, "duration_ms": 10.0}
        prev2 = {"filter_name": "B", "pipeline_id": "", "time_in": 0, "time_out": 0, "duration_ms": 20.0}
        frame = _make_frame(data={"meta": {"filter_timings": [prev1, prev2]}})
        frames = {"main": frame}

        f._inject_timings(frames, 0, 0, 30.0)

        # Now we have durations [10, 20, 30]
        # total = 60, avg = 20, std = sqrt((100+0+100)/3) = sqrt(200/3) ~ 8.165
        total = 60.0
        avg = 20.0
        std = (((10 - 20) ** 2 + (20 - 20) ** 2 + (30 - 20) ** 2) / 3) ** 0.5

        alpha = 0.05
        self.assertAlmostEqual(f._frame_total_time_ema, alpha * total)
        self.assertAlmostEqual(f._frame_avg_time_ema, alpha * avg)
        self.assertAlmostEqual(f._frame_std_time_ema, alpha * std)

    def test_non_last_filter_no_aggregates(self):
        """Non-last filter does not update aggregate EMA fields."""
        f = make_bare_filter(_is_last_filter=False)
        frame = _make_frame()
        frames = {"main": frame}
        f._inject_timings(frames, 0, 0, 42.0)

        self.assertEqual(f._frame_total_time_ema, 0.0)
        self.assertEqual(f._frame_avg_time_ema, 0.0)
        self.assertEqual(f._frame_std_time_ema, 0.0)

    def test_multiple_topics_each_get_entry(self):
        """Each non-_ topic frame gets its own timing entry."""
        f = make_bare_filter()
        frame_a = _make_frame()
        frame_b = _make_frame()
        frames = {"topicA": frame_a, "topicB": frame_b}
        f._inject_timings(frames, 0, 1, 5.0)

        self.assertEqual(len(frame_a.data["meta"]["filter_timings"]), 1)
        self.assertEqual(len(frame_b.data["meta"]["filter_timings"]), 1)

    def test_filter_name_fallback_to_class_name(self):
        """Uses __class__.__name__ when filter_name is None."""
        f = make_bare_filter(filter_name=None)
        frame = _make_frame()
        frames = {"main": frame}
        f._inject_timings(frames, 0, 0, 1.0)

        entry = frame.data["meta"]["filter_timings"][0]
        self.assertEqual(entry["filter_name"], "Filter")


# ===================================================================
# Group 3: process_frames -- sink filter (returns None)
# ===================================================================

class TestProcessFramesSink(unittest.TestCase):
    """Tests for process_frames when process() returns None."""

    def _make_sink(self, **overrides):
        f = make_bare_filter(**overrides)
        f.process = lambda frames: None
        return f

    def test_sink_updates_timing_fields(self):
        """Sink filter still records _filter_time_in, _filter_time_out, _process_time_ema."""
        f = self._make_sink()
        frames = {"main": _make_frame()}

        t_before = time.time()
        result = f.process_frames(frames)
        t_after = time.time()

        self.assertIsNone(result)
        self.assertGreaterEqual(f._filter_time_in, t_before)
        self.assertLessEqual(f._filter_time_out, t_after)
        self.assertGreaterEqual(f._filter_time_out, f._filter_time_in)
        # EMA was called (process_time_ema >= 0; may be ~0 for very fast process)
        self.assertGreaterEqual(f._process_time_ema, 0.0)

    def test_sink_last_filter_injects_timings(self):
        """Sink + last filter injects timings into *input* frames."""
        f = self._make_sink(_is_last_filter=True)
        frame = _make_frame()
        frames = {"main": frame}

        result = f.process_frames(frames)

        self.assertIsNone(result)
        timings = frame.data["meta"]["filter_timings"]
        self.assertEqual(len(timings), 1)
        self.assertEqual(timings[0]["filter_name"], "TestFilter")

    def test_sink_non_last_no_inject_but_timing_updated(self):
        """Sink + non-last: no inject_timings call, but timing fields updated."""
        f = self._make_sink(_is_last_filter=False)
        frame = _make_frame()
        frames = {"main": frame}

        t_before = time.time()
        result = f.process_frames(frames)

        self.assertIsNone(result)
        self.assertNotIn("meta", frame.data)
        self.assertGreaterEqual(f._filter_time_in, t_before)
        self.assertGreaterEqual(f._process_time_ema, 0.0)


# ===================================================================
# Group 4: process_frames -- dict/Frame return
# ===================================================================

class TestProcessFramesDictReturn(unittest.TestCase):
    """Tests for process_frames with dict or single Frame return."""

    def test_dict_return_injects_timings(self):
        """Dict return from process() gets timings injected."""
        f = make_bare_filter()
        out_frame = _make_frame()
        f.process = lambda frames: {"output": out_frame}

        result = f.process_frames({"main": _make_frame()})

        self.assertIn("output", result)
        timings = out_frame.data["meta"]["filter_timings"]
        self.assertEqual(len(timings), 1)
        self.assertEqual(timings[0]["filter_name"], "TestFilter")

    def test_single_frame_return_wrapped_as_main(self):
        """Single Frame return is wrapped as {'main': frame} with timings."""
        f = make_bare_filter()
        out_frame = _make_frame()
        f.process = lambda frames: out_frame

        result = f.process_frames({"main": _make_frame()})

        self.assertIn("main", result)
        self.assertIs(result["main"], out_frame)
        timings = out_frame.data["meta"]["filter_timings"]
        self.assertEqual(len(timings), 1)


# ===================================================================
# Group 5: process_frames -- callable return
# ===================================================================

class TestProcessFramesCallable(unittest.TestCase):
    """Tests for process_frames when process() returns a callable."""

    def test_returns_timed_callable_wrapper(self):
        """Callable return produces a new callable wrapper."""
        f = make_bare_filter()
        inner_frame = _make_frame()
        f.process = lambda frames: (lambda: {"main": inner_frame})

        result = f.process_frames({"main": _make_frame()})

        self.assertTrue(callable(result))

    def test_invoking_wrapper_updates_timing_and_injects(self):
        """Invoking the wrapper updates timing fields and injects timings."""
        f = make_bare_filter()
        inner_frame = _make_frame()
        f.process = lambda frames: (lambda: {"main": inner_frame})

        wrapper = f.process_frames({"main": _make_frame()})
        # Reset timing to verify callable updates them again
        f._filter_time_in = 0.0
        f._filter_time_out = 0.0
        old_ema = f._process_time_ema

        out = wrapper()

        self.assertIn("main", out)
        self.assertGreater(f._filter_time_in, 0)
        self.assertGreater(f._filter_time_out, 0)
        timings = inner_frame.data["meta"]["filter_timings"]
        self.assertGreaterEqual(len(timings), 1)

    def test_callable_returning_none_wrapper_returns_none(self):
        """Callable that returns None -> wrapper returns None."""
        f = make_bare_filter()
        f.process = lambda frames: (lambda: None)

        wrapper = f.process_frames({"main": _make_frame()})
        result = wrapper()

        self.assertIsNone(result)


# ===================================================================
# Group 6: _SYSTEM_HEALTH_METRICS / _GAUGE_METRICS sets
# ===================================================================

class TestMetricSets(unittest.TestCase):
    """Tests for _SYSTEM_HEALTH_METRICS and _GAUGE_METRICS containing timing metrics."""

    TIMING_METRICS = {
        "filter_time_in",
        "filter_time_out",
        "process_time_ms",
        "frame_total_time_ms",
        "frame_avg_time_ms",
        "frame_std_time_ms",
    }

    def test_system_health_metrics_contain_timing(self):
        """All 6 timing metric names are in _SYSTEM_HEALTH_METRICS."""
        for name in self.TIMING_METRICS:
            self.assertIn(name, OpenTelemetryClient._SYSTEM_HEALTH_METRICS, f"Missing {name}")

    def test_gauge_metrics_contain_timing(self):
        """All 6 timing metric names are in _GAUGE_METRICS."""
        for name in self.TIMING_METRICS:
            self.assertIn(name, OpenTelemetryClient._GAUGE_METRICS, f"Missing {name}")


# ===================================================================
# Group 7: update_metrics prefix logic
# ===================================================================

class TestUpdateMetricsPrefix(unittest.TestCase):
    """Tests for OpenTelemetryClient.update_metrics prefix and instrument logic."""

    def _make_client(self):
        """Create an enabled client with mocked internals."""
        c = object.__new__(OpenTelemetryClient)
        c.enabled = True
        c.instance_id = "test-instance"
        c.setup_metrics = {}
        c._lock = __import__("threading").Lock()
        c._metrics = {}
        c._values = {}
        c.meter = Mock()
        # Default mock returns for gauge/counter creation
        c.meter.create_observable_gauge.return_value = Mock()
        c.meter.create_counter.return_value = Mock()
        return c

    def test_health_metrics_get_openfilter_prefix(self):
        """System health metrics are prefixed with openfilter_."""
        c = self._make_client()
        c.update_metrics({"filter_time_in": 123.0}, "MyFilter")
        self.assertIn("openfilter_filter_time_in", c._metrics)

    def test_non_health_metrics_get_filter_name_prefix(self):
        """Non-health metrics are prefixed with {filter_name}_."""
        c = self._make_client()
        c.update_metrics({"custom_metric": 5.0}, "MyFilter")
        self.assertIn("MyFilter_custom_metric", c._metrics)

    def test_timing_metrics_create_gauges_not_counters(self):
        """Timing metrics (in _GAUGE_METRICS) should create observable gauges."""
        c = self._make_client()
        c.update_metrics({"process_time_ms": 42.0}, "MyFilter")
        c.meter.create_observable_gauge.assert_called()
        c.meter.create_counter.assert_not_called()

    def test_disabled_client_is_noop(self):
        """Disabled client returns immediately without updating anything."""
        c = self._make_client()
        c.enabled = False
        c.update_metrics({"filter_time_in": 1.0}, "MyFilter")
        self.assertEqual(len(c._metrics), 0)


if __name__ == "__main__":
    unittest.main()
