#!/usr/bin/env python3
"""Standalone pipeline reproducer for profiling IPC/serde overhead.

Thin wrapper around
``tests.test_benchmarks.TestPipelineSimulation._run_pipeline`` so the
profile reproducer uses exactly the same topology, timing loop, and
scenario definitions as the bench harness. If the runtime's pipeline
composition model changes, the bench gets updated and this script
automatically follows — no hand-rolled duplicate of the pipeline loop
to drift out of sync.

Use this when attaching ``py-spy record`` (or ``perf``, ``strace``,
etc.) to capture a clean flamegraph. The pytest harness adds layers
of fixture / collection / reporting overhead that pollute profiles;
running the same scenario through this entrypoint gives py-spy a
single-purpose Python process to sample.

Example:
    py-spy record -o /tmp/4k.svg --native --rate 250 -- \\
        uv run python scripts/profile_pipeline.py 4k_raw --frames 400

    # Pure IPC (no simulated filter work) — zeroes filter sleeps so
    # the profile doesn't get dominated by `time.sleep` samples:
    uv run python scripts/profile_pipeline.py 4k_raw --frames 400 --no-filter-work
"""

from __future__ import annotations

import argparse
import logging
import sys


sys.path.insert(0, "tests")
from test_benchmarks import (  # noqa: E402
    PIPELINE_SIMULATION_SCENARIOS,
    TestPipelineSimulation,
)


def _stages_without_filter_work(stages: list[tuple]) -> list[tuple]:
    """Return a copy of the stages list with all process_ms zeroed out."""
    return [(name, 0, res, jpg) for (name, _proc, res, jpg) in stages]


def run(preset: str, frames: int, no_filter_work: bool) -> None:
    scenario = PIPELINE_SIMULATION_SCENARIOS[preset]
    label    = scenario["label"]
    stages   = scenario["stages"]
    if no_filter_work:
        stages = _stages_without_filter_work(stages)

    logging.getLogger("openfilter").setLevel(logging.CRITICAL)

    r = TestPipelineSimulation._run_pipeline(stages, frames, f"profile-{preset}")

    n_hops      = r["n_hops"]
    total_ms    = r["total_ms"]
    process_ms  = r["process_ms"]
    overhead_ms = r["overhead_ms"]
    hop_ms      = r["hop_times_ms"]

    print(f"preset             : {preset}  ({label})")
    print(f"frames             : {frames}")
    print(f"hops               : {n_hops}")
    print(f"filter work        : {'skipped' if no_filter_work else 'simulated with time.sleep'}")
    print(f"avg total / frame  : {total_ms:7.2f} ms")
    print(f"avg filter / frame : {process_ms:7.2f} ms")
    print(f"avg IPC OH / frame : {overhead_ms:7.2f} ms  ({overhead_ms / n_hops:.2f} ms/hop avg)")
    if n_hops > 1:
        for i, h in enumerate(hop_ms):
            print(f"   hop {i:>2}            : {h:7.2f} ms")
    print(f"max FPS            : {1000 / total_ms:7.1f}" if total_ms > 0 else "max FPS            : inf")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("preset", choices=sorted(PIPELINE_SIMULATION_SCENARIOS),
                   help="Pipeline topology to run")
    p.add_argument("--frames", type=int, default=200, help="Number of frames to push (default: 200)")
    p.add_argument("--no-filter-work", action="store_true",
                   help="Zero out the simulated process() sleeps so the profile shows pure IPC cost")
    args = p.parse_args()
    run(args.preset, args.frames, args.no_filter_work)


if __name__ == "__main__":
    main()
