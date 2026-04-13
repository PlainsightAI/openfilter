"""Tests for openfilter.filter_runtime.gpu -- ctypes-based GPU detection and metrics."""

from unittest.mock import patch, MagicMock

import pytest

from openfilter.filter_runtime import gpu
from openfilter.filter_runtime.gpu import (
    detect_gpu,
    get_gpu_metrics,
    GPUInfo,
)


@pytest.fixture(autouse=True)
def _reset_gpu_state():
    """Reset cached library handles between tests."""
    gpu._libcuda = None
    gpu._libnvml = None
    gpu._nvml_initialized = False
    yield
    gpu._libcuda = None
    gpu._libnvml = None
    gpu._nvml_initialized = False


class TestDetectGpu:
    """Tests for detect_gpu() using mocked libcuda."""

    def test_returns_unavailable_when_libcuda_missing(self):
        """No libcuda => not available."""
        with patch.object(gpu, "_load_libcuda", return_value=None):
            info = detect_gpu()
        assert info == GPUInfo(available=False)

    def test_returns_unavailable_when_cuInit_fails(self):
        """cuInit returns non-zero => not available."""
        lib = MagicMock()
        lib.cuInit.return_value = 1
        with patch.object(gpu, "_load_libcuda", return_value=lib):
            info = detect_gpu()
        assert info.available is False

    def test_returns_unavailable_when_device_count_zero(self):
        """cuDeviceGetCount returns 0 devices."""
        lib = MagicMock()
        lib.cuInit.return_value = 0

        def mock_get_count(count_ptr):
            count_ptr._obj.value = 0
            return 0

        lib.cuDeviceGetCount.side_effect = mock_get_count

        with patch.object(gpu, "_load_libcuda", return_value=lib):
            info = detect_gpu()
        assert info.available is False
        assert info.device_count == 0

    def test_returns_gpu_info_on_success(self):
        """Successful detection returns full GPUInfo."""
        lib = MagicMock()
        lib.cuInit.return_value = 0

        def mock_get_count(count_ptr):
            count_ptr._obj.value = 2
            return 0

        lib.cuDeviceGetCount.side_effect = mock_get_count

        def mock_get_name(buf, buflen, dev):
            buf.value = b"Tesla T4"
            return 0

        lib.cuDeviceGetName.side_effect = mock_get_name

        def mock_get_version(ver_ptr):
            ver_ptr._obj.value = 12020  # 12.2
            return 0

        lib.cuDriverGetVersion.side_effect = mock_get_version

        with patch.object(gpu, "_load_libcuda", return_value=lib):
            info = detect_gpu()

        assert info.available is True
        assert info.device_count == 2
        assert info.device_name == "Tesla T4"
        assert info.driver_version == "12.2"

    def test_handles_exception_gracefully(self):
        """If libcuda raises, detect_gpu returns unavailable."""
        lib = MagicMock()
        lib.cuInit.side_effect = OSError("segfault")
        with patch.object(gpu, "_load_libcuda", return_value=lib):
            info = detect_gpu()
        assert info.available is False


class TestGetGpuMetrics:
    """Tests for get_gpu_metrics() using mocked libnvml."""

    def test_returns_none_when_libnvml_missing(self):
        """No libnvml => None."""
        with patch.object(gpu, "_load_libnvml", return_value=None):
            assert get_gpu_metrics() is None

    def test_returns_none_when_nvml_init_fails(self):
        """nvmlInit returns non-zero => None."""
        lib = MagicMock()
        lib.nvmlInit_v2.return_value = 1
        with patch.object(gpu, "_load_libnvml", return_value=lib):
            assert get_gpu_metrics() is None

    def test_returns_metrics_with_ctypes_structs(self):
        """Exercise actual ctypes struct filling via a fake NVML library."""
        import ctypes

        lib = MagicMock()
        lib.nvmlInit_v2.return_value = 0

        def mock_get_count(count_byref):
            # count_byref is the result of ctypes.byref(c_uint(0));
            # ctypes.cast lets us write into the underlying c_uint.
            ptr = ctypes.cast(count_byref, ctypes.POINTER(ctypes.c_uint))
            ptr[0] = 2
            return 0

        lib.nvmlDeviceGetCount_v2.side_effect = mock_get_count
        lib.nvmlDeviceGetHandleByIndex_v2.return_value = 0

        def mock_get_util(handle, util_byref):
            # NvmlUtilization is { c_uint gpu, c_uint memory }
            # Writing through a uint pointer: gpu at offset 0, memory at offset 1
            ptr = ctypes.cast(util_byref, ctypes.POINTER(ctypes.c_uint))
            ptr[0] = 75  # gpu util %
            ptr[1] = 40  # memory util %
            return 0

        lib.nvmlDeviceGetUtilizationRates.side_effect = mock_get_util

        def mock_get_mem(handle, mem_byref):
            # NvmlMemory is { c_ulonglong total, c_ulonglong free, c_ulonglong used }
            ptr = ctypes.cast(mem_byref, ctypes.POINTER(ctypes.c_ulonglong))
            ptr[0] = 8 * 1024 * 1024 * 1024  # total: 8 GiB
            ptr[1] = 6 * 1024 * 1024 * 1024  # free: 6 GiB
            ptr[2] = 2 * 1024 * 1024 * 1024  # used: 2 GiB = 2048 MiB
            return 0

        lib.nvmlDeviceGetMemoryInfo.side_effect = mock_get_mem

        with patch.object(gpu, "_load_libnvml", return_value=lib):
            metrics = get_gpu_metrics()

        assert metrics is not None
        assert len(metrics) == 2
        assert metrics[0].index == 0
        assert metrics[0].gpu_util == 75
        assert metrics[0].mem_used_mb == 2048
        assert metrics[1].index == 1
        assert metrics[1].gpu_util == 75
        assert metrics[1].mem_used_mb == 2048

    def test_nvml_init_called_once_across_polls(self):
        """nvmlInit_v2 is called only on the first call, not on subsequent polls."""
        lib = MagicMock()
        lib.nvmlInit_v2.return_value = 0
        lib.nvmlDeviceGetCount_v2.return_value = 0  # 0 devices, returns None

        with patch.object(gpu, "_load_libnvml", return_value=lib):
            get_gpu_metrics()
            get_gpu_metrics()
            get_gpu_metrics()

        assert lib.nvmlInit_v2.call_count == 1

    def test_handles_exception_gracefully(self):
        """If NVML raises, returns None."""
        lib = MagicMock()
        lib.nvmlInit_v2.side_effect = OSError("library error")
        with patch.object(gpu, "_load_libnvml", return_value=lib):
            assert get_gpu_metrics() is None
