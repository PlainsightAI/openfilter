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


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


pytestmark = [
    pytest.mark.skipif(
        not SCRIPT.exists(), reason="bump-strategy.sh not present in this checkout"
    ),
    pytest.mark.skipif(
        not _module_available("packaging"),
        reason="`packaging` required for bump-strategy.sh's Python heredocs",
    ),
    pytest.mark.skipif(
        not _module_available("tomlkit"),
        reason="`tomlkit` required for bump-strategy.sh's pyproject rewriter",
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


def test_release_md_idempotency_does_not_match_substring_versions(tmp_path: Path) -> None:
    """Regression for the `bullet in text` substring-match bug.

    `0.1.9` would previously match an existing `- Bump openfilter to 0.1.99`
    line in RELEASE.md, silently suppressing the new entry. The fix anchors
    the idempotency check to whole rstripped lines.
    """
    (tmp_path / "RELEASE.md").write_text(
        "# Changelog\n"
        "\n"
        "## v1.0.0\n"
        "\n"
        "### Changed\n"
        "\n"
        "- Bump openfilter to 0.1.99\n"
    )
    _run(tmp_path, of_version="0.1.9")
    rewritten = (tmp_path / "RELEASE.md").read_text()
    # Both lines must be present — the new 0.1.9 entry was added; the
    # existing 0.1.99 entry was not removed or treated as a duplicate.
    assert "- Bump openfilter to 0.1.9\n" in rewritten
    assert "- Bump openfilter to 0.1.99\n" in rewritten


def test_pyproject_preserves_comments_and_layout(tmp_path: Path) -> None:
    """tomlkit-based pyproject rewriter round-trips comments + layout.

    The earlier text-replacement approach also preserved comments by virtue
    of literal-replacing parsed dep strings, but only when the dep string
    appeared verbatim. tomlkit handles arbitrary whitespace inside the
    array (including a trailing comma + comment after the bumped item)
    without disturbing surrounding lines.
    """
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = [\n'
        '    "numpy>=1.20",\n'
        '    "openfilter>=0.1.10,<2",  # ML runtime — bump cascaded from openfilter releases\n'
        ']\n'
        '\n'
        '[project.optional-dependencies]\n'
        'gpu = ["openfilter[gpu]==0.1.27"]\n'
        '\n'
        '[tool.something]\n'
        '# Comment that mentions openfilter==0.1.27 — must NOT be touched\n'
    )

    _run(tmp_path, of_version="1.2.3")

    rewritten = py.read_text()
    # Pin updated, upper bound preserved, inline comment preserved.
    assert '"openfilter>=1.2.3,<2"' in rewritten
    assert "# ML runtime — bump cascaded from openfilter releases" in rewritten
    # Optional-dependencies group bumped.
    assert '"openfilter[gpu]==1.2.3"' in rewritten
    # Comment in [tool.something] untouched (substring-of-comment was the
    # main risk with the literal-text-replace approach).
    assert "openfilter==0.1.27 — must NOT be touched" in rewritten


def test_pyproject_idempotent_rerun_is_noop(tmp_path: Path) -> None:
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = ["openfilter==1.2.3"]\n'
    )
    _run(tmp_path)
    first = py.read_text()
    _run(tmp_path)
    second = py.read_text()
    assert first == second


# ───────────────────────── upper-bound widening ──────────────────────────
# DT-145 augmentation: bump-strategy.sh now widens `<` / `<=` upper bounds
# that would exclude OF_VERSION. Widening rule: for 0.X targets, next minor
# after target; for 1.0+ targets, next major after target. Lower bounds
# (`>=`), exclusions (`!=`), and `>` clauses are still preserved verbatim.


def test_pyproject_widens_upper_bound_for_0_x_target(tmp_path: Path) -> None:
    """Org-canonical case: filter pinning `>=0.1.30,<0.2.0` cascades to 0.2.0."""
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = ["openfilter[all]>=0.1.30,<0.2.0"]\n'
    )
    _run(tmp_path, of_version="0.2.0")
    rewritten = py.read_text()
    # Lower bound bumped to target; upper bound widened to next minor.
    assert '"openfilter[all]>=0.2.0,<0.3.0"' in rewritten


def test_pyproject_widens_upper_bound_for_1_0_target(tmp_path: Path) -> None:
    """1.0+ targets widen to next-major rather than next-minor."""
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = ["openfilter>=0.2.0,<1.0.0"]\n'
    )
    _run(tmp_path, of_version="1.0.0")
    rewritten = py.read_text()
    assert '"openfilter>=1.0.0,<2.0.0"' in rewritten


def test_pyproject_widens_le_upper_bound(tmp_path: Path) -> None:
    """`<=X` upper bound widens when target > X."""
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = ["openfilter>=0.1.30,<=0.1.99"]\n'
    )
    _run(tmp_path, of_version="0.2.0")
    rewritten = py.read_text()
    # Both `<=` and `<` widen to the `<<next>` form.
    assert '"openfilter>=0.2.0,<0.3.0"' in rewritten


def test_pyproject_does_not_widen_when_upper_bound_already_admits_target(
    tmp_path: Path,
) -> None:
    """No widening when `<X` already permits target — bound preserved verbatim."""
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = ["openfilter>=0.1.10,<2"]\n'
    )
    _run(tmp_path, of_version="1.2.3")
    rewritten = py.read_text()
    # Lower bound bumped; upper bound `<2` preserved verbatim (1.2.3 < 2).
    assert '"openfilter>=1.2.3,<2"' in rewritten


def test_pyproject_preserves_inline_comment_when_widening(tmp_path: Path) -> None:
    """tomlkit + the rewriter together preserve the trailing inline comment
    even though both the lower and upper bound are rewritten."""
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = [\n'
        '    "openfilter>=0.1.30,<0.2.0",  # widened by cascade on 0.2.0 release\n'
        ']\n'
    )
    _run(tmp_path, of_version="0.2.0")
    rewritten = py.read_text()
    assert '"openfilter>=0.2.0,<0.3.0"' in rewritten
    assert "# widened by cascade on 0.2.0 release" in rewritten


def test_requirements_widens_upper_bound(tmp_path: Path) -> None:
    """requirements.txt path goes through the same _bump.py helper."""
    req = tmp_path / "requirements.txt"
    req.write_text("openfilter>=0.1.30,<0.2.0\n")
    _run(tmp_path, of_version="0.2.0")
    assert req.read_text() == "openfilter>=0.2.0,<0.3.0\n"


def test_pyproject_widening_is_idempotent(tmp_path: Path) -> None:
    """Re-running bump-strategy on an already-widened pin is a no-op."""
    py = tmp_path / "pyproject.toml"
    py.write_text(
        '[project]\n'
        'name = "filter-x"\n'
        'version = "0.0.1"\n'
        'dependencies = ["openfilter>=0.1.30,<0.2.0"]\n'
    )
    _run(tmp_path, of_version="0.2.0")
    first = py.read_text()
    _run(tmp_path, of_version="0.2.0")
    second = py.read_text()
    assert first == second
    assert '"openfilter>=0.2.0,<0.3.0"' in second
