#!/usr/bin/env python
"""Tests for FILTER_* environment variable support in core I/O filters.

Verifies that core filters accept the standardized FILTER_* prefix as an alternative
to filter-specific prefixes (VIDEO_IN_*, VIDEO_OUT_*, IMAGE_IN_*, IMAGE_OUT_*),
with the filter-specific prefix taking precedence for backward compatibility.

Uses unittest.mock.patch.dict + importlib.reload to test module-level env var loading
in-process. Each test saves/restores module-level constants to avoid class identity
issues from reload affecting other test files.
"""

import importlib
import os
import unittest
from unittest.mock import patch

# All env var names that could affect filter behavior — cleared before each test
ALL_FILTER_ENV_VARS = [
    'FILTER_BGR', 'FILTER_SYNC', 'FILTER_LOOP', 'FILTER_MAXFPS', 'FILTER_MAXSIZE',
    'FILTER_RESIZE', 'FILTER_FPS', 'FILTER_SEGTIME', 'FILTER_PARAMS',
    'FILTER_POLL_INTERVAL', 'FILTER_RECURSIVE', 'FILTER_QUALITY', 'FILTER_COMPRESSION',
    'VIDEO_IN_BGR', 'VIDEO_IN_SYNC', 'VIDEO_IN_LOOP', 'VIDEO_IN_MAXFPS',
    'VIDEO_IN_MAXSIZE', 'VIDEO_IN_RESIZE',
    'VIDEO_OUT_BGR', 'VIDEO_OUT_FPS', 'VIDEO_OUT_SEGTIME', 'VIDEO_OUT_PARAMS',
    'IMAGE_IN_POLL_INTERVAL', 'IMAGE_IN_LOOP', 'IMAGE_IN_RECURSIVE', 'IMAGE_IN_MAXFPS',
    'IMAGE_OUT_BGR', 'IMAGE_OUT_QUALITY', 'IMAGE_OUT_COMPRESSION',
]

# Module-level constant names per filter module
_FILTER_CONSTANTS = {
    'openfilter.filter_runtime.filters.video_in': [
        'VIDEO_IN_BGR', 'VIDEO_IN_SYNC', 'VIDEO_IN_LOOP', 'VIDEO_IN_MAXFPS',
        'VIDEO_IN_MAXSIZE', 'VIDEO_IN_RESIZE',
    ],
    'openfilter.filter_runtime.filters.video_out': [
        'VIDEO_OUT_BGR', 'VIDEO_OUT_FPS', 'VIDEO_OUT_SEGTIME', 'VIDEO_OUT_PARAMS',
    ],
    'openfilter.filter_runtime.filters.image_in': [
        'IMAGE_IN_POLL_INTERVAL', 'IMAGE_IN_LOOP', 'IMAGE_IN_RECURSIVE', 'IMAGE_IN_MAXFPS',
    ],
    'openfilter.filter_runtime.filters.image_out': [
        'IMAGE_OUT_BGR', 'IMAGE_OUT_QUALITY', 'IMAGE_OUT_COMPRESSION',
    ],
}


def _eval_with_env(mod_path, var_name, env_overrides):
    """Reload module with patched env, read the constant, then restore all original attributes.

    Saves and restores the entire module __dict__ to preserve class identity for
    isinstance checks in other test files that import config classes.
    """
    mod = importlib.import_module(mod_path)

    # Save entire module dict (shallow copy — class objects are preserved by reference)
    original_dict = dict(mod.__dict__)

    try:
        with patch.dict(os.environ, env_overrides, clear=False):
            # Remove all filter env vars not in overrides
            for k in ALL_FILTER_ENV_VARS:
                if k not in env_overrides:
                    os.environ.pop(k, None)
            importlib.reload(mod)
            return getattr(mod, var_name)
    finally:
        # Restore all original module attributes (preserves class identity)
        mod.__dict__.clear()
        mod.__dict__.update(original_dict)


# ---------------------------------------------------------------------------
#  VideoIn env var tests
# ---------------------------------------------------------------------------

class TestVideoInEnvVars(unittest.TestCase):
    """Test VIDEO_IN_* env vars with FILTER_* fallback."""

    MOD = 'openfilter.filter_runtime.filters.video_in'

    def _get(self, var, env):
        return _eval_with_env(self.MOD, var, env)

    # --- FILTER_* as primary configuration (platform convention) ---

    def test_filter_bgr_true(self):
        self.assertTrue(self._get('VIDEO_IN_BGR', {'FILTER_BGR': 'true'}))

    def test_filter_bgr_false(self):
        self.assertFalse(self._get('VIDEO_IN_BGR', {'FILTER_BGR': 'false'}))

    def test_filter_sync_true(self):
        self.assertTrue(self._get('VIDEO_IN_SYNC', {'FILTER_SYNC': 'true'}))

    def test_filter_sync_false(self):
        self.assertFalse(self._get('VIDEO_IN_SYNC', {'FILTER_SYNC': 'false'}))

    def test_filter_loop_true(self):
        self.assertTrue(self._get('VIDEO_IN_LOOP', {'FILTER_LOOP': 'true'}))

    def test_filter_loop_false(self):
        self.assertFalse(self._get('VIDEO_IN_LOOP', {'FILTER_LOOP': 'false'}))

    def test_filter_loop_int(self):
        self.assertEqual(self._get('VIDEO_IN_LOOP', {'FILTER_LOOP': '3'}), 3)

    def test_filter_loop_zero(self):
        """Loop=0 means infinite loop (same as True)."""
        self.assertEqual(self._get('VIDEO_IN_LOOP', {'FILTER_LOOP': '0'}), 0)

    def test_filter_maxfps(self):
        self.assertEqual(self._get('VIDEO_IN_MAXFPS', {'FILTER_MAXFPS': '15'}), 15.0)

    def test_filter_maxfps_float(self):
        self.assertEqual(self._get('VIDEO_IN_MAXFPS', {'FILTER_MAXFPS': '0.5'}), 0.5)

    def test_filter_maxsize(self):
        self.assertEqual(self._get('VIDEO_IN_MAXSIZE', {'FILTER_MAXSIZE': '1920x1080'}), '1920x1080')

    def test_filter_resize(self):
        self.assertEqual(self._get('VIDEO_IN_RESIZE', {'FILTER_RESIZE': '640x480'}), '640x480')

    def test_filter_resize_with_interpolation(self):
        self.assertEqual(self._get('VIDEO_IN_RESIZE', {'FILTER_RESIZE': '640x480lin'}), '640x480lin')

    # --- Legacy VIDEO_IN_* still works ---

    def test_legacy_bgr(self):
        self.assertFalse(self._get('VIDEO_IN_BGR', {'VIDEO_IN_BGR': 'false'}))

    def test_legacy_sync(self):
        self.assertTrue(self._get('VIDEO_IN_SYNC', {'VIDEO_IN_SYNC': 'true'}))

    def test_legacy_loop(self):
        self.assertEqual(self._get('VIDEO_IN_LOOP', {'VIDEO_IN_LOOP': '5'}), 5)

    def test_legacy_maxfps(self):
        self.assertEqual(self._get('VIDEO_IN_MAXFPS', {'VIDEO_IN_MAXFPS': '24'}), 24.0)

    def test_legacy_maxsize(self):
        self.assertEqual(self._get('VIDEO_IN_MAXSIZE', {'VIDEO_IN_MAXSIZE': '800x600'}), '800x600')

    def test_legacy_resize(self):
        self.assertEqual(self._get('VIDEO_IN_RESIZE', {'VIDEO_IN_RESIZE': '320x240'}), '320x240')

    # --- Legacy takes precedence over FILTER_* ---

    def test_precedence_bgr(self):
        self.assertTrue(self._get('VIDEO_IN_BGR', {'FILTER_BGR': 'false', 'VIDEO_IN_BGR': 'true'}))

    def test_precedence_sync(self):
        self.assertTrue(self._get('VIDEO_IN_SYNC', {'FILTER_SYNC': 'false', 'VIDEO_IN_SYNC': 'true'}))

    def test_precedence_loop(self):
        self.assertEqual(self._get('VIDEO_IN_LOOP', {'FILTER_LOOP': '1', 'VIDEO_IN_LOOP': '10'}), 10)

    def test_precedence_maxfps(self):
        self.assertEqual(self._get('VIDEO_IN_MAXFPS', {'FILTER_MAXFPS': '10', 'VIDEO_IN_MAXFPS': '30'}), 30.0)

    def test_precedence_maxsize(self):
        self.assertEqual(self._get('VIDEO_IN_MAXSIZE', {'FILTER_MAXSIZE': '640x480', 'VIDEO_IN_MAXSIZE': '1920x1080'}), '1920x1080')

    def test_precedence_resize(self):
        self.assertEqual(self._get('VIDEO_IN_RESIZE', {'FILTER_RESIZE': '320x240', 'VIDEO_IN_RESIZE': '640x480'}), '640x480')

    # --- Defaults (no env vars set) ---

    def test_default_bgr(self):
        self.assertTrue(self._get('VIDEO_IN_BGR', {}))

    def test_default_sync(self):
        self.assertFalse(self._get('VIDEO_IN_SYNC', {}))

    def test_default_loop(self):
        self.assertFalse(self._get('VIDEO_IN_LOOP', {}))

    def test_default_maxfps(self):
        self.assertIsNone(self._get('VIDEO_IN_MAXFPS', {}))

    def test_default_maxsize(self):
        self.assertIsNone(self._get('VIDEO_IN_MAXSIZE', {}))

    def test_default_resize(self):
        self.assertIsNone(self._get('VIDEO_IN_RESIZE', {}))

    # --- Case insensitivity ---

    def test_case_insensitive_true(self):
        self.assertTrue(self._get('VIDEO_IN_SYNC', {'FILTER_SYNC': 'True'}))

    def test_case_insensitive_false(self):
        self.assertFalse(self._get('VIDEO_IN_BGR', {'FILTER_BGR': 'False'}))

    def test_case_insensitive_TRUE(self):
        self.assertTrue(self._get('VIDEO_IN_SYNC', {'FILTER_SYNC': 'TRUE'}))


# ---------------------------------------------------------------------------
#  VideoOut env var tests
# ---------------------------------------------------------------------------

class TestVideoOutEnvVars(unittest.TestCase):
    """Test VIDEO_OUT_* env vars with FILTER_* fallback."""

    MOD = 'openfilter.filter_runtime.filters.video_out'

    def _get(self, var, env):
        return _eval_with_env(self.MOD, var, env)

    # --- FILTER_* as primary configuration ---

    def test_filter_bgr_false(self):
        self.assertFalse(self._get('VIDEO_OUT_BGR', {'FILTER_BGR': 'false'}))

    def test_filter_bgr_true(self):
        self.assertTrue(self._get('VIDEO_OUT_BGR', {'FILTER_BGR': 'true'}))

    def test_filter_fps_int(self):
        self.assertEqual(self._get('VIDEO_OUT_FPS', {'FILTER_FPS': '30'}), 30)

    def test_filter_fps_float(self):
        self.assertEqual(self._get('VIDEO_OUT_FPS', {'FILTER_FPS': '29.97'}), 29.97)

    def test_filter_segtime_minutes(self):
        """Segtime '2:30' = 150 minutes total."""
        self.assertEqual(self._get('VIDEO_OUT_SEGTIME', {'FILTER_SEGTIME': '2:30'}), 150.0)

    def test_filter_segtime_single_value(self):
        """Segtime '5' = 5 minutes."""
        self.assertEqual(self._get('VIDEO_OUT_SEGTIME', {'FILTER_SEGTIME': '5'}), 5.0)

    def test_filter_params_json(self):
        self.assertEqual(self._get('VIDEO_OUT_PARAMS', {'FILTER_PARAMS': '{"preset": "fast"}'}), {'preset': 'fast'})

    def test_filter_params_nested(self):
        self.assertEqual(
            self._get('VIDEO_OUT_PARAMS', {'FILTER_PARAMS': '{"preset": "fast", "crf": 23}'}),
            {'preset': 'fast', 'crf': 23}
        )

    def test_filter_params_preserves_case(self):
        """JSON string values must preserve case (e.g., codec preset names)."""
        self.assertEqual(
            self._get('VIDEO_OUT_PARAMS', {'FILTER_PARAMS': '{"preset": "UltraFast", "profile": "High"}'}),
            {'preset': 'UltraFast', 'profile': 'High'}
        )

    def test_legacy_params_preserves_case(self):
        """Legacy VIDEO_OUT_PARAMS must also preserve case."""
        self.assertEqual(
            self._get('VIDEO_OUT_PARAMS', {'VIDEO_OUT_PARAMS': '{"vf": "scale=1280:720,Hflip"}'}),
            {'vf': 'scale=1280:720,Hflip'}
        )

    # --- Legacy VIDEO_OUT_* still works ---

    def test_legacy_bgr(self):
        self.assertFalse(self._get('VIDEO_OUT_BGR', {'VIDEO_OUT_BGR': 'false'}))

    def test_legacy_fps(self):
        self.assertEqual(self._get('VIDEO_OUT_FPS', {'VIDEO_OUT_FPS': '60'}), 60)

    def test_legacy_segtime(self):
        self.assertEqual(self._get('VIDEO_OUT_SEGTIME', {'VIDEO_OUT_SEGTIME': '10'}), 10.0)

    def test_legacy_params(self):
        self.assertEqual(self._get('VIDEO_OUT_PARAMS', {'VIDEO_OUT_PARAMS': '{"g": 30}'}), {'g': 30})

    # --- Legacy takes precedence ---

    def test_precedence_bgr(self):
        self.assertTrue(self._get('VIDEO_OUT_BGR', {'FILTER_BGR': 'false', 'VIDEO_OUT_BGR': 'true'}))

    def test_precedence_fps(self):
        self.assertEqual(self._get('VIDEO_OUT_FPS', {'FILTER_FPS': '15', 'VIDEO_OUT_FPS': '30'}), 30)

    def test_precedence_segtime(self):
        self.assertEqual(self._get('VIDEO_OUT_SEGTIME', {'FILTER_SEGTIME': '1', 'VIDEO_OUT_SEGTIME': '5'}), 5.0)

    def test_precedence_params(self):
        self.assertEqual(
            self._get('VIDEO_OUT_PARAMS', {'FILTER_PARAMS': '{"a": 1}', 'VIDEO_OUT_PARAMS': '{"b": 2}'}),
            {'b': 2}
        )

    # --- Defaults ---

    def test_default_bgr(self):
        self.assertTrue(self._get('VIDEO_OUT_BGR', {}))

    def test_default_fps(self):
        self.assertIsNone(self._get('VIDEO_OUT_FPS', {}))

    def test_default_segtime(self):
        self.assertIsNone(self._get('VIDEO_OUT_SEGTIME', {}))

    def test_default_params(self):
        self.assertIsNone(self._get('VIDEO_OUT_PARAMS', {}))


# ---------------------------------------------------------------------------
#  ImageIn env var tests
# ---------------------------------------------------------------------------

class TestImageInEnvVars(unittest.TestCase):
    """Test IMAGE_IN_* env vars with FILTER_* fallback."""

    MOD = 'openfilter.filter_runtime.filters.image_in'

    def _get(self, var, env):
        return _eval_with_env(self.MOD, var, env)

    # --- FILTER_* as primary configuration ---

    def test_filter_poll_interval(self):
        self.assertEqual(self._get('IMAGE_IN_POLL_INTERVAL', {'FILTER_POLL_INTERVAL': '10.0'}), 10.0)

    def test_filter_poll_interval_int(self):
        self.assertEqual(self._get('IMAGE_IN_POLL_INTERVAL', {'FILTER_POLL_INTERVAL': '3'}), 3.0)

    def test_filter_loop_true(self):
        self.assertTrue(self._get('IMAGE_IN_LOOP', {'FILTER_LOOP': 'true'}))

    def test_filter_loop_false(self):
        self.assertFalse(self._get('IMAGE_IN_LOOP', {'FILTER_LOOP': 'false'}))

    def test_filter_recursive_true(self):
        self.assertTrue(self._get('IMAGE_IN_RECURSIVE', {'FILTER_RECURSIVE': 'true'}))

    def test_filter_recursive_false(self):
        self.assertFalse(self._get('IMAGE_IN_RECURSIVE', {'FILTER_RECURSIVE': 'false'}))

    def test_filter_maxfps(self):
        self.assertEqual(self._get('IMAGE_IN_MAXFPS', {'FILTER_MAXFPS': '5'}), 5.0)

    def test_filter_maxfps_float(self):
        self.assertEqual(self._get('IMAGE_IN_MAXFPS', {'FILTER_MAXFPS': '0.1'}), 0.1)

    # --- Legacy IMAGE_IN_* still works ---

    def test_legacy_poll_interval(self):
        self.assertEqual(self._get('IMAGE_IN_POLL_INTERVAL', {'IMAGE_IN_POLL_INTERVAL': '20'}), 20.0)

    def test_legacy_loop(self):
        self.assertTrue(self._get('IMAGE_IN_LOOP', {'IMAGE_IN_LOOP': 'true'}))

    def test_legacy_recursive(self):
        self.assertTrue(self._get('IMAGE_IN_RECURSIVE', {'IMAGE_IN_RECURSIVE': 'true'}))

    def test_legacy_maxfps(self):
        self.assertEqual(self._get('IMAGE_IN_MAXFPS', {'IMAGE_IN_MAXFPS': '60'}), 60.0)

    # --- Legacy takes precedence ---

    def test_precedence_poll_interval(self):
        self.assertEqual(
            self._get('IMAGE_IN_POLL_INTERVAL', {'FILTER_POLL_INTERVAL': '5', 'IMAGE_IN_POLL_INTERVAL': '15'}),
            15.0
        )

    def test_precedence_loop(self):
        self.assertTrue(self._get('IMAGE_IN_LOOP', {'FILTER_LOOP': 'false', 'IMAGE_IN_LOOP': 'true'}))

    def test_precedence_recursive(self):
        self.assertTrue(self._get('IMAGE_IN_RECURSIVE', {'FILTER_RECURSIVE': 'false', 'IMAGE_IN_RECURSIVE': 'true'}))

    def test_precedence_maxfps(self):
        self.assertEqual(self._get('IMAGE_IN_MAXFPS', {'FILTER_MAXFPS': '5', 'IMAGE_IN_MAXFPS': '30'}), 30.0)

    # --- Defaults ---

    def test_default_poll_interval(self):
        self.assertEqual(self._get('IMAGE_IN_POLL_INTERVAL', {}), 5.0)

    def test_default_loop(self):
        self.assertFalse(self._get('IMAGE_IN_LOOP', {}))

    def test_default_recursive(self):
        self.assertFalse(self._get('IMAGE_IN_RECURSIVE', {}))

    def test_default_maxfps(self):
        self.assertIsNone(self._get('IMAGE_IN_MAXFPS', {}))


# ---------------------------------------------------------------------------
#  ImageOut env var tests
# ---------------------------------------------------------------------------

class TestImageOutEnvVars(unittest.TestCase):
    """Test IMAGE_OUT_* env vars with FILTER_* fallback."""

    MOD = 'openfilter.filter_runtime.filters.image_out'

    def _get(self, var, env):
        return _eval_with_env(self.MOD, var, env)

    # --- FILTER_* as primary configuration ---

    def test_filter_bgr_false(self):
        self.assertFalse(self._get('IMAGE_OUT_BGR', {'FILTER_BGR': 'false'}))

    def test_filter_bgr_true(self):
        self.assertTrue(self._get('IMAGE_OUT_BGR', {'FILTER_BGR': 'true'}))

    def test_filter_quality(self):
        self.assertEqual(self._get('IMAGE_OUT_QUALITY', {'FILTER_QUALITY': '80'}), 80)

    def test_filter_quality_min(self):
        self.assertEqual(self._get('IMAGE_OUT_QUALITY', {'FILTER_QUALITY': '1'}), 1)

    def test_filter_quality_max(self):
        self.assertEqual(self._get('IMAGE_OUT_QUALITY', {'FILTER_QUALITY': '100'}), 100)

    def test_filter_compression(self):
        self.assertEqual(self._get('IMAGE_OUT_COMPRESSION', {'FILTER_COMPRESSION': '3'}), 3)

    def test_filter_compression_min(self):
        self.assertEqual(self._get('IMAGE_OUT_COMPRESSION', {'FILTER_COMPRESSION': '0'}), 0)

    def test_filter_compression_max(self):
        self.assertEqual(self._get('IMAGE_OUT_COMPRESSION', {'FILTER_COMPRESSION': '9'}), 9)

    # --- Legacy IMAGE_OUT_* still works ---

    def test_legacy_bgr(self):
        self.assertFalse(self._get('IMAGE_OUT_BGR', {'IMAGE_OUT_BGR': 'false'}))

    def test_legacy_quality(self):
        self.assertEqual(self._get('IMAGE_OUT_QUALITY', {'IMAGE_OUT_QUALITY': '50'}), 50)

    def test_legacy_compression(self):
        self.assertEqual(self._get('IMAGE_OUT_COMPRESSION', {'IMAGE_OUT_COMPRESSION': '2'}), 2)

    # --- Legacy takes precedence ---

    def test_precedence_bgr(self):
        self.assertTrue(self._get('IMAGE_OUT_BGR', {'FILTER_BGR': 'false', 'IMAGE_OUT_BGR': 'true'}))

    def test_precedence_quality(self):
        self.assertEqual(self._get('IMAGE_OUT_QUALITY', {'FILTER_QUALITY': '50', 'IMAGE_OUT_QUALITY': '90'}), 90)

    def test_precedence_compression(self):
        self.assertEqual(self._get('IMAGE_OUT_COMPRESSION', {'FILTER_COMPRESSION': '1', 'IMAGE_OUT_COMPRESSION': '8'}), 8)

    # --- Defaults ---

    def test_default_bgr(self):
        self.assertTrue(self._get('IMAGE_OUT_BGR', {}))

    def test_default_quality(self):
        self.assertEqual(self._get('IMAGE_OUT_QUALITY', {}), 95)

    def test_default_compression(self):
        self.assertEqual(self._get('IMAGE_OUT_COMPRESSION', {}), 6)


# ---------------------------------------------------------------------------
#  Cross-filter interaction tests
# ---------------------------------------------------------------------------

class TestCrossFilterEnvVars(unittest.TestCase):
    """Test that shared FILTER_* env vars correctly propagate to multiple filters."""

    def test_filter_bgr_affects_both_video_in_and_out(self):
        self.assertFalse(_eval_with_env('openfilter.filter_runtime.filters.video_in', 'VIDEO_IN_BGR', {'FILTER_BGR': 'false'}))
        self.assertFalse(_eval_with_env('openfilter.filter_runtime.filters.video_out', 'VIDEO_OUT_BGR', {'FILTER_BGR': 'false'}))

    def test_filter_bgr_affects_image_out(self):
        self.assertFalse(_eval_with_env('openfilter.filter_runtime.filters.image_out', 'IMAGE_OUT_BGR', {'FILTER_BGR': 'false'}))

    def test_filter_loop_affects_both_video_in_and_image_in(self):
        self.assertTrue(_eval_with_env('openfilter.filter_runtime.filters.video_in', 'VIDEO_IN_LOOP', {'FILTER_LOOP': 'true'}))
        self.assertTrue(_eval_with_env('openfilter.filter_runtime.filters.image_in', 'IMAGE_IN_LOOP', {'FILTER_LOOP': 'true'}))

    def test_filter_maxfps_affects_both_video_in_and_image_in(self):
        self.assertEqual(_eval_with_env('openfilter.filter_runtime.filters.video_in', 'VIDEO_IN_MAXFPS', {'FILTER_MAXFPS': '10'}), 10.0)
        self.assertEqual(_eval_with_env('openfilter.filter_runtime.filters.image_in', 'IMAGE_IN_MAXFPS', {'FILTER_MAXFPS': '10'}), 10.0)

    def test_independent_legacy_prefixes(self):
        self.assertFalse(_eval_with_env('openfilter.filter_runtime.filters.video_in', 'VIDEO_IN_BGR', {'VIDEO_IN_BGR': 'false'}))
        self.assertTrue(_eval_with_env('openfilter.filter_runtime.filters.video_out', 'VIDEO_OUT_BGR', {'VIDEO_OUT_BGR': 'true'}))

    def test_mixed_legacy_and_filter_prefix(self):
        self.assertEqual(_eval_with_env('openfilter.filter_runtime.filters.video_in', 'VIDEO_IN_MAXFPS', {'VIDEO_IN_MAXFPS': '60', 'FILTER_MAXFPS': '30'}), 60.0)
        self.assertEqual(_eval_with_env('openfilter.filter_runtime.filters.image_in', 'IMAGE_IN_MAXFPS', {'FILTER_MAXFPS': '30'}), 30.0)


# ---------------------------------------------------------------------------
#  FilterConfig.get_config() interaction tests
# ---------------------------------------------------------------------------

class TestFilterConfigInteraction(unittest.TestCase):
    """Test that Filter.get_config() and module-level defaults coexist correctly."""

    def test_get_config_reads_filter_prefix(self):
        from openfilter.filter_runtime.filter import Filter
        env = {'FILTER_SYNC': 'true', 'FILTER_BGR': 'false', 'FILTER_MAXFPS': '15'}
        with patch.dict(os.environ, env, clear=False):
            for k in ALL_FILTER_ENV_VARS:
                if k not in env:
                    os.environ.pop(k, None)
            cfg = Filter.get_config()
        self.assertTrue(cfg.get('sync'))
        self.assertFalse(cfg.get('bgr'))
        self.assertEqual(cfg.get('maxfps'), 15)

    def test_module_defaults_align_with_filter_config(self):
        from openfilter.filter_runtime.filter import Filter
        env = {'FILTER_SYNC': 'true', 'FILTER_MAXFPS': '25'}
        module_sync = _eval_with_env('openfilter.filter_runtime.filters.video_in', 'VIDEO_IN_SYNC', env)
        module_maxfps = _eval_with_env('openfilter.filter_runtime.filters.video_in', 'VIDEO_IN_MAXFPS', env)
        with patch.dict(os.environ, env, clear=False):
            for k in ALL_FILTER_ENV_VARS:
                if k not in env:
                    os.environ.pop(k, None)
            cfg = Filter.get_config()
        self.assertTrue(module_sync)
        self.assertTrue(cfg.get('sync'))
        self.assertEqual(module_maxfps, 25.0)
        self.assertEqual(cfg.get('maxfps'), 25)


if __name__ == '__main__':
    unittest.main()
