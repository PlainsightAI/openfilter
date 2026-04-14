#!/usr/bin/env python3
"""Standalone pipeline reproducer for profiling IPC/serde overhead.

Mirrors the 4K/1080p/480p scenarios from
``tests/test_benchmarks.py::TestPipelineSimulation`` but runs outside of
pytest so you can attach ``py-spy record`` (or perf, strace, etc.) to it
without the bench harness noise.

Example:
    py-spy record -o /tmp/4k.svg --native --rate 250 -- \\
        uv run python scripts/profile_pipeline.py 4k_raw --frames 400

    # Pure IPC (no simulated filter work) — isolates the transport cost:
    uv run python scripts/profile_pipeline.py 4k_raw --frames 400 --no-filter-work
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import numpy as np

from openfilter.filter_runtime import Frame
from openfilter.filter_runtime.mq import MQReceiver

# Re-use the threaded sender from the bench harness so we match its topology.
sys.path.insert(0, "tests")
from helpers import ThreadMQSender  # noqa: E402


PRESETS: dict[str, dict] = {
    "4k_raw": {
        "shape": (2160, 3840),
        "jpg":   False,
        "stages": [("VideoIn", 0), ("Detector", 20), ("Sink", 0)],
    },
    "4k_jpg": {
        "shape": (2160, 3840),
        "jpg":   True,
        "stages": [("VideoIn", 0), ("Detector", 20), ("Sink", 0)],
    },
    "1080p_raw": {
        "shape": (1080, 1920),
        "jpg":   False,
        "stages": [("VideoIn", 0), ("Preprocess", 2), ("Inference", 30), ("Postprocess", 3), ("Sink", 0)],
    },
    "4k_to_1080p_raw": {
        "shape": (1080, 1920),  # already resampled at source
        "jpg":   False,
        "stages": [("VideoIn", 0.2), ("Detector", 15), ("Tracker", 5), ("Sink", 0)],
    },
    "480p_raw": {
        "shape": (480, 640),
        "jpg":   False,
        "stages": [("VideoIn", 0), ("Detector", 8), ("Tracker", 3), ("Sink", 0)],
    },
}


def run(preset: str, frames: int, no_filter_work: bool) -> None:
    cfg    = PRESETS[preset]
    stages = cfg["stages"]
    n_hops = len(stages) - 1
    h, w   = cfg["shape"]
    jpg    = cfg["jpg"]

    logging.getLogger("openfilter").setLevel(logging.CRITICAL)

    senders:   list[ThreadMQSender] = []
    receivers: list[MQReceiver] = []

    try:
        for i in range(n_hops):
            addr = f"ipc:///tmp/of-profile-{preset}-{i}"
            senders.append(ThreadMQSender(addr, f"p{i}s", outs_jpg=jpg, outs_metrics=False))
            receivers.append(MQReceiver(addr, f"p{i}r"))

        # Hoist .ro out of the loop: .ro on a writable source is copy-on-call,
        # and the runtime itself never invokes .ro — it's a filter convenience.
        # Keeping it inside the timing loop conflates IPC cost with a ~1ms/frame
        # bench-side memcpy.
        src_frame    = Frame(np.random.randint(0, 255, (h, w, 3), dtype=np.uint8), {"source": True}, "RGB")
        src_frame_ro = src_frame.ro

        for _ in range(3):  # warm up
            f = {"main": src_frame_ro}
            for hop in range(n_hops):
                senders[hop].send(f)
                f = receivers[hop].recv(timeout=5000)

        per_stage = [0.0] * len(stages)
        t_total   = 0.0

        for _ in range(frames):
            t0 = time.perf_counter()
            f  = {"main": src_frame_ro}

            for hop in range(n_hops):
                senders[hop].send(f)
                f = receivers[hop].recv(timeout=5000)

                if not no_filter_work:
                    proc_ms = stages[hop + 1][1]
                    if proc_ms:
                        tp = time.perf_counter()
                        time.sleep(proc_ms / 1000)
                        per_stage[hop + 1] += time.perf_counter() - tp

            t_total += time.perf_counter() - t0

        avg_total_ms    = t_total / frames * 1000
        avg_process_ms  = sum(per_stage) / frames * 1000
        avg_overhead_ms = avg_total_ms - avg_process_ms

        print(f"preset             : {preset}")
        print(f"frames             : {frames}")
        print(f"hops               : {n_hops}")
        print(f"filter work        : {'skipped' if no_filter_work else 'simulated with time.sleep'}")
        print(f"avg total / frame  : {avg_total_ms:7.2f} ms")
        print(f"avg filter / frame : {avg_process_ms:7.2f} ms")
        print(f"avg IPC OH / frame : {avg_overhead_ms:7.2f} ms  ({avg_overhead_ms / n_hops:.2f} ms/hop)")
        print(f"max FPS            : {1000 / avg_total_ms:7.1f}")

    finally:
        for s in senders:
            s.destroy()
        for r in receivers:
            r.destroy()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("preset", choices=sorted(PRESETS), help="Pipeline topology to run")
    p.add_argument("--frames", type=int, default=200, help="Number of frames to push (default: 200)")
    p.add_argument("--no-filter-work", action="store_true",
                   help="Skip the simulated process() sleep so profiles show pure IPC cost")
    args = p.parse_args()
    run(args.preset, args.frames, args.no_filter_work)


if __name__ == "__main__":
    main()
