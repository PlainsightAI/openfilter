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


def test_gpu_usage_percent_is_float_when_gpu_idle():
    """An idle GPU reports integer gpu_util==0; without the float() cast this path would emit an int 0 and be rejected by the DOUBLE-locked Cloud Monitoring descriptor, so this test fails on the un-cast code."""
    metrics = _run_one_iteration([GPUMetrics(index=0, gpu_util=0, mem_used_mb=1024)])

    assert type(metrics.gpu_usage_percent) is float
    assert metrics.gpu_usage_percent == 0.0
