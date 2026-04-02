"""Tests for OPENFILTER_APPEND_* environment variable support."""

import os

from openfilter.filter_runtime.filter import _apply_append_env_vars


def test_append_ld_library_path_when_not_set(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "/usr/local/nvidia/lib64")
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    _apply_append_env_vars()
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/local/nvidia/lib64"


def test_append_ld_library_path_when_existing(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "/usr/local/nvidia/lib64")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/usr/lib/custom")
    _apply_append_env_vars()
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/lib/custom:/usr/local/nvidia/lib64"


def test_append_path_when_existing(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_PATH", "/usr/local/nvidia/bin")
    monkeypatch.setenv("PATH", "/usr/bin:/usr/local/bin")
    _apply_append_env_vars()
    assert os.environ["PATH"] == "/usr/bin:/usr/local/bin:/usr/local/nvidia/bin"


def test_append_path_when_not_set(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_PATH", "/usr/local/nvidia/bin")
    monkeypatch.delenv("PATH", raising=False)
    _apply_append_env_vars()
    assert os.environ["PATH"] == "/usr/local/nvidia/bin"


def test_no_append_when_not_set(monkeypatch):
    monkeypatch.delenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", raising=False)
    monkeypatch.delenv("OPENFILTER_APPEND_PATH", raising=False)
    original_path = os.environ.get("PATH", "")
    _apply_append_env_vars()
    assert os.environ.get("PATH") == original_path  # unchanged


def test_empty_append_value_ignored(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "")
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    _apply_append_env_vars()
    assert "LD_LIBRARY_PATH" not in os.environ


def test_idempotent_on_reload(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "/usr/local/nvidia/lib64")
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    _apply_append_env_vars()
    _apply_append_env_vars()  # simulate module reload
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/local/nvidia/lib64"


def test_append_multi_value_colon_separated(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "/usr/local/nvidia/lib64:/usr/local/cuda/lib64")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/usr/lib/custom")
    _apply_append_env_vars()
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/lib/custom:/usr/local/nvidia/lib64:/usr/local/cuda/lib64"


def test_multi_value_idempotent_on_reload(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "/usr/local/nvidia/lib64:/usr/local/cuda/lib64")
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    _apply_append_env_vars()
    _apply_append_env_vars()  # simulate module reload
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/local/nvidia/lib64:/usr/local/cuda/lib64"


def test_multi_value_partial_overlap(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "/usr/local/nvidia/lib64:/usr/local/cuda/lib64")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/usr/lib/custom:/usr/local/nvidia/lib64")
    _apply_append_env_vars()
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/lib/custom:/usr/local/nvidia/lib64:/usr/local/cuda/lib64"
