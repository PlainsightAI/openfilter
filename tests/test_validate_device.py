#!/usr/bin/env python
"""Tests for Filter._validate_device() -- CUDA/GPU availability validation."""

import logging
import unittest
from unittest.mock import patch, MagicMock

from openfilter.filter_runtime import Filter, FilterConfig

logger = logging.getLogger(__name__)


def _mock_torch(**overrides):
    """Return a MagicMock pre-configured as a torch module.

    Defaults: CUDA available, 1 device (Tesla T4), CUDA 12.2.
    Pass keyword overrides to change any default.
    """
    defaults = dict(
        is_available=True,
        device_count=1,
        device_name='Tesla T4',
        cuda_version='12.2',
        cuda_built=True,
    )
    defaults.update(overrides)

    m = MagicMock()
    m.cuda.is_available.return_value = defaults['is_available']
    m.cuda.device_count.return_value = defaults['device_count']
    m.cuda.get_device_name.return_value = defaults['device_name']
    m.version.cuda = defaults['cuda_version']
    m.backends.cuda.is_built.return_value = defaults['cuda_built']
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
    # No-op cases -- should not raise and should not require torch
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

    @patch.dict('sys.modules', {'torch': _mock_torch()})
    def test_device_cuda_available(self):
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

    @patch.dict('sys.modules', {'torch': _mock_torch()})
    def test_device_cuda_colon_0_available(self):
        """device=cuda:0 + CUDA available + 1 GPU = passes."""
        f, config = self._make('cuda:0')
        f._validate_device(config)

    @patch.dict('sys.modules', {'torch': _mock_torch(device_count=4, device_name='A100')})
    def test_device_cuda_colon_3_available_with_4_gpus(self):
        """device=cuda:3 + 4 GPUs = passes (index in range)."""
        f, config = self._make('cuda:3')
        f._validate_device(config)

    @patch.dict('sys.modules', {'torch': _mock_torch(device_count=2, device_name='A100')})
    def test_multiple_gpus_logs_correct_info(self):
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
        mock = _mock_torch(is_available=False, cuda_version='12.8')
        for device, expected_substring in cases:
            with self.subTest(device=device):
                f, config = self._make(device)
                with patch.dict('sys.modules', {'torch': mock}):
                    with self.assertRaises(RuntimeError) as ctx:
                        f._validate_device(config)

                msg = str(ctx.exception)
                self.assertIn(expected_substring, msg)
                self.assertIn('CUDA is not available', msg)
                self.assertIn('12.8', msg)
                self.assertIn('FILTER_DEVICE=cpu', msg)
                self.assertIn('FILTER_DEVICE=auto', msg)

    # -------------------------------------------------------------------------
    # Auto mode
    # -------------------------------------------------------------------------

    @patch.dict('sys.modules', {'torch': _mock_torch(device_count=2, device_name='A100')})
    def test_device_auto_cuda_available(self):
        """device=auto + CUDA available = sets config to 'cuda', logs info."""
        f, config = self._make('auto')
        with self.assertLogs('openfilter.filter_runtime.filter', level='INFO') as cm:
            f._validate_device(config)

        self.assertEqual(config['device'], 'cuda')
        self.assertTrue(any('CUDA available' in msg for msg in cm.output))

    @patch.dict('sys.modules', {'torch': _mock_torch(is_available=False, cuda_built=False)})
    def test_device_auto_cuda_unavailable_falls_back(self):
        """device=auto + CUDA unavailable = warns, sets config to 'cpu'."""
        f, config = self._make('auto')
        with self.assertLogs('openfilter.filter_runtime.filter', level='WARNING') as cm:
            f._validate_device(config)

        self.assertEqual(config['device'], 'cpu')
        self.assertTrue(any('Falling back to CPU' in msg for msg in cm.output))

    # -------------------------------------------------------------------------
    # Device index out-of-range validation
    # -------------------------------------------------------------------------

    @patch.dict('sys.modules', {'torch': _mock_torch(device_count=1)})
    def test_device_cuda_index_out_of_range(self):
        """device=cuda:2 but only 1 GPU = RuntimeError with index info."""
        f, config = self._make('cuda:2')
        with self.assertRaises(RuntimeError) as ctx:
            f._validate_device(config)

        msg = str(ctx.exception)
        self.assertIn('device index 2', msg)
        self.assertIn('1 CUDA device(s)', msg)

    @patch.dict('sys.modules', {'torch': _mock_torch(device_count=2)})
    def test_device_integer_index_out_of_range(self):
        """device=3 (integer) but only 2 GPUs = RuntimeError."""
        f, config = self._make(3)
        with self.assertRaises(RuntimeError) as ctx:
            f._validate_device(config)

        self.assertIn('device index 3', str(ctx.exception))

    # -------------------------------------------------------------------------
    # Edge cases: device_count=0, is_available raises, torch missing
    # -------------------------------------------------------------------------

    @patch.dict('sys.modules', {'torch': _mock_torch(device_count=0)})
    def test_device_count_zero_with_cuda_available(self):
        """CUDA available but device_count=0 -- logs 'unknown', never calls get_device_name."""
        import sys
        mock_torch = sys.modules['torch']

        f, config = self._make('cuda')
        with self.assertLogs('openfilter.filter_runtime.filter', level='INFO') as cm:
            f._validate_device(config)

        mock_torch.cuda.get_device_name.assert_not_called()
        self.assertTrue(any('unknown' in msg for msg in cm.output))

    def test_is_available_raises_exception_cuda_device(self):
        """torch.cuda.is_available() raises -- logs warning, does not crash."""
        mock_torch = _mock_torch()
        mock_torch.cuda.is_available.side_effect = RuntimeError("CUDA driver error")

        f, config = self._make('cuda')
        with patch.dict('sys.modules', {'torch': mock_torch}):
            with self.assertLogs('openfilter.filter_runtime.filter', level='WARNING') as cm:
                f._validate_device(config)

        self.assertTrue(any('CUDA driver error' in msg for msg in cm.output))

    def test_is_available_raises_exception_auto_falls_back(self):
        """device=auto + is_available() raises -- falls back to cpu."""
        mock_torch = _mock_torch()
        mock_torch.cuda.is_available.side_effect = RuntimeError("CUDA init failed")

        f, config = self._make('auto')
        with patch.dict('sys.modules', {'torch': mock_torch}):
            with self.assertLogs('openfilter.filter_runtime.filter', level='WARNING') as cm:
                f._validate_device(config)

        self.assertEqual(config['device'], 'cpu')

    def test_torch_not_installed(self):
        """device=cuda but torch not importable -- no error (non-GPU filter)."""
        f, config = self._make('cuda')
        with patch.dict('sys.modules', {'torch': None}):
            f._validate_device(config)


if __name__ == '__main__':
    unittest.main()
