"""Tests for ensuring that openfilter_gpu_usage_percent is always emitted as a float."""

from unittest.mock import MagicMock, patch

from openfilter.filter_runtime.gpu import GPUMetrics
from openfilter.filter_runtime.metrics import Metrics


def _run_one_iteration(mock_metrics):
    """Run gpu_thread_func for exactly one loop iteration with mocked NVML metrics."""
    metrics = object.__new__(Metrics)  # bare object, skip __init__'s background threads

    stop_evt = MagicMock()
    stop_evt.wait.side_effect = [False, True]  # run the loop body exactly once

    with patch('openfilter.filter_runtime.metrics.get_gpu_metrics', return_value=mock_metrics):
        metrics.gpu_thread_func(stop_evt)

    return metrics


def test_gpu_usage_percent_is_float():
    """gpu_usage_percent is cast to float even when NVML returns an int gpu_util."""
    metrics = _run_one_iteration([GPUMetrics(index=0, gpu_util=55, mem_used_mb=1024)])

    assert type(metrics.gpu_usage_percent) is float
    assert metrics.gpu_usage_percent == 55.0


def test_gpu_usage_percent_is_float_when_gpu0_absent():
    """The default path (no gpu0 present) still yields a float, not an int."""
    metrics = _run_one_iteration([GPUMetrics(index=1, gpu_util=42, mem_used_mb=1024)])

    assert type(metrics.gpu_usage_percent) is float
    assert metrics.gpu_usage_percent == 0.0
