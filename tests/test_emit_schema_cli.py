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
    from typing import ClassVar, Literal
    from pydantic import Field
    from openfilter.filter_runtime.config import FilterConfigBase, Managed
    from openfilter.filter_runtime.formats import VideoSource
    from openfilter.filter_runtime.output import FilterOutputSchema
    from openfilter.filter_runtime.shapes import Detection

    class SynthFilterConfig(FilterConfigBase):
        sources: list[VideoSource] = Managed([], resolve="orchestrator-generated")
        confidence_threshold: float = Field(default=0.5, ge=0, le=1)
        mode: Literal["fast", "accurate"] = "fast"

    class SynthFilterOutput(FilterOutputSchema):
        __schema_id__: ClassVar[str] = "https://schemas.plainsight.ai/filters/synth/v1"
        __frame_data_key__: ClassVar[str] = "detections"

        items: list[Detection]

    # A nested helper FilterOutputSchema co-located with the top-level
    # output. CLI auto-detect must prefer the anchored top-level class
    # (non-None __frame_data_key__) over this helper.
    class _SynthHelperShape(FilterOutputSchema):
        __schema_id__: ClassVar[str] = "https://schemas.plainsight.ai/filters/synth/helper/v1"

        helper_field: int
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


# ---------- --kind output (FILTER-444) ----------


def test_emit_schema_cli_output_kind_explicit_class(
    synth_filter_module: str,
) -> None:
    result = _run_cli(
        [
            "emit-schema",
            "--kind",
            "output",
            f"{synth_filter_module}:SynthFilterOutput",
        ]
    )
    assert result.returncode == 0, result.stderr
    schema = json.loads(result.stdout)
    assert schema["$id"] == "https://schemas.plainsight.ai/filters/synth/v1"
    assert schema["x-openfilter-frame-data-key"] == "detections"
    assert "Detection" in schema.get("$defs", {})


def test_emit_schema_cli_output_kind_auto_picks_anchored_class(
    synth_filter_module: str,
) -> None:
    """With --kind output and no explicit class, auto-detect prefers the
    FilterOutputSchema subclass with a non-None __frame_data_key__ (the
    filter-author top-level output) over co-located helper subclasses
    (which leave __frame_data_key__ unset)."""
    result = _run_cli(
        ["emit-schema", "--kind", "output", synth_filter_module]
    )
    assert result.returncode == 0, result.stderr
    schema = json.loads(result.stdout)
    assert schema["title"] == "SynthFilterOutput"


def test_emit_schema_cli_output_kind_rejects_config_class(
    synth_filter_module: str,
) -> None:
    result = _run_cli(
        [
            "emit-schema",
            "--kind",
            "output",
            f"{synth_filter_module}:SynthFilterConfig",
        ]
    )
    assert result.returncode != 0
    assert "FilterOutputSchema" in (result.stderr + result.stdout)


def test_emit_schema_cli_config_kind_rejects_output_class(
    synth_filter_module: str,
) -> None:
    result = _run_cli(
        [
            "emit-schema",
            f"{synth_filter_module}:SynthFilterOutput",
        ]
    )
    assert result.returncode != 0
    assert "FilterConfigBase" in (result.stderr + result.stdout)


def test_emit_schema_cli_include_managed_rejected_with_output_kind(
    synth_filter_module: str,
) -> None:
    result = _run_cli(
        [
            "emit-schema",
            "--kind",
            "output",
            "--include-managed",
            f"{synth_filter_module}:SynthFilterOutput",
        ]
    )
    assert result.returncode != 0
    assert "include-managed" in (result.stderr + result.stdout)


def test_emit_schema_cli_output_kind_fails_when_multiple_anchored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-detect only resolves ambiguity when exactly one candidate has a
    non-None __frame_data_key__. Two anchored candidates remain ambiguous."""
    src = textwrap.dedent(
        """
        from typing import ClassVar
        from openfilter.filter_runtime.output import FilterOutputSchema

        class FirstOutput(FilterOutputSchema):
            __schema_id__: ClassVar[str] = "https://example.com/first/v1"
            __frame_data_key__: ClassVar[str] = "first"
            payload: int

        class SecondOutput(FilterOutputSchema):
            __schema_id__: ClassVar[str] = "https://example.com/second/v1"
            __frame_data_key__: ClassVar[str] = "second"
            payload: int
        """
    )
    mod_path = tmp_path / "_synth_two_anchored.py"
    mod_path.write_text(src)
    monkeypatch.setenv(
        "PYTHONPATH",
        str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    result = _run_cli(["emit-schema", "--kind", "output", mod_path.stem])
    assert result.returncode != 0
    assert "multiple" in (result.stderr + result.stdout).lower()
