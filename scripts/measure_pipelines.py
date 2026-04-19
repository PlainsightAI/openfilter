#!/usr/bin/env python3
"""Run a fixed set of pipeline scenarios and dump timing JSON to stdout.

This script is a thin wrapper around
``tests.test_benchmarks.TestPipelineSimulation._run_pipeline`` — it
imports the bench harness's scenario definitions and measurement loop
directly so that any refactor to the runtime's pipeline composition
model automatically propagates through. If the bench gets updated,
this script (and the waterfall display that consumes its output)
picks the change up on the next run.

Output schema (single JSON object on stdout):

    {
      "git_ref":   "feat/perf-waterfall" | "main" | "<sha>",
      "git_sha":   "...",
      "summary": [
        {
          "name":         "4k_raw",
          "label":        "4K native, 2 filters, raw",
          "hops":         2,
          "frames":       200,
          "total_ms":     40.35,
          "filter_ms":    20.07,
          "ipc_ms":       20.26,
          "ipc_per_hop":  10.13,
          "max_fps":      24.8
        },
        ...
      ],
      "waterfall": {
        "label":  "4K native, 2 filters, raw",
        "frames": 200,
        "stages": [
          {"name": "VideoIn(4K)",  "kind": "filter", "ms": 0.0},
          {"name": "hop-0",        "kind": "ipc",    "ms": 7.5},
          {"name": "Detector",     "kind": "filter", "ms": 20.0},
          {"name": "hop-1",        "kind": "ipc",    "ms": 6.5},
          {"name": "Sink",         "kind": "filter", "ms": 0.0}
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


# The bench harness lives under tests/; import it via sys.path so we
# can use its scenario definitions and _run_pipeline method directly.
sys.path.insert(0, "tests")
from test_benchmarks import (  # noqa: E402
    PIPELINE_SIMULATION_SCENARIOS,
    TestPipelineSimulation,
)


def _run_pipeline(name: str, frames: int) -> dict:
    """Run a single pipeline scenario via the bench harness; return our summary shape."""
    scenario = PIPELINE_SIMULATION_SCENARIOS[name]
    label    = scenario["label"]
    stages   = scenario["stages"]

    r = TestPipelineSimulation._run_pipeline(
        stages, frames, label.replace(" ", "-").replace(",", "")
    )

    return {
        "name":         name,
        "label":        label,
        "stages":       [s[0] for s in stages],
        "stage_ms":     r["stage_times_ms"],
        "hops":         r["n_hops"],
        "hop_ms":       r["hop_times_ms"],
        "frames":       frames,
        "total_ms":     r["total_ms"],
        "filter_ms":    r["process_ms"],
        "ipc_ms":       r["overhead_ms"],
        "ipc_per_hop":  (r["overhead_ms"] / r["n_hops"]) if r["n_hops"] else 0.0,
        "max_fps":      r["max_fps"],
    }


def _waterfall_from_run(run: dict) -> dict:
    """Convert a per-pipeline run into a stage-by-stage waterfall structure."""
    stage_names = run["stages"]
    stage_ms    = run["stage_ms"]
    hop_ms      = run["hop_ms"]

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
    p.add_argument("--pipeline", default="4k_raw", choices=sorted(PIPELINE_SIMULATION_SCENARIOS),
                   help="Pipeline used for the per-frame waterfall (default 4k_raw)")
    p.add_argument("--only", nargs="*", default=None, choices=sorted(PIPELINE_SIMULATION_SCENARIOS),
                   help="If set, only run these pipelines for the summary table")
    args = p.parse_args()

    logging.getLogger("openfilter").setLevel(logging.CRITICAL)

    pipelines_to_run = list(args.only) if args.only else list(PIPELINE_SIMULATION_SCENARIOS)
    if args.pipeline not in pipelines_to_run:
        pipelines_to_run.append(args.pipeline)

    ref, sha = _git_info()

    summary   = []
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
