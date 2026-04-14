"""Performance benchmarks: serialization/IPC overhead vs filter processing time.

Measures the cost of the OpenFilter runtime's own machinery — frame
serialization, JSON data encoding, JPG encode/decode, ZMQ transport,
timing injection — relative to the time filters spend in process().

Run benchmarks:
    pytest tests/test_benchmarks.py -v --benchmark-group-by=group -s

Skip benchmarks during normal test runs:
    pytest tests/ --benchmark-disable
"""

import functools
import json
import logging
import time
import warnings

import cv2
import numpy as np
import pytest

from helpers import ThreadMQSender
from openfilter.filter_runtime import Filter, Frame
from openfilter.filter_runtime.mq import MQ, MQReceiver


# ---------------------------------------------------------------------------
# Fixtures: realistic frames at varying sizes
# ---------------------------------------------------------------------------


def _rgb_frame(h, w, data=None):
    """Create an RGB frame with random pixel data and metadata."""
    image = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
    return Frame(image, data or {}, "RGB")


def _frame_with_meta(h, w):
    """Create a frame with realistic pipeline metadata."""
    return _rgb_frame(
        h,
        w,
        {
            "meta": {
                "id": 42,
                "filter_timings": [
                    {
                        "filter_name": f"filter_{i}",
                        "filter_id": f"f{i}",
                        "pipeline_id": "bench-pipe",
                        "time_in": 1000.0 + i,
                        "time_out": 1000.0 + i + 0.005,
                        "duration_ms": 5.0,
                    }
                    for i in range(5)
                ],
            },
            "detections": [
                {"class": "person", "confidence": 0.95, "bbox": [100, 200, 300, 400]}
                for _ in range(10)
            ],
        },
    )


@functools.cache
def FRAME_480P():
    return _rgb_frame(480, 640)

@functools.cache
def FRAME_720P():
    return _rgb_frame(720, 1280)

@functools.cache
def FRAME_1080P():
    return _rgb_frame(1080, 1920)

@functools.cache
def FRAME_4K():
    return _rgb_frame(2160, 3840)

@functools.cache
def FRAME_DATA_ONLY():
    return Frame({"detections": [{"class": "car", "score": 0.9}] * 20})

@functools.cache
def FRAME_WITH_META():
    return _frame_with_meta(480, 640)


# ---------------------------------------------------------------------------
# Group: frame_serde — Frame ↔ ZMQ wire format (the core serialization)
# ---------------------------------------------------------------------------


class TestFrameSerdeBenchmarks:
    """Benchmarks for MQ.frames2topicmsgs / MQ.topicmsgs2frames —
    the serialization layer between every pair of filters."""

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_480p_raw(self, benchmark):
        frames = {"main": FRAME_480P()}
        benchmark(MQ.frames2topicmsgs, frames, False)

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_480p_jpg(self, benchmark):
        frames = {"main": FRAME_480P()}
        benchmark(MQ.frames2topicmsgs, frames, True)

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_1080p_raw(self, benchmark):
        frames = {"main": FRAME_1080P()}
        benchmark(MQ.frames2topicmsgs, frames, False)

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_1080p_jpg(self, benchmark):
        frames = {"main": FRAME_1080P()}
        benchmark(MQ.frames2topicmsgs, frames, True)

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_data_only(self, benchmark):
        frames = {"main": FRAME_DATA_ONLY()}
        benchmark(MQ.frames2topicmsgs, frames)

    @pytest.mark.benchmark(group="frame_serde")
    def test_deserialize_480p_raw(self, benchmark):
        topicmsgs = MQ.frames2topicmsgs({"main": FRAME_480P()}, False)
        benchmark(MQ.topicmsgs2frames, topicmsgs)

    @pytest.mark.benchmark(group="frame_serde")
    def test_deserialize_480p_jpg(self, benchmark):
        topicmsgs = MQ.frames2topicmsgs({"main": FRAME_480P()}, True)
        benchmark(MQ.topicmsgs2frames, topicmsgs)

    @pytest.mark.benchmark(group="frame_serde")
    def test_deserialize_1080p_raw(self, benchmark):
        topicmsgs = MQ.frames2topicmsgs({"main": FRAME_1080P()}, False)
        benchmark(MQ.topicmsgs2frames, topicmsgs)

    @pytest.mark.benchmark(group="frame_serde")
    def test_deserialize_1080p_jpg(self, benchmark):
        topicmsgs = MQ.frames2topicmsgs({"main": FRAME_1080P()}, True)
        benchmark(MQ.topicmsgs2frames, topicmsgs)

    @pytest.mark.benchmark(group="frame_serde")
    def test_roundtrip_480p_raw(self, benchmark):
        frames = {"main": FRAME_480P()}

        def roundtrip():
            return MQ.topicmsgs2frames(MQ.frames2topicmsgs(frames, False))

        benchmark(roundtrip)

    @pytest.mark.benchmark(group="frame_serde")
    def test_roundtrip_480p_jpg(self, benchmark):
        frames = {"main": FRAME_480P()}

        def roundtrip():
            return MQ.topicmsgs2frames(MQ.frames2topicmsgs(frames, True))

        benchmark(roundtrip)

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_4k_raw(self, benchmark):
        frames = {"main": FRAME_4K()}
        benchmark(MQ.frames2topicmsgs, frames, False)

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_4k_jpg(self, benchmark):
        frames = {"main": FRAME_4K()}
        benchmark(MQ.frames2topicmsgs, frames, True)

    @pytest.mark.benchmark(group="frame_serde")
    def test_deserialize_4k_raw(self, benchmark):
        topicmsgs = MQ.frames2topicmsgs({"main": FRAME_4K()}, False)
        benchmark(MQ.topicmsgs2frames, topicmsgs)

    @pytest.mark.benchmark(group="frame_serde")
    def test_roundtrip_4k_raw(self, benchmark):
        frames = {"main": FRAME_4K()}

        def roundtrip():
            return MQ.topicmsgs2frames(MQ.frames2topicmsgs(frames, False))

        benchmark(roundtrip)

    @pytest.mark.benchmark(group="frame_serde")
    def test_serialize_with_rich_metadata(self, benchmark):
        frames = {"main": FRAME_WITH_META()}
        benchmark(MQ.frames2topicmsgs, frames, False)


# ---------------------------------------------------------------------------
# Group: jpg_codec — JPG encode/decode in isolation
# ---------------------------------------------------------------------------


class TestJpgCodecBenchmarks:
    """Benchmarks for JPG encoding and decoding (the dominant serialization cost)."""

    @pytest.mark.benchmark(group="jpg_codec")
    def test_jpg_encode_480p(self, benchmark):
        image = FRAME_480P().image
        benchmark(cv2.imencode, ".jpg", image)

    @pytest.mark.benchmark(group="jpg_codec")
    def test_jpg_encode_1080p(self, benchmark):
        image = FRAME_1080P().image
        benchmark(cv2.imencode, ".jpg", image)

    @pytest.mark.benchmark(group="jpg_codec")
    def test_jpg_decode_480p(self, benchmark):
        _, buf = cv2.imencode(".jpg", FRAME_480P().image)
        jpg_bytes = buf.tobytes()
        benchmark(cv2.imdecode, np.frombuffer(jpg_bytes, np.uint8), cv2.IMREAD_COLOR)

    @pytest.mark.benchmark(group="jpg_codec")
    def test_jpg_decode_1080p(self, benchmark):
        _, buf = cv2.imencode(".jpg", FRAME_1080P().image)
        jpg_bytes = buf.tobytes()
        benchmark(cv2.imdecode, np.frombuffer(jpg_bytes, np.uint8), cv2.IMREAD_COLOR)

    @pytest.mark.benchmark(group="jpg_codec")
    def test_jpg_encode_4k(self, benchmark):
        image = FRAME_4K().image
        benchmark(cv2.imencode, ".jpg", image)

    @pytest.mark.benchmark(group="jpg_codec")
    def test_jpg_decode_4k(self, benchmark):
        _, buf = cv2.imencode(".jpg", FRAME_4K().image)
        jpg_bytes = buf.tobytes()
        benchmark(cv2.imdecode, np.frombuffer(jpg_bytes, np.uint8), cv2.IMREAD_COLOR)

    @pytest.mark.benchmark(group="jpg_codec")
    def test_frame_jpg_property_cached_ro(self, benchmark):
        """Accessing .jpg on a read-only frame should be cheap after first call (cached)."""
        frame = FRAME_480P().ro
        _ = frame.jpg  # prime the cache

        benchmark(lambda: frame.jpg)

    @pytest.mark.benchmark(group="jpg_codec")
    def test_frame_jpg_property_rw(self, benchmark):
        """Accessing .jpg on a read-write frame re-encodes every time (no cache)."""
        frame = _rgb_frame(480, 640)  # fresh rw frame each time

        benchmark(lambda: frame.jpg)


# ---------------------------------------------------------------------------
# Group: json_data — JSON serialization of frame.data metadata
# ---------------------------------------------------------------------------


class TestJsonDataBenchmarks:
    """Benchmarks for frame.data JSON serialization (the metadata portion of IPC)."""

    @pytest.mark.benchmark(group="json_data")
    def test_json_encode_small(self, benchmark):
        data = {"meta": {"id": 1}, "ts": 1234567890.123}
        benchmark(json.dumps, data, separators=(",", ":"))

    @pytest.mark.benchmark(group="json_data")
    def test_json_encode_detections(self, benchmark):
        data = {
            "detections": [
                {
                    "class": "person",
                    "confidence": 0.95,
                    "bbox": [100, 200, 300, 400],
                    "track_id": i,
                    "attributes": {"age": "adult", "gender": "unknown"},
                }
                for i in range(50)
            ],
            "meta": {
                "id": 42,
                "filter_timings": [
                    {"filter_name": f"f{i}", "duration_ms": 5.0} for i in range(8)
                ],
            },
        }
        benchmark(json.dumps, data, separators=(",", ":"))

    @pytest.mark.benchmark(group="json_data")
    def test_json_decode_detections(self, benchmark):
        data = {
            "detections": [
                {"class": "person", "confidence": 0.95, "bbox": [100, 200, 300, 400]}
                for _ in range(50)
            ]
        }
        raw = json.dumps(data, separators=(",", ":"))
        benchmark(json.loads, raw)


# ---------------------------------------------------------------------------
# Group: frame_conversion — format conversions (RGB ↔ BGR, .rw, .ro)
# ---------------------------------------------------------------------------


class TestFrameConversionBenchmarks:
    """Benchmarks for Frame format conversions that happen at filter boundaries."""

    @pytest.mark.benchmark(group="frame_conversion")
    def test_rgb_to_bgr_480p(self, benchmark):
        frame = _rgb_frame(480, 640).ro
        benchmark(lambda: frame.bgr)

    @pytest.mark.benchmark(group="frame_conversion")
    def test_bgr_to_rgb_480p(self, benchmark):
        image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        frame = Frame(image, {}, "BGR").ro
        benchmark(lambda: frame.rgb)

    @pytest.mark.benchmark(group="frame_conversion")
    def test_ro_to_rw_480p(self, benchmark):
        frame = _rgb_frame(480, 640).ro
        benchmark(lambda: frame.rw)

    @pytest.mark.benchmark(group="frame_conversion")
    def test_rw_bgr_480p(self, benchmark):
        """Combined rw+bgr conversion (common filter entry pattern)."""
        frame = _rgb_frame(480, 640).ro
        benchmark(lambda: frame.rw_bgr)

    @pytest.mark.benchmark(group="frame_conversion")
    def test_rgb_to_bgr_1080p(self, benchmark):
        frame = _rgb_frame(1080, 1920).ro
        benchmark(lambda: frame.bgr)


# ---------------------------------------------------------------------------
# Group: timing_injection — _inject_timings overhead per frame
# ---------------------------------------------------------------------------


class TestTimingInjectionBenchmarks:
    """Benchmarks for the per-filter timing metadata injection."""

    @staticmethod
    def _make_bare_filter(**overrides):
        """Create a Filter bypassing __init__."""
        import queue

        f = object.__new__(Filter)
        f._filter_time_in = 0.0
        f._filter_time_out = 0.0
        f._process_time_ema = 0.0
        f._frame_total_time_ema = 0.0
        f._frame_avg_time_ema = 0.0
        f._frame_std_time_ema = 0.0
        f._is_last_filter = False
        f.filter_name = "BenchFilter"
        f.pipeline_id = "bench-pipeline"
        f.emitter = None
        f._telemetry = None
        f._metadata_queue = queue.Queue()
        f._csv_exporter = None
        for k, v in overrides.items():
            setattr(f, k, v)
        return f

    @pytest.mark.benchmark(group="timing_injection")
    def test_inject_timings_mid_filter(self, benchmark):
        filt = self._make_bare_filter()

        def run():
            frames = {"main": _frame_with_meta(480, 640)}
            filt._inject_timings(frames, 1000.0, 1000.005, 5.0)

        benchmark(run)

    @pytest.mark.benchmark(group="timing_injection")
    def test_inject_timings_last_filter(self, benchmark):
        filt = self._make_bare_filter(_is_last_filter=True)

        def run():
            frames = {"main": _frame_with_meta(480, 640)}
            filt._inject_timings(frames, 1000.0, 1000.005, 5.0)

        benchmark(run)

    @pytest.mark.benchmark(group="timing_injection")
    def test_inject_timings_10_topics(self, benchmark):
        filt = self._make_bare_filter(_is_last_filter=True)

        def run():
            frames = {f"topic_{i}": _frame_with_meta(480, 640) for i in range(10)}
            filt._inject_timings(frames, 1000.0, 1000.005, 5.0)

        benchmark(run)

    @pytest.mark.benchmark(group="timing_injection")
    def test_update_process_time_ema(self, benchmark):
        filt = self._make_bare_filter()
        benchmark(filt._update_process_time_ema, 5.0)


# ---------------------------------------------------------------------------
# Group: zmq_ipc — end-to-end ZMQ send/recv (real IPC transport)
# ---------------------------------------------------------------------------


class TestZmqIpcBenchmarks:
    """Benchmarks for actual ZMQ send/recv round-trips over IPC sockets.

    Uses manual timing (not pytest-benchmark) because the ZMQ request-response
    synchronization is incompatible with the benchmark framework's calibration.
    """

    N_FRAMES = 50

    def _measure_roundtrip(self, addr, mq_id, frames, outs_jpg=False, n_frames=None):
        """Run n_frames through a ThreadMQSender → MQReceiver pair and return avg ms."""
        n = n_frames or self.N_FRAMES
        sender = ThreadMQSender(
            addr, f"{mq_id}-send", outs_jpg=outs_jpg, outs_metrics=False
        )
        receiver = MQReceiver(addr, f"{mq_id}-recv")

        try:
            # Warm up
            for _ in range(2):
                sender.send(frames)
                result = receiver.recv(timeout=5000)
                if result is None:
                    pytest.fail("receiver.recv() timed out during warm-up")

            t0 = time.perf_counter()
            for _ in range(n):
                sender.send(frames)
                result = receiver.recv(timeout=5000)
                if result is None:
                    pytest.fail("receiver.recv() timed out during measurement")
            elapsed = time.perf_counter() - t0
        finally:
            # Cleanup: destroy sender before receiver to avoid ZMQ PUSH blocking
            sender.destroy()
            receiver.destroy()

        return (elapsed / n) * 1000

    @pytest.mark.slow
    def test_zmq_roundtrip_report(self, caplog):
        caplog.set_level(logging.CRITICAL)

        scenarios = [
            ("data-only", {"main": Frame({"count": 0})}, False, 50),
            ("480p raw", {"main": FRAME_480P().ro}, False, 50),
            ("480p jpg", {"main": FRAME_480P().ro}, True, 50),
            ("1080p raw", {"main": FRAME_1080P().ro}, False, 30),
            ("1080p jpg", {"main": FRAME_1080P().ro}, True, 30),
            ("4K raw", {"main": FRAME_4K().ro}, False, 10),
            ("4K jpg", {"main": FRAME_4K().ro}, True, 10),
        ]

        _ctr = [0]

        print("\n" + "=" * 72)
        print("ZMQ IPC ROUND-TRIP LATENCY (ThreadMQSender → MQReceiver)")
        print("-" * 72)
        print(f"{'Scenario':>15} {'Avg (ms)':>12} {'@60fps budget':>15}")
        print("-" * 72)

        for label, frames, jpg, n in scenarios:
            _ctr[0] += 1
            addr = f"ipc:///tmp/bench-zmq-{_ctr[0]}-{id(self)}"
            avg_ms = self._measure_roundtrip(addr, f"z{_ctr[0]}", frames, jpg, n)
            pct = avg_ms / 16.67 * 100
            print(f"{label:>15} {avg_ms:>12.3f} {pct:>13.1f}%")

        print("=" * 72)


# ---------------------------------------------------------------------------
# Group: overhead_ratio — quantify IPC+serde overhead as % of total per-frame time
# ---------------------------------------------------------------------------


# Pipeline scenarios lifted to module scope so external tooling
# (scripts/measure_pipelines.py, scripts/profile_pipeline.py) can import
# the same topology definitions the bench uses — if a runtime refactor
# changes what a "pipeline" looks like, this dict gets updated here and
# the tooling picks the change up automatically.
PIPELINE_SIMULATION_SCENARIOS: dict[str, dict] = {
    "4k_to_1080p_raw": {
        "label":  "4K→1080p, 3 filters, raw",
        "stages": [
            ("VideoIn(4K→1080p)", 0.2, (1080, 1920), False),  # resample cost
            ("Detector",         15,   None,         False),
            ("Tracker",           5,   None,         False),
            ("Sink",              0,   None,         False),
        ],
    },
    "4k_to_1080p_jpg": {
        "label":  "4K→1080p, 3 filters, jpg",
        "stages": [
            ("VideoIn(4K→1080p)", 0.2, (1080, 1920), True),
            ("Detector",         15,   None,         True),
            ("Tracker",           5,   None,         True),
            ("Sink",              0,   None,         True),
        ],
    },
    "1080p_raw": {
        "label":  "1080p, 4 filters, raw",
        "stages": [
            ("VideoIn(1080p)",   0, (1080, 1920), False),
            ("Preprocess",       2, None,         False),
            ("Inference",       30, None,         False),
            ("Postprocess",      3, None,         False),
            ("Sink",             0, None,         False),
        ],
    },
    "480p_raw": {
        "label":  "480p, 3 filters, raw (fast path)",
        "stages": [
            ("VideoIn(480p)",    0, (480, 640), False),
            ("Detector",         8, None,       False),
            ("Tracker",          3, None,       False),
            ("Sink",             0, None,       False),
        ],
    },
    "4k_raw": {
        "label":  "4K native, 2 filters, raw",
        "stages": [
            ("VideoIn(4K)",      0, (2160, 3840), False),
            ("Detector",        20, None,         False),
            ("Sink",             0, None,         False),
        ],
    },
    "4k_jpg": {
        "label":  "4K native, 2 filters, jpg",
        "stages": [
            ("VideoIn(4K)",      0, (2160, 3840), True),
            ("Detector",        20, None,         True),
            ("Sink",             0, None,         True),
        ],
    },
}


class TestPipelineSimulation:
    """Simulates realistic multi-filter pipelines end-to-end.

    Models real pipeline topologies:
      - VideoIn(4K, resize=1080p) → DetectorFilter(15ms) → TrackerFilter(5ms) → VideoOut
      - VideoIn(1080p) → PreprocessFilter(2ms) → InferenceFilter(30ms) → PostprocessFilter(3ms)

    Each hop is a real ZMQ IPC send→recv. Filter work is simulated with
    time.sleep (representing actual process() time). The test measures total
    wall time and reports the overhead breakdown.
    """

    N_FRAMES = 20

    @staticmethod
    def _run_pipeline(stages, n_frames, label):
        """Run a simulated pipeline and return timing results.

        Args:
            stages: list of (name, process_ms, resolution, jpg) tuples.
                    resolution is (h, w) or None to reuse previous frame.
                    First stage is the source (process_ms = resample time).
            n_frames: number of frames to push through.
            label: human-readable pipeline name.
        """
        logger = logging.getLogger("openfilter")
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)

        senders = []
        receivers = []
        try:
            # Build the ZMQ chain: stage[i] sender → stage[i+1] receiver
            n_hops = len(stages) - 1

            for i in range(n_hops):
                _, _, _, jpg = stages[i]
                addr = f"ipc:///tmp/bench-pipe-{label}-{i}-{id(stages)}"
                senders.append(
                    ThreadMQSender(addr, f"p{i}s", outs_jpg=jpg, outs_metrics=False)
                )
                receivers.append(MQReceiver(addr, f"p{i}r"))

            # Build source frame
            src_name, src_process_ms, src_res, src_jpg = stages[0]
            if src_res:
                source_frame = _rgb_frame(*src_res)
            else:
                source_frame = Frame({"source": True})

            # Warm up
            if senders:
                for _ in range(2):
                    senders[0].send({"main": source_frame.ro})
                    f = receivers[0].recv(timeout=5000)
                    if f is None:
                        pytest.fail(f"Pipeline {label}: recv timed out during warm-up at hop 0")
                    for j in range(1, n_hops):
                        senders[j].send(f)
                        f = receivers[j].recv(timeout=5000)
                        if f is None:
                            pytest.fail(f"Pipeline {label}: recv timed out during warm-up at hop {j}")

            # Measure
            per_stage_process = [0.0] * len(stages)
            per_hop_ipc       = [0.0] * n_hops
            total_elapsed     = 0.0

            for _ in range(n_frames):
                t0 = time.perf_counter()

                # Source stage: simulate VideoIn read + optional resample
                if src_process_ms > 0:
                    tp = time.perf_counter()
                    time.sleep(src_process_ms / 1000)
                    per_stage_process[0] += time.perf_counter() - tp

                # Send source frame into pipeline
                current_frames = {"main": source_frame.ro}

                for hop in range(n_hops):
                    # Send to next filter
                    t_hop = time.perf_counter()
                    senders[hop].send(current_frames)
                    current_frames = receivers[hop].recv(timeout=5000)
                    if current_frames is None:
                        pytest.fail(f"Pipeline {label}: recv timed out at hop {hop}")
                    per_hop_ipc[hop] += time.perf_counter() - t_hop

                    # Simulate filter process()
                    _, proc_ms, _, _ = stages[hop + 1]
                    if proc_ms > 0:
                        tp = time.perf_counter()
                        time.sleep(proc_ms / 1000)
                        per_stage_process[hop + 1] += time.perf_counter() - tp

                total_elapsed += time.perf_counter() - t0
        finally:
            # Cleanup: destroy senders first to avoid ZMQ PUSH blocking on missing PULL peer
            for s in senders:
                s.destroy()
            for r in receivers:
                r.destroy()
            logger.setLevel(original_level)

        avg_total_ms = (total_elapsed / n_frames) * 1000
        avg_process_ms = sum(per_stage_process) / n_frames * 1000
        avg_overhead_ms = avg_total_ms - avg_process_ms
        overhead_pct = (avg_overhead_ms / avg_total_ms * 100) if avg_total_ms > 0 else 0
        fps = 1000 / avg_total_ms if avg_total_ms > 0 else float("inf")

        stage_times = [round(t / n_frames * 1000, 2) for t in per_stage_process]
        hop_times   = [round(t / n_frames * 1000, 2) for t in per_hop_ipc]

        return {
            "label": label,
            "stages": stages,
            "stage_times_ms": stage_times,
            "hop_times_ms": hop_times,
            "total_ms": round(avg_total_ms, 2),
            "process_ms": round(avg_process_ms, 2),
            "overhead_ms": round(avg_overhead_ms, 2),
            "overhead_pct": round(overhead_pct, 1),
            "n_hops": n_hops,
            "max_fps": round(fps, 1),
        }

    @pytest.mark.slow
    def test_pipeline_simulation_report(self):
        """Run several realistic pipeline configurations and report overhead."""

        results = []
        for scenario in PIPELINE_SIMULATION_SCENARIOS.values():
            label  = scenario["label"]
            stages = scenario["stages"]
            r = self._run_pipeline(
                stages, self.N_FRAMES, label.replace(" ", "-").replace(",", "")
            )
            results.append(r)

        # Print report
        print("\n" + "=" * 88)
        print("PIPELINE SIMULATION — IPC/SERDE OVERHEAD IN REALISTIC TOPOLOGIES")
        print("=" * 88)

        for r in results:
            stages = r["stages"]
            print(f"\n  {r['label']}")
            print(f"  {'─' * 80}")

            # Show pipeline diagram
            chain = " → ".join(f"{s[0]}({s[1]}ms)" if s[1] else s[0] for s in stages)
            print(f"  {chain}")
            print()

            # Per-stage breakdown
            for i, (stage, t_ms) in enumerate(zip(stages, r["stage_times_ms"])):
                name = stage[0]
                print(f"    {name:.<30s} {t_ms:>8.2f} ms  (process)")

            print(
                f"    {'IPC overhead':.<30s} {r['overhead_ms']:>8.2f} ms  "
                f"({r['n_hops']} hops × ~{r['overhead_ms']/r['n_hops']:.2f} ms/hop)"
            )
            print(f"    {'─' * 46}")
            print(
                f"    {'TOTAL':.<30s} {r['total_ms']:>8.2f} ms  "
                f"→ {r['max_fps']} fps max  "
                f"(overhead: {r['overhead_pct']}%)"
            )

        # Summary table
        print("\n" + "=" * 88)
        print(
            f"{'Pipeline':>40s} {'Total':>8} {'Filter':>8} {'IPC':>8} {'OH%':>6} {'FPS':>6}"
        )
        print("-" * 88)
        for r in results:
            print(
                f"{r['label']:>40s} "
                f"{r['total_ms']:>7.1f}  "
                f"{r['process_ms']:>7.1f}  "
                f"{r['overhead_ms']:>7.1f}  "
                f"{r['overhead_pct']:>5.1f}  "
                f"{r['max_fps']:>5.1f}"
            )
        print("=" * 88)

        # Sanity: 480p fast path should be under 15ms overhead
        fast_path = next(r for r in results if "480p" in r["label"])
        if fast_path["overhead_ms"] >= 15.0:
            warnings.warn(
                f"480p fast-path overhead {fast_path['overhead_ms']:.1f}ms "
                f"exceeded 15ms target"
            )


# ---------------------------------------------------------------------------
# Group: frame_sizes — compare overhead across resolutions
# ---------------------------------------------------------------------------


class TestFrameSizeScaling:
    """Shows how serialization cost scales with frame resolution."""

    @pytest.mark.benchmark(group="frame_sizes")
    def test_serialize_480p(self, benchmark):
        benchmark(MQ.frames2topicmsgs, {"main": FRAME_480P()}, False)

    @pytest.mark.benchmark(group="frame_sizes")
    def test_serialize_720p(self, benchmark):
        benchmark(MQ.frames2topicmsgs, {"main": FRAME_720P()}, False)

    @pytest.mark.benchmark(group="frame_sizes")
    def test_serialize_1080p(self, benchmark):
        benchmark(MQ.frames2topicmsgs, {"main": FRAME_1080P()}, False)

    @pytest.mark.benchmark(group="frame_sizes")
    def test_deserialize_480p(self, benchmark):
        msgs = MQ.frames2topicmsgs({"main": FRAME_480P()}, False)
        benchmark(MQ.topicmsgs2frames, msgs)

    @pytest.mark.benchmark(group="frame_sizes")
    def test_deserialize_720p(self, benchmark):
        msgs = MQ.frames2topicmsgs({"main": FRAME_720P()}, False)
        benchmark(MQ.topicmsgs2frames, msgs)

    @pytest.mark.benchmark(group="frame_sizes")
    def test_deserialize_1080p(self, benchmark):
        msgs = MQ.frames2topicmsgs({"main": FRAME_1080P()}, False)
        benchmark(MQ.topicmsgs2frames, msgs)

    @pytest.mark.benchmark(group="frame_sizes")
    def test_serialize_4k(self, benchmark):
        benchmark(MQ.frames2topicmsgs, {"main": FRAME_4K()}, False)

    @pytest.mark.benchmark(group="frame_sizes")
    def test_deserialize_4k(self, benchmark):
        msgs = MQ.frames2topicmsgs({"main": FRAME_4K()}, False)
        benchmark(MQ.topicmsgs2frames, msgs)


# ---------------------------------------------------------------------------
# Group: resample — cv2.resize cost (VideoIn on-line resampling)
# ---------------------------------------------------------------------------


class TestResampleBenchmarks:
    """Benchmarks for cv2.resize at various resolutions and interpolation modes.

    This simulates VideoIn's on-line resampling when maxsize or resize is set.
    At 60fps you have 16.7ms per frame — this shows how much resampling eats.
    """

    @pytest.mark.benchmark(group="resample")
    def test_4k_to_1080p_linear(self, benchmark):
        image = FRAME_4K().image
        benchmark(cv2.resize, image, (1920, 1080), interpolation=cv2.INTER_LINEAR)

    @pytest.mark.benchmark(group="resample")
    def test_4k_to_1080p_nearest(self, benchmark):
        image = FRAME_4K().image
        benchmark(cv2.resize, image, (1920, 1080), interpolation=cv2.INTER_NEAREST)

    @pytest.mark.benchmark(group="resample")
    def test_4k_to_1080p_cubic(self, benchmark):
        image = FRAME_4K().image
        benchmark(cv2.resize, image, (1920, 1080), interpolation=cv2.INTER_CUBIC)

    @pytest.mark.benchmark(group="resample")
    def test_4k_to_720p_linear(self, benchmark):
        image = FRAME_4K().image
        benchmark(cv2.resize, image, (1280, 720), interpolation=cv2.INTER_LINEAR)

    @pytest.mark.benchmark(group="resample")
    def test_4k_to_480p_linear(self, benchmark):
        image = FRAME_4K().image
        benchmark(cv2.resize, image, (640, 480), interpolation=cv2.INTER_LINEAR)

    @pytest.mark.benchmark(group="resample")
    def test_1080p_to_720p_linear(self, benchmark):
        image = FRAME_1080P().image
        benchmark(cv2.resize, image, (1280, 720), interpolation=cv2.INTER_LINEAR)

    @pytest.mark.benchmark(group="resample")
    def test_1080p_to_480p_linear(self, benchmark):
        image = FRAME_1080P().image
        benchmark(cv2.resize, image, (640, 480), interpolation=cv2.INTER_LINEAR)

    @pytest.mark.benchmark(group="resample")
    def test_4k_to_1080p_then_serialize_raw(self, benchmark):
        """Full VideoIn path: resample + serialize (raw) — total IPC cost."""
        image_4k = FRAME_4K().image

        def resample_and_serialize():
            resized = cv2.resize(image_4k, (1920, 1080), interpolation=cv2.INTER_LINEAR)
            frame = Frame(resized, {}, "RGB")
            return MQ.frames2topicmsgs({"main": frame}, False)

        benchmark(resample_and_serialize)

    @pytest.mark.benchmark(group="resample")
    def test_4k_to_1080p_then_serialize_jpg(self, benchmark):
        """Full VideoIn path: resample + serialize (jpg) — total IPC cost."""
        image_4k = FRAME_4K().image

        def resample_and_serialize():
            resized = cv2.resize(image_4k, (1920, 1080), interpolation=cv2.INTER_LINEAR)
            frame = Frame(resized, {}, "RGB")
            return MQ.frames2topicmsgs({"main": frame}, True)

        benchmark(resample_and_serialize)
