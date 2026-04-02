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


def test_append_path(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_PATH", "/usr/local/nvidia/bin")
    original_path = os.environ.get("PATH", "")
    _apply_append_env_vars()
    assert os.environ["PATH"] == f"{original_path}:/usr/local/nvidia/bin"


def test_no_append_when_not_set(monkeypatch):
    monkeypatch.delenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", raising=False)
    monkeypatch.delenv("OPENFILTER_APPEND_PATH", raising=False)
    original_path = os.environ.get("PATH", "")
    _apply_append_env_vars()
    assert os.environ.get("PATH") == original_path  # unchanged


def test_empty_append_value_ignored(monkeypatch):
    monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", "")
    _apply_append_env_vars()
    # empty string is falsy, should not modify
