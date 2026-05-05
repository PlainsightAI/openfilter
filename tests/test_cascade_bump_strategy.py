"""Smoke + regression tests for scripts/cascade/bump-strategy.sh.

The bump-strategy.sh script is a thin shell wrapper around three Python
heredocs (pyproject rewrite, requirements rewrite, RELEASE.md append). We
can't unit-test the heredocs in isolation without duplicating them, but we
can drive the script as a subprocess against synthetic working directories
and assert on the resulting file contents — which is the contract the
cascade workflow actually depends on.

These tests guard the trailing-whitespace fix (PR #85 round-2 feedback)
plus a couple of adjacent edge cases that were close enough that we may as
well lock them down at the same time.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cascade" / "bump-strategy.sh"


def _packaging_available() -> bool:
    try:
        import packaging  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = [
    pytest.mark.skipif(
        not SCRIPT.exists(), reason="bump-strategy.sh not present in this checkout"
    ),
    pytest.mark.skipif(
        not _packaging_available(),
        reason="packaging module required for bump-strategy.sh's Python heredocs",
    ),
    pytest.mark.skipif(
        sys.version_info < (3, 11),
        reason="bump-strategy.sh's tomllib usage requires Python >= 3.11",
    ),
]


def _run(workdir: Path, of_version: str = "1.2.3") -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "OF_VERSION": of_version,
        "PYTHON": sys.executable,
        # Ensure the script's `python3` resolves to the same interpreter
        # pytest is running under (so `packaging` is importable).
        "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(workdir),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_requirements_preserves_inner_trailing_whitespace_with_comment(tmp_path: Path) -> None:
    """Regression for the `trailing_ws_len = ... - leading_ws_len` bug.

    With the previous formula, a line that had BOTH leading whitespace
    (e.g. nested under a `# section` heading via indentation) AND inner
    trailing whitespace before the `# comment` would lose the inner
    trailing whitespace on rewrite. After the fix the count is computed
    independently of leading whitespace and is preserved verbatim.
    """
    req = tmp_path / "requirements.txt"
    req.write_text("  openfilter>=1.0  # legacy comment\n")

    _run(tmp_path)

    rewritten = req.read_text()
    # Leading two spaces preserved.
    assert rewritten.startswith("  ")
    # Version bumped to 1.2.3.
    assert ">=1.2.3" in rewritten
    # Two spaces between body and comment preserved.
    assert "1.2.3  # legacy comment" in rewritten


def test_requirements_no_indent_no_comment_roundtrips(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("openfilter>=1.0\n")
    _run(tmp_path)
    assert req.read_text() == "openfilter>=1.2.3\n"


def test_requirements_indent_only_no_trailing_ws(tmp_path: Path) -> None:
    """Leading whitespace alone (no inner trailing) must round-trip cleanly.

    This is the path the old buggy formulation accidentally got right
    (because trailing_ws_len was already 0). Lock it in.
    """
    req = tmp_path / "requirements.txt"
    req.write_text("    openfilter>=1.0\n")
    _run(tmp_path)
    assert req.read_text() == "    openfilter>=1.2.3\n"


def test_requirements_comment_only_no_indent(tmp_path: Path) -> None:
    """Comment with no inner trailing whitespace must round-trip cleanly."""
    req = tmp_path / "requirements.txt"
    req.write_text("openfilter>=1.0 # spaced once\n")
    _run(tmp_path)
    rewritten = req.read_text()
    assert rewritten == "openfilter>=1.2.3 # spaced once\n"


def test_requirements_trailing_only_no_comment(tmp_path: Path) -> None:
    """Trailing whitespace with no comment after must round-trip verbatim.

    This is the case where `trailing_ws_len = len(body) - len(body.rstrip())`
    is doing all the work alone (no comment to anchor against). The old
    `len(line) - len(line.rstrip()) - leading_ws_len` formulation would
    silently truncate this; the new formula preserves it.
    """
    req = tmp_path / "requirements.txt"
    req.write_text("openfilter>=1.0  \n")
    _run(tmp_path)
    rewritten = req.read_text()
    assert rewritten == "openfilter>=1.2.3  \n"


def test_requirements_non_openfilter_lines_untouched(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    original = "  numpy>=1.20\n-r other.txt\n  openfilter>=1.0  # bump me\n"
    req.write_text(original)
    _run(tmp_path)
    rewritten = req.read_text()
    # numpy and -r lines untouched.
    assert "  numpy>=1.20\n" in rewritten
    assert "-r other.txt\n" in rewritten
    # openfilter bumped with whitespace preserved.
    assert "  openfilter>=1.2.3  # bump me\n" in rewritten
