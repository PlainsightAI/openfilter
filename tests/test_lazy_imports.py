"""Verify that importing the filters package does not eagerly load optional dependencies."""

import importlib
import sys
import unittest


class TestFiltersPackageImport(unittest.TestCase):
    """The filters __init__.py must be empty — no eager imports of submodules."""

    def test_import_does_not_load_video_out(self):
        """Importing the filters package must NOT trigger video_out (which needs av)."""
        # Clear cached modules
        mods_to_remove = [k for k in sys.modules if k.startswith('openfilter.filter_runtime.filters')]
        saved = {k: sys.modules.pop(k) for k in mods_to_remove}

        # Block av to simulate video-in container (no av installed)
        import builtins
        _real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == 'av':
                raise ImportError("Mocked: av is not installed")
            return _real_import(name, *args, **kwargs)

        builtins.__import__ = _mock_import
        try:
            # This must NOT crash — __init__.py should be empty
            mod = importlib.import_module('openfilter.filter_runtime.filters')
            # No re-exports expected
            self.assertFalse(hasattr(mod, 'VideoOut'), "VideoOut should not be eagerly imported")
            self.assertFalse(hasattr(mod, 'ImageOut'), "ImageOut should not be eagerly imported")
            self.assertFalse(hasattr(mod, 'ImageIn'), "ImageIn should not be eagerly imported")
        finally:
            builtins.__import__ = _real_import
            # Restore
            for k in list(sys.modules):
                if k.startswith('openfilter.filter_runtime.filters'):
                    sys.modules.pop(k, None)
            sys.modules.update(saved)

    def test_submodule_direct_import_still_works(self):
        """Direct submodule imports must still work."""
        from openfilter.filter_runtime.filters.image_in import ImageIn
        self.assertIsNotNone(ImageIn)


if __name__ == '__main__':
    unittest.main()
