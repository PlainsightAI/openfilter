"""Tests for ensuring that openfilter_gpu_usage_percent is always emitted as a float."""

from unittest.mock import MagicMock, patch

from openfilter.filter_runtime.gpu import GPUMetrics
from openfilter.filter_runtime.metrics import Metrics


def test_gpu_usage_percent_is_float():
    """Test that self.gpu_usage_percent is cast to float even when NVML returns an int."""
    # Construct a bare Metrics object to avoid background thread execution
    metrics = object.__new__(Metrics)
    metrics.gpu = {}
    metrics.gpu_accessible = 0
    metrics.gpu_usage_percent = 0.0

    # Simulate NVML returning an integer gpu_util
    mock_metrics = [
        GPUMetrics(index=0, gpu_util=55, mem_used_mb=1024)
    ]

    # Create a mock Event that lets gpu_thread_func run exactly one iteration
    stop_evt = MagicMock()
    stop_evt.wait.side_effect = [False, True]

    # Patch get_gpu_metrics to return our mock integer metric
    with patch("openfilter.filter_runtime.metrics.get_gpu_metrics", return_value=mock_metrics):
        metrics.gpu_thread_func(stop_evt)

    # Assert that the type is strictly float and the value is 55.0
    assert type(metrics.gpu_usage_percent) is float
    assert metrics.gpu_usage_percent == 55.0
