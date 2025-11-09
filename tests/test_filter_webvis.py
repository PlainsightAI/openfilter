#!/usr/bin/env python

import logging
import os
import unittest
from time import sleep



from openfilter.filter_runtime import Filter
from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.webvis import Webvis, WebvisConfig


logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)

class TestWebvisConfig(unittest.TestCase):
    """Test the WebvisConfig class."""
    def test_normalize_config_basic(self):
        config = {
            'sources': 'tcp://localhost:5550'
        }
        normalized = Webvis.normalize_config(config)
        print(normalized)
        self.assertIsInstance(normalized, WebvisConfig)
        self.assertIsInstance(normalized.enable_json, bool)
        self.assertIsInstance(normalized.sleep_interval, float)
        assert True

    def test_default_config(self):
        config = WebvisConfig()
        self.assertFalse(config.enable_json)
        self.assertEqual(config.sleep_interval, 1.0)

    def test_enable_json(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'enable_json': 'true'
        }
        normalized = Webvis.normalize_config(config)
        self.assertTrue(normalized.enable_json)

    def test_set_interval(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'sleep_interval': 0.2
        }
        normalized = Webvis.normalize_config(config)
        self.assertFalse(normalized.enable_json)
        self.assertEqual(normalized.sleep_interval, 0.2)

if __name__ == '__main__':
    unittest.main()
