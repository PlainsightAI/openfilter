"""Classifier output tests for scripts/cascade/check_constraint.py.

The classifier emits `ok:` / `widen:` / `skip:` / `none*` / `error:` against a
consumer pyproject.toml in CWD. discover.sh reads this and decides whether to
dispatch a bump PR. Anything classified `skip:` is stranded — the cascade
ignores it — so the boundary between `widen:` and `skip:` is the load-bearing
policy: which pin shapes get auto-cascaded vs. left to operators.

Coverage:
- `<X` / `<=X` upper bounds — widenable (historical behavior).
- `~=X` / `==X` pins — widenable. Almost half the filter fleet uses `~=` per
  org convention (Mundim's stylistic preference, no semantic intent claim);
  classifying them as skip strands them out of the cascade.
- `!=X` exclusions and `>X` strict lower bounds — skip (rewriter can't handle).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cascade" / "check_constraint.py"


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


pytestmark = [
    pytest.mark.skipif(
        not SCRIPT.exists(), reason="check_constraint.py not present in this checkout"
    ),
    pytest.mark.skipif(
        not _module_available("packaging"),
        reason="`packaging` required for check_constraint.py",
    ),
    pytest.mark.skipif(
        sys.version_info < (3, 11),
        reason="check_constraint.py uses stdlib `tomllib` (3.11+); cascade runs on GHA Python 3.11+",
    ),
]


def _run(workdir: Path, of_version: str = "0.3.0") -> str:
    env = {**os.environ, "OF_VERSION": of_version}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(workdir),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_pyproject(workdir: Path, openfilter_pin: str) -> None:
    (workdir / "pyproject.toml").write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        f'dependencies = ["{openfilter_pin}"]\n'
    )


def test_lt_upper_bound_excludes_target_is_widen(tmp_path: Path) -> None:
    """`>=0.1.30,<0.2.0` upgrading to 0.3.0 — historical widen path."""
    _write_pyproject(tmp_path, "openfilter>=0.1.30,<0.2.0")
    assert _run(tmp_path, of_version="0.3.0").startswith("widen:")


def test_le_upper_bound_excludes_target_is_widen(tmp_path: Path) -> None:
    """`<=` upper bound that excludes target is also widen."""
    _write_pyproject(tmp_path, "openfilter>=0.1.30,<=0.1.99")
    assert _run(tmp_path, of_version="0.3.0").startswith("widen:")


def test_tilde_pin_excluding_target_is_widen(tmp_path: Path) -> None:
    """`~=0.1.30` upgrading to 0.3.0 — must dispatch, not strand.

    `~=0.1.30` desugars to `>=0.1.30,<0.2.0`, so 0.3.0 is excluded. The rewriter
    has `~=` in _BUMPABLE_OPS and emits `~=0.3.0`. Cascade PRs are reviewed
    before merge; there's no auto-rewrite risk to design against.
    """
    _write_pyproject(tmp_path, "openfilter~=0.1.30")
    assert _run(tmp_path, of_version="0.3.0").startswith("widen:")


def test_exact_pin_excluding_target_is_widen(tmp_path: Path) -> None:
    """`==0.1.18` upgrading to 0.3.0 — must dispatch, not strand."""
    _write_pyproject(tmp_path, "openfilter==0.1.18")
    assert _run(tmp_path, of_version="0.3.0").startswith("widen:")


def test_not_equal_blocking_is_skip(tmp_path: Path) -> None:
    """`!=X` blocking target — rewriter doesn't reason about exclusions."""
    _write_pyproject(tmp_path, "openfilter!=0.3.0,>=0.1.30")
    assert _run(tmp_path, of_version="0.3.0").startswith("skip:")


def test_gt_strict_lower_bound_blocking_is_skip(tmp_path: Path) -> None:
    """`>X` strict lower bound — not in the rewriter's handled op set."""
    _write_pyproject(tmp_path, "openfilter>0.3.0")
    assert _run(tmp_path, of_version="0.3.0").startswith("skip:")


def test_target_already_admitted_is_ok(tmp_path: Path) -> None:
    """`>=X` admitting target — no cascade needed."""
    _write_pyproject(tmp_path, "openfilter>=0.1.21")
    assert _run(tmp_path, of_version="0.3.0").startswith("ok:")


def test_tilde_pin_already_admitting_target_is_ok(tmp_path: Path) -> None:
    """`~=0.3.0` for target 0.3.5 — admitted, no action."""
    _write_pyproject(tmp_path, "openfilter~=0.3.0")
    assert _run(tmp_path, of_version="0.3.5").startswith("ok:")


def test_combined_widenable_and_passing_clauses(tmp_path: Path) -> None:
    """`~=0.1.30,!=0.1.35` for target 0.3.0 — `~=` excludes, `!=` doesn't.

    The `!=0.1.35` clause passes (target isn't 0.1.35). The `~=0.1.30` clause
    is the blocker, and it's rewritable. Should be `widen:`.
    """
    _write_pyproject(tmp_path, "openfilter~=0.1.30,!=0.1.35")
    assert _run(tmp_path, of_version="0.3.0").startswith("widen:")


def test_no_openfilter_dependency(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "filter-x"\nversion = "0.0.1"\ndependencies = ["numpy>=1.20"]\n'
    )
    assert _run(tmp_path).startswith("none")


def test_poetry_format_detected(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "filter-x"\n\n'
        '[tool.poetry.dependencies]\n'
        'openfilter = "^0.1.30"\n'
    )
    assert _run(tmp_path).startswith("none:poetry-format")
