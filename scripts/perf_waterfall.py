#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "rich>=13",
# ]
# ///
"""Terminal waterfall display for the IPC perf wins on this branch.

Measures pipeline IPC overhead at two git refs (one current, one
baseline) by running ``scripts/measure_pipelines.py`` against each, then
renders two terminal panels:

  1. Per-pipeline summary — grouped horizontal bars, ms IPC overhead
     plus delta percentage.
  2. Frame waterfall — single representative frame, stage-by-stage,
     baseline panel above current panel, with per-stage deltas
     annotated on the AFTER panel so you can see exactly where time
     moved.

The baseline ref is materialized as an ephemeral git worktree under
``/tmp``; the same measurement script is copied into it (so refs that
predate this branch can still be measured), ``uv run`` resolves the
``openfilter`` import to that worktree's project venv, and the temp
worktree is torn down afterward.

Dependencies are declared inline via PEP 723, so rich is pulled into an
ephemeral environment automatically — no pyproject changes, no install
step. Run directly with ``uv run`` or via the shebang.

    # default: compare HEAD vs origin/main
    uv run scripts/perf_waterfall.py

    # compare against any ref (branch, tag, sha)
    uv run scripts/perf_waterfall.py --baseline-ref feat/perf-fixes
    uv run scripts/perf_waterfall.py --baseline-ref c291174

    # tighter / wider runs
    uv run scripts/perf_waterfall.py --frames 400
    uv run scripts/perf_waterfall.py --pipeline 1080p_raw

    # save the raw JSON for later
    uv run scripts/perf_waterfall.py --save-json /tmp/perf.json
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.bar import Bar
from rich.box import HEAVY_HEAD, ROUNDED, SIMPLE
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.tree import Tree


console = Console()


# Plainsight brand palette — see docs/brand-guidelines.pptx. Hex values
# are authoritative; rich renders these as 24-bit truecolor on modern
# terminals and falls back to the nearest 256-color match elsewhere.
BRAND_LIGHT_SKY = "#B6CFD0"  # primary — "dawn"
BRAND_TURQUOISE = "#6399AE"  # primary
BRAND_PURPLE    = "#615E9B"  # primary
BRAND_GRAPE     = "#6D2077"  # primary — "sunset"
BRAND_DUSK      = "#E5E2E7"  # secondary, neutral light
BRAND_NOON      = "#73BDC5"  # secondary, bright teal
BRAND_MIDNIGHT  = "#242444"  # secondary, darkest
BRAND_SEAGULL   = "#7FA9AE"  # secondary
BRAND_GREY      = "#888B8D"  # neutral
BRAND_TWILIGHT  = "#2C5E8C"  # accent, deep blue
BRAND_FOREST    = "#006070"  # accent, deep teal

# Role → color. Structural chrome uses the brand palette; the diagnostic
# signals (win / loss / neutral) use conventional green / red / dim so
# they read at a glance. This is a diagnostic tool, not a deck.
IPC_STYLE     = BRAND_PURPLE      # under-the-hood machinery
FILTER_STYLE  = BRAND_TURQUOISE   # visible filter work
WIN_STYLE     = "bright_green"    # standard success
LOSS_STYLE    = "red"             # standard failure
NEUTRAL_STYLE = BRAND_GREY
AXIS_STYLE    = BRAND_SEAGULL
GRID_STYLE    = BRAND_GREY
HEADER_STYLE  = BRAND_TWILIGHT
TITLE_STYLE   = f"bold {BRAND_TWILIGHT}"


# ---------------------------------------------------------------------------
# Measurement orchestration
# ---------------------------------------------------------------------------

def _common_dir() -> Path:
    return Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True).strip()).resolve()


def _main_repo() -> Path:
    return _common_dir().parent


def _ref_to_sha(ref: str) -> str:
    return subprocess.check_output(["git", "rev-parse", ref], text=True).strip()


def _measurement_script() -> Path:
    return Path(__file__).resolve().parent / "measure_pipelines.py"


def measure_current(frames: int, pipeline: str) -> dict:
    """Run the measurement script in the current worktree and return JSON."""
    script = _measurement_script()
    r = subprocess.run(
        ["uv", "run", "python", str(script),
         "--frames", str(frames), "--pipeline", pipeline],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def measure_at_ref(ref: str, frames: int, pipeline: str) -> dict:
    """Materialize a temp git worktree at ``ref``, copy the measurement
    script AND the bench harness it depends on into it, run it, parse
    JSON, then tear the worktree down.

    We copy the bench harness (``tests/test_benchmarks.py``) alongside
    the measurement script so the baseline ref uses THIS branch's
    scenario definitions and timing loop. That's the comparison we
    want: same bench, different runtime. Without this, refs that
    predate our bench refactor would fail to import
    ``PIPELINE_SIMULATION_SCENARIOS``.
    """
    repo         = _main_repo()
    sha          = _ref_to_sha(ref)
    script_dir   = Path(__file__).resolve().parent
    current_root = script_dir.parent
    measure_src  = script_dir / "measure_pipelines.py"
    bench_src    = current_root / "tests" / "test_benchmarks.py"

    with tempfile.TemporaryDirectory(prefix="perf-waterfall-") as wt_dir:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", wt_dir, ref],
            check=True, capture_output=True, text=True,
        )
        try:
            wt = Path(wt_dir)
            (wt / "scripts").mkdir(exist_ok=True)
            (wt / "tests").mkdir(exist_ok=True)
            shutil.copy(measure_src, wt / "scripts" / "measure_pipelines.py")
            shutil.copy(bench_src,   wt / "tests"   / "test_benchmarks.py")

            r = subprocess.run(
                ["uv", "run", "python", "scripts/measure_pipelines.py",
                 "--frames", str(frames), "--pipeline", pipeline],
                cwd=wt_dir, capture_output=True, text=True, check=True,
            )
            data = json.loads(r.stdout)
            data["git_ref"] = ref  # rewrite — temp worktree reports detached HEAD
            data["git_sha"] = sha
            return data
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", wt_dir],
                check=False, capture_output=True,
            )


def _commits_between(base_sha: str, head_sha: str) -> list[tuple[str, str]]:
    try:
        out = subprocess.check_output(
            ["git", "log", "--reverse", "--format=%h %s", f"{base_sha}..{head_sha}"],
            text=True,
        )
    except Exception:
        return []
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        sha, _, subject = line.partition(" ")
        rows.append((sha, subject))
    return rows


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _nice_axis(max_value: float, target_ticks: int = 6) -> tuple[float, float]:
    """Pick a 'nice' (axis_max, tick_step) so tick labels land on round ms values."""
    if max_value <= 0:
        return 1.0, 1.0
    raw_step = max_value / target_ticks
    mag      = 10 ** math.floor(math.log10(raw_step))
    norm     = raw_step / mag
    step     = (1 if norm < 1.5 else 2 if norm < 3.5 else 5 if norm < 7.5 else 10) * mag
    axis_max = math.ceil(max_value / step) * step
    return axis_max, step


def _delta_text(curr: float, base: float, fmt: str = "{:+7.2f} ms", unit_ms: bool = True) -> Text:
    """A Text object for a numeric delta, colored green / red / dim."""
    delta = curr - base
    if abs(delta) < 0.05 and unit_ms:
        return Text("     ±0 ms" if unit_ms else "±0", style=NEUTRAL_STYLE)
    style = WIN_STYLE if delta < 0 else LOSS_STYLE
    return Text(fmt.format(delta), style=style)


def _pct_delta_text(curr: float, base: float) -> Text:
    if base <= 0:
        return Text("n/a", style=NEUTRAL_STYLE)
    pct = (curr - base) / base * 100
    if abs(pct) < 1:
        return Text(f"{pct:+5.1f}%", style=NEUTRAL_STYLE)
    style = WIN_STYLE if pct < 0 else LOSS_STYLE
    return Text(f"{pct:+5.1f}%", style=style)


# ---------------------------------------------------------------------------
# Summary panel
# ---------------------------------------------------------------------------

def build_summary_table(baseline: dict, current: dict) -> Table:
    base_by = {p["name"]: p for p in baseline["summary"]}
    curr_by = {p["name"]: p for p in current["summary"]}
    names   = [p["name"] for p in current["summary"] if p["name"] in base_by]

    table = Table(
        title=Text("IPC overhead — per-pipeline gains", style=TITLE_STYLE),
        title_justify="left",
        box=SIMPLE,
        header_style=f"bold {BRAND_SEAGULL}",
        pad_edge=False,
    )
    table.add_column("pipeline",   style="bold", no_wrap=True)
    table.add_column("",           ratio=1)  # bar column expands to fill available width
    table.add_column("ms saved",   justify="right", no_wrap=True)
    table.add_column("fps gained", justify="right", no_wrap=True)
    table.add_column("change",     justify="right", no_wrap=True)

    if not names:
        table.add_row(Text("(no overlapping pipelines between refs)", style=NEUTRAL_STYLE))
        return table

    # Gain = (baseline - current). Positive across all three columns == win.
    gains = [
        (curr_by[n]["label"],
         base_by[n]["ipc_ms"]  - curr_by[n]["ipc_ms"],
         curr_by[n]["max_fps"] - base_by[n]["max_fps"],
         ((base_by[n]["ipc_ms"] - curr_by[n]["ipc_ms"]) / base_by[n]["ipc_ms"] * 100)
             if base_by[n]["ipc_ms"] > 0 else 0.0)
        for n in names
    ]
    max_abs_ms = max((abs(g[1]) for g in gains), default=1.0)

    def signed(val: float, fmt: str) -> Text:
        if abs(val) < 0.05:
            return Text(" ±0", style=NEUTRAL_STYLE)
        return Text(fmt.format(val), style=WIN_STYLE if val > 0 else LOSS_STYLE)

    for label, ms, fps, pct in gains:
        if ms > 0.05:
            color = WIN_STYLE
        elif ms < -0.05:
            color = LOSS_STYLE
        else:
            color = NEUTRAL_STYLE
        table.add_row(
            Text(label),
            Bar(size=max_abs_ms, begin=0.0, end=abs(ms), color=color),
            signed(ms,  "{:+6.2f}"),
            signed(fps, "{:+5.1f}"),
            signed(pct, "{:+5.1f}%"),
        )

    return table


# ---------------------------------------------------------------------------
# Waterfall panel
# ---------------------------------------------------------------------------

def build_waterfall_panel(panel_label: str, wf: dict, axis_max_ms: float,
                          tick_step: float, baseline_wf: dict | None = None) -> Panel:
    """Render one waterfall panel (BEFORE or AFTER) as a rich Panel."""
    stages        = wf["stages"]
    stage_label_w = max(len(s["name"]) for s in stages) + 2
    term_w        = console.size.width
    bar_inner_w   = max(40, term_w - stage_label_w - 32)

    base_by_name: dict[str, dict] = {}
    if baseline_wf:
        for s in baseline_wf["stages"]:
            base_by_name[s["name"]] = s

    rows: list[Text] = []

    # Tick axis with round labels
    tick_positions: list[tuple[int, str]] = []
    t = 0.0
    while t <= axis_max_ms + 0.01:
        pos = round(t / axis_max_ms * bar_inner_w)
        tick_positions.append((pos, f"{t:.0f}"))
        t += tick_step

    tick_line = list(" " * (bar_inner_w + 6))
    for pos, label in tick_positions:
        for j, ch in enumerate(label):
            if 0 <= pos + j < len(tick_line):
                tick_line[pos + j] = ch
    axis = Text()
    axis.append(" " * stage_label_w)
    axis.append("".join(tick_line).rstrip() + " ms", style=AXIS_STYLE)
    rows.append(axis)

    grid = list("·" * bar_inner_w)
    for pos, _ in tick_positions:
        if 0 <= pos < len(grid):
            grid[pos] = "│"
    grid_row = Text()
    grid_row.append(" " * stage_label_w)
    grid_row.append("".join(grid), style=GRID_STYLE)
    rows.append(grid_row)

    cursor_ms = 0.0
    total_ms  = sum(s["ms"] for s in stages)

    for stage in stages:
        name    = stage["name"].ljust(stage_label_w)
        ms      = stage["ms"]
        base_ms = base_by_name.get(stage["name"], {}).get("ms") if baseline_wf else None

        row = Text()
        row.append(name, style=NEUTRAL_STYLE if ms <= 0 else "")
        if ms <= 0:
            if baseline_wf and base_ms is not None and base_ms > 0.05:
                row.append(" " * bar_inner_w)
                row.append(f"  {'':>7}", style=NEUTRAL_STYLE)
                row.append(_delta_text(0.0, base_ms))
            rows.append(row)
            continue

        start_pos = round(cursor_ms / axis_max_ms * bar_inner_w)
        bar_len   = max(1, round(ms / axis_max_ms * bar_inner_w))
        style     = IPC_STYLE if stage["kind"] == "ipc" else FILTER_STYLE

        row.append(" " * start_pos)
        row.append("█" * bar_len, style=style)
        row.append(" " * max(0, bar_inner_w - start_pos - bar_len))
        row.append(f"  {ms:5.2f} ms", style=NEUTRAL_STYLE)
        if baseline_wf and base_ms is not None:
            row.append(" ")
            row.append(_delta_text(ms, base_ms))
        rows.append(row)
        cursor_ms += ms

    # Total / fps footer
    fps      = 1000.0 / total_ms if total_ms > 0 else float("inf")
    footer   = Text()
    footer.append(" " * stage_label_w)
    footer.append(f"total {total_ms:6.2f} ms · {fps:5.1f} fps max", style=NEUTRAL_STYLE)
    if baseline_wf:
        base_total = sum(s["ms"] for s in baseline_wf["stages"])
        base_fps   = 1000.0 / base_total if base_total > 0 else float("inf")
        footer.append("   ")
        footer.append(_delta_text(total_ms, base_total))
        footer.append("   (")
        footer.append(_delta_text(fps, base_fps, fmt="{:+5.1f} fps", unit_ms=False))
        footer.append(")")
    rows.append(footer)

    title = Text()
    title.append(panel_label, style=TITLE_STYLE)
    title.append("  ")
    title.append(wf["label"], style=NEUTRAL_STYLE)
    border_style = BRAND_TURQUOISE if baseline_wf else BRAND_GREY  # AFTER gets the brand color, BEFORE stays dim
    return Panel(
        Group(*rows),
        title=title,
        title_align="left",
        box=ROUNDED,
        border_style=border_style,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------------

def render(baseline: dict, current: dict) -> None:
    title_text = Text()
    title_text.append("Plainsight ", style=f"bold {BRAND_GRAPE}")
    title_text.append("· ", style=NEUTRAL_STYLE)
    title_text.append("OpenFilter IPC perf", style=f"bold {BRAND_PURPLE}")
    title_text.append(" — ", style=NEUTRAL_STYLE)
    title_text.append("waterfall display", style=BRAND_TURQUOISE)

    header = Panel(
        title_text,
        box=ROUNDED,
        border_style=HEADER_STYLE,
        padding=(0, 1),
        expand=True,
    )
    console.print(header)

    meta = Text()
    meta.append("  baseline:  ")
    meta.append(baseline["git_ref"], style=BRAND_SEAGULL)
    meta.append(f"  ({baseline['git_sha'][:10]})", style=NEUTRAL_STYLE)
    meta.append("\n")
    meta.append("  current:   ")
    meta.append(current["git_ref"],  style=BRAND_SEAGULL)
    meta.append(f"  ({current['git_sha'][:10]})",  style=NEUTRAL_STYLE)
    console.print(meta)
    console.print()

    console.print(build_summary_table(baseline, current))

    if baseline.get("waterfall") and current.get("waterfall"):
        console.print()
        title = Text()
        title.append("Frame waterfall ", style=TITLE_STYLE)
        title.append("— ", style=NEUTRAL_STYLE)
        title.append(current["waterfall"]["label"])
        console.print(title)

        legend = Text()
        legend.append("██", style=IPC_STYLE)
        legend.append(" = IPC hop   ", style=NEUTRAL_STYLE)
        legend.append("██", style=FILTER_STYLE)
        legend.append(" = filter work", style=NEUTRAL_STYLE)
        console.print(legend)
        console.print()

        max_total = max(
            sum(s["ms"] for s in baseline["waterfall"]["stages"]),
            sum(s["ms"] for s in current["waterfall"]["stages"]),
        )
        axis_max, tick_step = _nice_axis(max_total)

        console.print(build_waterfall_panel("BEFORE", baseline["waterfall"], axis_max, tick_step))
        console.print(build_waterfall_panel("AFTER",  current["waterfall"],  axis_max, tick_step,
                                            baseline_wf=baseline["waterfall"]))

    commits = _commits_between(baseline["git_sha"], current["git_sha"])
    if commits:
        console.print()
        tree_label = Text()
        tree_label.append("Wins from ", style=TITLE_STYLE)
        tree_label.append(f"({len(commits)} commit{'s' if len(commits) != 1 else ''} on top of baseline)",
                          style=NEUTRAL_STYLE)
        tree = Tree(tree_label, guide_style=BRAND_GREY)
        for sha, subject in commits:
            line = Text()
            line.append(sha, style=BRAND_SEAGULL)
            line.append("  ")
            line.append(subject)
            tree.add(line)
        console.print(tree)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--baseline-ref", default="origin/main",
                   help="Git ref to measure as the BEFORE state (default: origin/main)")
    p.add_argument("--frames", type=int, default=200,
                   help="Frames per pipeline (default: 200)")
    p.add_argument("--pipeline", default="4k_raw",
                   help="Which pipeline to render in the waterfall panel (default: 4k_raw)")
    p.add_argument("--save-json", metavar="PATH",
                   help="Save the combined {baseline, current} JSON to a file")
    args = p.parse_args()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    with progress:
        task_current  = progress.add_task("[dim]measuring current worktree...", start=True)
        current = measure_current(args.frames, args.pipeline)
        progress.update(task_current, completed=1, total=1)

        task_base = progress.add_task(f"[dim]measuring {args.baseline_ref} in temp worktree...", start=True)
        baseline = measure_at_ref(args.baseline_ref, args.frames, args.pipeline)
        progress.update(task_base, completed=1, total=1)

    if args.save_json:
        Path(args.save_json).write_text(json.dumps({"baseline": baseline, "current": current}, indent=2))
        console.print(f"[dim]Wrote {args.save_json}[/dim]")

    console.print()
    render(baseline, current)
    console.print()


if __name__ == "__main__":
    main()
