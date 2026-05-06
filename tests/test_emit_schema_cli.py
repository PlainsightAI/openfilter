"""Tests for the `openfilter emit-schema` CLI (Goldenrod.2 FC-3)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from openfilter.filter_runtime.config import MANAGED_KEY


_SYNTH_FILTER = textwrap.dedent(
    """
    from typing import Literal
    from pydantic import Field
    from openfilter.filter_runtime.config import FilterConfigBase, Managed
    from openfilter.filter_runtime.formats import VideoSource

    class SynthFilterConfig(FilterConfigBase):
        sources: list[VideoSource] = Managed([], resolve="orchestrator-generated")
        confidence_threshold: float = Field(default=0.5, ge=0, le=1)
        mode: Literal["fast", "accurate"] = "fast"
    """
)


@pytest.fixture
def synth_filter_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    mod_path = tmp_path / "_synth_emit_schema_filter.py"
    mod_path.write_text(_SYNTH_FILTER)
    monkeypatch.syspath_prepend(str(tmp_path))
    # Subprocess invocations also need the path
    monkeypatch.setenv(
        "PYTHONPATH",
        str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    return mod_path.stem


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "openfilter.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_emit_schema_cli_stdout(synth_filter_module: str) -> None:
    result = _run_cli(["emit-schema", f"{synth_filter_module}:SynthFilterConfig"])
    assert result.returncode == 0, result.stderr
    schema = json.loads(result.stdout)
    assert schema["title"] == "SynthFilterConfig"
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    props = schema["properties"]
    assert "sources" not in props  # managed by default
    assert "confidence_threshold" in props
    assert props["mode"]["enum"] == ["fast", "accurate"]


def test_emit_schema_cli_writes_file(
    synth_filter_module: str, tmp_path: Path
) -> None:
    out = tmp_path / "schema.json"
    result = _run_cli(
        [
            "emit-schema",
            f"{synth_filter_module}:SynthFilterConfig",
            "-o",
            str(out),
        ]
    )
    assert result.returncode == 0, result.stderr
    schema = json.loads(out.read_text())
    assert "confidence_threshold" in schema["properties"]


def test_emit_schema_cli_include_managed_surfaces_overrides(
    synth_filter_module: str,
) -> None:
    result = _run_cli(
        [
            "emit-schema",
            f"{synth_filter_module}:SynthFilterConfig",
            "--include-managed",
        ]
    )
    assert result.returncode == 0, result.stderr
    schema = json.loads(result.stdout)
    sources = schema["properties"]["sources"]
    assert sources[MANAGED_KEY] is True
    assert sources["items"]["format"] == "video-source"


def test_emit_schema_cli_auto_picks_single_class(
    synth_filter_module: str,
) -> None:
    result = _run_cli(["emit-schema", synth_filter_module])
    assert result.returncode == 0, result.stderr
    schema = json.loads(result.stdout)
    assert schema["title"] == "SynthFilterConfig"


def test_emit_schema_cli_fails_on_unknown_class(
    synth_filter_module: str,
) -> None:
    result = _run_cli(
        ["emit-schema", f"{synth_filter_module}:NotARealClass"]
    )
    assert result.returncode != 0
    assert "NotARealClass" in result.stderr or "NotARealClass" in result.stdout
