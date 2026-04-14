#!/usr/bin/env python3
"""Run a fixed set of pipeline scenarios and dump timing JSON to stdout.

Self-contained: imports only stdlib + numpy + the local ``openfilter``
package, so the same script can be dropped into any worktree (current
branch or any historical ref) and produce comparable measurements.

Output schema (printed as a single JSON object on stdout):

    {
      "git_ref":   "feat/perf-fixes" | "main" | "<sha>",
      "git_sha":   "...",
      "summary": [
        {
          "label":         "4K native, 2 filters, raw",
          "hops":          2,
          "frames":        200,
          "total_ms":      40.35,
          "filter_ms":     20.07,
          "ipc_ms":        20.26,
          "ipc_per_hop":   10.13,
          "max_fps":       24.8
        },
        ...
      ],
      "waterfall": {
        "label":  "4K native, 2 filters, raw",
        "frames": 100,
        "stages": [
          {"name": "VideoIn",  "kind": "filter", "ms": 0.0},
          {"name": "hop-0",    "kind": "ipc",    "ms": 7.5},
          {"name": "Detector", "kind": "filter", "ms": 20.0},
          {"name": "hop-1",    "kind": "ipc",    "ms": 6.5},
          {"name": "Sink",     "kind": "filter", "ms": 0.0}
        ]
      }
    }

Run:
    uv run python scripts/measure_pipelines.py [--frames N] [--pipeline 4k_raw]
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time

import numpy as np

# ThreadMQSender lives in tests/helpers.py — this script must run from a
# worktree where that file exists. (It does on every ref since PR #77.)
sys.path.insert(0, "tests")
from helpers import ThreadMQSender  # noqa: E402

from openfilter.filter_runtime import Frame  # noqa: E402
from openfilter.filter_runtime.mq import MQReceiver  # noqa: E402


# ---------------------------------------------------------------------------
# Pipeline definitions — kept identical across refs so measurements compare.
# ---------------------------------------------------------------------------

PIPELINES: dict[str, dict] = {
    "4k_raw": {
        "label":  "4K native, 2 filters, raw",
        "shape":  (2160, 3840),
        "jpg":    False,
        "stages": [("VideoIn",   0),
                   ("Detector", 20),
                   ("Sink",      0)],
    },
    "1080p_raw": {
        "label":  "1080p, 4 filters, raw",
        "shape":  (1080, 1920),
        "jpg":    False,
        "stages": [("VideoIn",      0),
                   ("Preprocess",   2),
                   ("Inference",   30),
                   ("Postprocess",  3),
                   ("Sink",         0)],
    },
    "4k_to_1080p_raw": {
        "label":  "4K→1080p, 3 filters, raw",
        "shape":  (1080, 1920),  # already resampled at source
        "jpg":    False,
        "stages": [("VideoIn",   0.2),
                   ("Detector", 15),
                   ("Tracker",   5),
                   ("Sink",      0)],
    },
    "480p_raw": {
        "label":  "480p, 3 filters, raw (fast path)",
        "shape":  (480, 640),
        "jpg":    False,
        "stages": [("VideoIn",   0),
                   ("Detector",  8),
                   ("Tracker",   3),
                   ("Sink",      0)],
    },
}


# ---------------------------------------------------------------------------
# Measurement core
# ---------------------------------------------------------------------------

def _run_pipeline(name: str, frames: int) -> dict:
    """Push ``frames`` frames through the given preset; return aggregate stats.

    Mirrors the bench's pipeline_simulation pattern (fresh ``.ro`` per
    iteration + filter sleep) so wins/regressions show up identically.
    """
    cfg    = PIPELINES[name]
    stages = cfg["stages"]
    n_hops = len(stages) - 1
    h, w   = cfg["shape"]
    jpg    = cfg["jpg"]

    senders:   list[ThreadMQSender] = []
    receivers: list[MQReceiver] = []

    try:
        for i in range(n_hops):
            addr = f"ipc:///tmp/perf-waterfall-{name}-{i}"
            senders.append(ThreadMQSender(addr, f"p{i}s", outs_jpg=jpg, outs_metrics=False))
            receivers.append(MQReceiver(addr, f"p{i}r"))

        src_frame = Frame(np.random.randint(0, 255, (h, w, 3), dtype=np.uint8), {"source": True}, "RGB")

        # warm up
        for _ in range(3):
            f = {"main": src_frame.ro}
            for hop in range(n_hops):
                senders[hop].send(f)
                f = receivers[hop].recv(timeout=5000)

        per_stage_filter = [0.0] * len(stages)
        per_hop_ipc      = [0.0] * n_hops
        t_total          = 0.0

        for _ in range(frames):
            t0 = time.perf_counter()
            f  = {"main": src_frame.ro}

            for hop in range(n_hops):
                t_send = time.perf_counter()
                senders[hop].send(f)
                f = receivers[hop].recv(timeout=5000)
                per_hop_ipc[hop] += time.perf_counter() - t_send

                proc_ms = stages[hop + 1][1]
                if proc_ms:
                    tp = time.perf_counter()
                    time.sleep(proc_ms / 1000)
                    per_stage_filter[hop + 1] += time.perf_counter() - tp

            t_total += time.perf_counter() - t0

        avg_total_ms  = t_total / frames * 1000
        avg_filter_ms = sum(per_stage_filter) / frames * 1000
        avg_ipc_ms    = avg_total_ms - avg_filter_ms

        per_hop_ms     = [t / frames * 1000 for t in per_hop_ipc]
        per_stage_ms   = [t / frames * 1000 for t in per_stage_filter]

        return {
            "name":         name,
            "label":        cfg["label"],
            "stages":       [s[0] for s in stages],
            "stage_ms":     per_stage_ms,
            "hops":         n_hops,
            "hop_ms":       per_hop_ms,
            "frames":       frames,
            "total_ms":     avg_total_ms,
            "filter_ms":    avg_filter_ms,
            "ipc_ms":       avg_ipc_ms,
            "ipc_per_hop":  avg_ipc_ms / n_hops if n_hops else 0.0,
            "max_fps":      1000.0 / avg_total_ms if avg_total_ms > 0 else float("inf"),
        }

    finally:
        for s in senders:
            s.destroy()
        for r in receivers:
            r.destroy()


def _waterfall_from_run(run: dict) -> dict:
    """Convert a per-pipeline run into a stage-by-stage waterfall structure."""
    stage_names  = run["stages"]
    stage_ms     = run["stage_ms"]
    hop_ms       = run["hop_ms"]

    waterfall = []
    for i, name in enumerate(stage_names):
        waterfall.append({"name": name, "kind": "filter", "ms": stage_ms[i]})
        if i < len(hop_ms):
            waterfall.append({"name": f"hop-{i}", "kind": "ipc", "ms": hop_ms[i]})

    return {
        "label":  run["label"],
        "frames": run["frames"],
        "stages": waterfall,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _git_info() -> tuple[str, str]:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        sha = "unknown"
    try:
        ref = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    except Exception:
        ref = "unknown"
    return ref, sha


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames",   type=int, default=200, help="Frames per pipeline (default 200)")
    p.add_argument("--pipeline", default="4k_raw", choices=sorted(PIPELINES),
                   help="Pipeline used for the per-frame waterfall (default 4k_raw)")
    p.add_argument("--only", nargs="*", default=None, choices=sorted(PIPELINES),
                   help="If set, only run these pipelines for the summary table")
    args = p.parse_args()

    logging.getLogger("openfilter").setLevel(logging.CRITICAL)

    pipelines_to_run = args.only if args.only else sorted(PIPELINES)
    if args.pipeline not in pipelines_to_run:
        pipelines_to_run = list(pipelines_to_run) + [args.pipeline]

    ref, sha = _git_info()

    summary = []
    waterfall = None
    for name in pipelines_to_run:
        run = _run_pipeline(name, args.frames)
        summary.append({k: run[k] for k in ("name", "label", "hops", "frames",
                                            "total_ms", "filter_ms", "ipc_ms",
                                            "ipc_per_hop", "max_fps")})
        if name == args.pipeline:
            waterfall = _waterfall_from_run(run)

    out = {
        "git_ref":   ref,
        "git_sha":   sha,
        "summary":   summary,
        "waterfall": waterfall,
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
