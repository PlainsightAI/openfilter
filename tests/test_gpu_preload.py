"""Tests for GPU library preloading via ctypes.CDLL."""

import ctypes
from unittest.mock import patch

import pytest

from openfilter.filter_runtime.filter import _preload_gpu_libs, _preloaded_gpu_libs


@pytest.fixture(autouse=True)
def _clear_preload_state():
    """Reset the preloaded set between tests so each test starts clean."""
    _preloaded_gpu_libs.clear()
    yield
    _preloaded_gpu_libs.clear()


class TestPreloadGpuLibs:
    """Tests for _preload_gpu_libs()."""

    def test_loads_libcuda_when_exists(self, monkeypatch, tmp_path):
        """When OPENFILTER_APPEND_LD_LIBRARY_PATH is set and libcuda.so.1 exists, it is loaded."""
        lib_dir = tmp_path / "nvidia"
        lib_dir.mkdir()
        (lib_dir / "libcuda.so.1").touch()

        monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", str(lib_dir))

        with patch("ctypes.CDLL") as mock_cdll:
            _preload_gpu_libs()
            mock_cdll.assert_any_call(
                str(lib_dir / "libcuda.so.1"), mode=ctypes.RTLD_GLOBAL
            )

    def test_loads_libnvidia_ml_when_exists(self, monkeypatch, tmp_path):
        """When libnvidia-ml.so.1 exists, it is also loaded."""
        lib_dir = tmp_path / "nvidia"
        lib_dir.mkdir()
        (lib_dir / "libnvidia-ml.so.1").touch()

        monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", str(lib_dir))

        with patch("ctypes.CDLL") as mock_cdll:
            _preload_gpu_libs()
            mock_cdll.assert_any_call(
                str(lib_dir / "libnvidia-ml.so.1"), mode=ctypes.RTLD_GLOBAL
            )

    def test_skips_when_no_env_var(self, monkeypatch):
        """When OPENFILTER_APPEND_LD_LIBRARY_PATH is not set, nothing is loaded."""
        monkeypatch.delenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", raising=False)

        with patch("ctypes.CDLL") as mock_cdll:
            _preload_gpu_libs()
            mock_cdll.assert_not_called()

    def test_skips_when_libcuda_not_found(self, monkeypatch, tmp_path):
        """When the path exists but contains no GPU libs, nothing is loaded."""
        lib_dir = tmp_path / "empty"
        lib_dir.mkdir()

        monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", str(lib_dir))

        with patch("ctypes.CDLL") as mock_cdll:
            _preload_gpu_libs()
            mock_cdll.assert_not_called()

    def test_handles_multiple_paths(self, monkeypatch, tmp_path):
        """Colon-separated paths are all searched."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "libcuda.so.1").touch()
        (dir2 / "libnvidia-ml.so.1").touch()

        monkeypatch.setenv(
            "OPENFILTER_APPEND_LD_LIBRARY_PATH", f"{dir1}:{dir2}"
        )

        with patch("ctypes.CDLL") as mock_cdll:
            _preload_gpu_libs()
            mock_cdll.assert_any_call(
                str(dir1 / "libcuda.so.1"), mode=ctypes.RTLD_GLOBAL
            )
            mock_cdll.assert_any_call(
                str(dir2 / "libnvidia-ml.so.1"), mode=ctypes.RTLD_GLOBAL
            )

    def test_handles_load_failure(self, monkeypatch, tmp_path):
        """OSError from ctypes.CDLL is caught, not raised."""
        lib_dir = tmp_path / "nvidia"
        lib_dir.mkdir()
        (lib_dir / "libcuda.so.1").touch()

        monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", str(lib_dir))

        with patch("ctypes.CDLL", side_effect=OSError("cannot load")):
            # Should not raise
            _preload_gpu_libs()

    def test_idempotent(self, monkeypatch, tmp_path):
        """Calling twice doesn't double-load the same library."""
        lib_dir = tmp_path / "nvidia"
        lib_dir.mkdir()
        (lib_dir / "libcuda.so.1").touch()

        monkeypatch.setenv("OPENFILTER_APPEND_LD_LIBRARY_PATH", str(lib_dir))

        with patch("ctypes.CDLL") as mock_cdll:
            _preload_gpu_libs()
            _preload_gpu_libs()
            # libcuda.so.1 should only be loaded once
            libcuda_calls = [
                c for c in mock_cdll.call_args_list
                if str(lib_dir / "libcuda.so.1") in str(c)
            ]
            assert len(libcuda_calls) == 1


class TestPreloadRunsBeforeApplyEnvVars:
    """Verify call order in filter.py module-level code."""

    def test_preload_runs_before_apply_env_vars(self):
        """_preload_gpu_libs() is called before _apply_append_env_vars() at module level."""
        import re
        import inspect
        from openfilter.filter_runtime import filter as filter_module

        source = inspect.getsource(filter_module)
        # Match standalone calls (not function definitions starting with 'def ')
        preload_match = re.search(r"^(?!.*\bdef\b).*_preload_gpu_libs\(\)", source, re.MULTILINE)
        apply_match = re.search(r"^(?!.*\bdef\b).*_apply_append_env_vars\(\)", source, re.MULTILINE)
        assert preload_match is not None, "_preload_gpu_libs() module-level call not found"
        assert apply_match is not None, "_apply_append_env_vars() module-level call not found"
        assert preload_match.start() < apply_match.start(), (
            "_preload_gpu_libs() must be called before _apply_append_env_vars()"
        )
