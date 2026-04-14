#!/usr/bin/env python
"""Tests for Filter._validate_device() -- CUDA/GPU availability validation.

These tests mock openfilter.filter_runtime.filter.detect_gpu (the ctypes-based
GPU detection) and optionally torch.cuda (secondary framework check).
"""

import logging
import unittest
from unittest.mock import patch, MagicMock

from openfilter.filter_runtime import Filter, FilterConfig
from openfilter.filter_runtime.gpu import GPUInfo

logger = logging.getLogger(__name__)


def _gpu_info(**overrides):
    """Return a GPUInfo with sensible defaults.

    Defaults: available, 1 device (Tesla T4), driver 12.2.
    """
    defaults = dict(
        available=True,
        device_count=1,
        device_name='Tesla T4',
        driver_version='12.2',
    )
    defaults.update(overrides)
    return GPUInfo(**defaults)


def _mock_torch_available():
    """Return a MagicMock that acts as torch with cuda.is_available() == True."""
    m = MagicMock()
    m.cuda.is_available.return_value = True
    return m


class TestValidateDevice(unittest.TestCase):
    """Unit tests for Filter._validate_device()."""

    def _make(self, device=None):
        """Create a minimal Filter instance (bypassing full __init__) and a FilterConfig."""
        config = FilterConfig()
        if device is not None:
            config['device'] = device
        f = object.__new__(Filter)
        return f, config

    # -------------------------------------------------------------------------
    # No-op cases -- should not raise and should not require GPU detection
    # -------------------------------------------------------------------------

    def test_noop_devices(self):
        """Devices that need no validation: None, 'cpu', '', -1."""
        noop_cases = [
            (None, "no device config"),
            ('cpu', "device=cpu"),
            ('', "device=empty string"),
            (-1, "device=-1 (negative int means CPU)"),
        ]
        for device, label in noop_cases:
            with self.subTest(label):
                f, config = self._make(device)
                f._validate_device(config)

    # -------------------------------------------------------------------------
    # CUDA available -- happy paths
    # -------------------------------------------------------------------------

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu', return_value=_gpu_info())
    def test_device_cuda_available(self, _mock):
        """device=cuda + CUDA available = passes, logs GPU info with all fields."""
        f, config = self._make('cuda')
        with self.assertLogs('openfilter.filter_runtime.filter', level='INFO') as cm:
            f._validate_device(config)

        log_text = '\n'.join(cm.output)
        self.assertIn('CUDA available', log_text)
        self.assertIn('device_count=1', log_text)
        self.assertIn('Tesla T4', log_text)
        self.assertIn('12.2', log_text)
        self.assertEqual(config['device'], 'cuda')

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu', return_value=_gpu_info())
    def test_device_cuda_colon_0_available(self, _mock):
        """device=cuda:0 + CUDA available + 1 GPU = passes."""
        f, config = self._make('cuda:0')
        f._validate_device(config)

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu',
           return_value=_gpu_info(device_count=4, device_name='A100'))
    def test_device_cuda_colon_3_available_with_4_gpus(self, _mock):
        """device=cuda:3 + 4 GPUs = passes (index in range)."""
        f, config = self._make('cuda:3')
        f._validate_device(config)

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu',
           return_value=_gpu_info(device_count=2, device_name='A100'))
    def test_multiple_gpus_logs_correct_info(self, _mock):
        """Multiple GPUs: log message includes device_count=2 and first device name."""
        f, config = self._make('cuda')
        with self.assertLogs('openfilter.filter_runtime.filter', level='INFO') as cm:
            f._validate_device(config)

        log_text = '\n'.join(cm.output)
        self.assertIn('device_count=2', log_text)
        self.assertIn('A100', log_text)

    # -------------------------------------------------------------------------
    # CUDA unavailable -- error paths
    # -------------------------------------------------------------------------

    def test_cuda_unavailable_raises_for_explicit_devices(self):
        """Explicit CUDA devices raise RuntimeError when CUDA is unavailable."""
        cases = [
            ('cuda', 'FILTER_DEVICE=cuda'),
            ('cuda:0', 'FILTER_DEVICE=cuda:0'),
            ('cuda:1', 'FILTER_DEVICE=cuda:1'),
            (0, 'FILTER_DEVICE=0'),
            (1, 'FILTER_DEVICE=1'),
        ]
        gpu = _gpu_info(available=False, driver_version='unknown')
        for device, expected_substring in cases:
            with self.subTest(device=device):
                f, config = self._make(device)
                with patch('openfilter.filter_runtime.filter.detect_gpu', return_value=gpu):
                    with self.assertRaises(RuntimeError) as ctx:
                        f._validate_device(config)

                msg = str(ctx.exception)
                self.assertIn(expected_substring, msg)
                self.assertIn('CUDA is not available', msg)
                self.assertIn('FILTER_DEVICE=cpu', msg)
                self.assertIn('FILTER_DEVICE=auto', msg)

    # -------------------------------------------------------------------------
    # Auto mode
    # -------------------------------------------------------------------------

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu',
           return_value=_gpu_info(device_count=2, device_name='A100'))
    def test_device_auto_cuda_available(self, _mock):
        """device=auto + CUDA available = sets config to 'cuda', logs info."""
        f, config = self._make('auto')
        with self.assertLogs('openfilter.filter_runtime.filter', level='INFO') as cm:
            f._validate_device(config)

        self.assertEqual(config['device'], 'cuda')
        self.assertTrue(any('CUDA available' in msg for msg in cm.output))

    @patch('openfilter.filter_runtime.filter.detect_gpu',
           return_value=_gpu_info(available=False))
    def test_device_auto_cuda_unavailable_falls_back(self, _mock):
        """device=auto + CUDA unavailable = warns, sets config to 'cpu'."""
        f, config = self._make('auto')
        with self.assertLogs('openfilter.filter_runtime.filter', level='WARNING') as cm:
            f._validate_device(config)

        self.assertEqual(config['device'], 'cpu')
        self.assertTrue(any('Falling back to CPU' in msg for msg in cm.output))

    # -------------------------------------------------------------------------
    # Device index out-of-range validation
    # -------------------------------------------------------------------------

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu',
           return_value=_gpu_info(device_count=1))
    def test_device_cuda_index_out_of_range(self, _mock):
        """device=cuda:2 but only 1 GPU = RuntimeError with index info."""
        f, config = self._make('cuda:2')
        with self.assertRaises(RuntimeError) as ctx:
            f._validate_device(config)

        msg = str(ctx.exception)
        self.assertIn('device index 2', msg)
        self.assertIn('1 CUDA device(s)', msg)

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu',
           return_value=_gpu_info(device_count=2))
    def test_device_integer_index_out_of_range(self, _mock):
        """device=3 (integer) but only 2 GPUs = RuntimeError."""
        f, config = self._make(3)
        with self.assertRaises(RuntimeError) as ctx:
            f._validate_device(config)

        self.assertIn('device index 3', str(ctx.exception))

    # -------------------------------------------------------------------------
    # Edge cases: detect_gpu raises, device_count=0
    # -------------------------------------------------------------------------

    @patch.dict('sys.modules', {'torch': _mock_torch_available()})
    @patch('openfilter.filter_runtime.filter.detect_gpu',
           return_value=_gpu_info(available=True, device_count=0))
    def test_device_count_zero_with_cuda_available(self, _mock):
        """CUDA available but device_count=0 -- logs info with device_count=0."""
        f, config = self._make('cuda')
        with self.assertLogs('openfilter.filter_runtime.filter', level='INFO') as cm:
            f._validate_device(config)

        self.assertTrue(any('device_count=0' in msg for msg in cm.output))

    def test_detect_gpu_raises_exception_cuda_device(self):
        """detect_gpu() raises -- raises RuntimeError for explicit cuda."""
        f, config = self._make('cuda')
        with patch('openfilter.filter_runtime.filter.detect_gpu',
                   side_effect=RuntimeError("CUDA driver error")):
            with self.assertLogs('openfilter.filter_runtime.filter', level='WARNING') as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    f._validate_device(config)

        self.assertIn('CUDA driver error', str(ctx.exception))
        self.assertTrue(any('CUDA driver error' in msg for msg in cm.output))

    def test_detect_gpu_raises_exception_auto_falls_back(self):
        """device=auto + detect_gpu() raises -- falls back to cpu."""
        f, config = self._make('auto')
        with patch('openfilter.filter_runtime.filter.detect_gpu',
                   side_effect=RuntimeError("CUDA init failed")):
            with self.assertLogs('openfilter.filter_runtime.filter', level='WARNING'):
                f._validate_device(config)

        self.assertEqual(config['device'], 'cpu')

    # -------------------------------------------------------------------------
    # Driver present but torch CUDA unavailable (CPU-only wheel, etc.)
    # -------------------------------------------------------------------------

    @patch('openfilter.filter_runtime.filter.detect_gpu', return_value=_gpu_info())
    def test_driver_present_torch_cuda_unavailable_explicit_raises(self, _mock):
        """Driver detected but torch.cuda.is_available()=False raises for explicit cuda."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        f, config = self._make('cuda')
        with patch.dict('sys.modules', {'torch': mock_torch}):
            with self.assertRaises(RuntimeError) as ctx:
                f._validate_device(config)

        msg = str(ctx.exception)
        self.assertIn('torch CUDA is not available', msg)
        self.assertIn('FILTER_DEVICE=cpu', msg)

    @patch('openfilter.filter_runtime.filter.detect_gpu', return_value=_gpu_info())
    def test_driver_present_torch_cuda_unavailable_auto_falls_back(self, _mock):
        """Driver detected but torch.cuda.is_available()=False falls back for auto."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        f, config = self._make('auto')
        with patch.dict('sys.modules', {'torch': mock_torch}):
            with self.assertLogs('openfilter.filter_runtime.filter', level='WARNING') as cm:
                f._validate_device(config)

        self.assertEqual(config['device'], 'cpu')
        self.assertTrue(any('torch CUDA is not available' in msg for msg in cm.output))

    @patch('openfilter.filter_runtime.filter.detect_gpu', return_value=_gpu_info())
    def test_driver_present_torch_not_installed_passes(self, _mock):
        """Driver detected, torch not importable -- trusts driver detection."""
        f, config = self._make('cuda')
        with patch.dict('sys.modules', {'torch': None}):
            with self.assertLogs('openfilter.filter_runtime.filter', level='INFO'):
                f._validate_device(config)

        self.assertEqual(config['device'], 'cuda')


if __name__ == '__main__':
    unittest.main()
