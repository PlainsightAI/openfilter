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

    def test_auth_token_config_param(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'auth_token': 'my-secret',
        }
        normalized = Webvis.normalize_config(config)
        self.assertEqual(normalized.auth_token, 'my-secret')

    def test_cors_origins_config_param(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'cors_origins': 'https://portal.plainsight.tech',
        }
        normalized = Webvis.normalize_config(config)
        self.assertEqual(normalized.cors_origins, 'https://portal.plainsight.tech')

    def test_auth_token_default_none(self):
        config = {
            'sources': 'tcp://localhost:5550',
        }
        normalized = Webvis.normalize_config(config)
        self.assertIsNone(normalized.auth_token)

    def test_cors_origins_default_none(self):
        config = {
            'sources': 'tcp://localhost:5550',
        }
        normalized = Webvis.normalize_config(config)
        self.assertIsNone(normalized.cors_origins)

    def test_auth_token_from_env_var(self):
        os.environ['FILTER_AUTH_TOKEN'] = 'env-token'
        try:
            config = {'sources': 'tcp://localhost:5550'}
            normalized = Webvis.normalize_config(config)
            self.assertEqual(normalized.auth_token, 'env-token')
        finally:
            del os.environ['FILTER_AUTH_TOKEN']

    def test_cors_origins_from_env_var(self):
        os.environ['FILTER_CORS_ORIGINS'] = 'https://a.com,https://b.com'
        try:
            config = {'sources': 'tcp://localhost:5550'}
            normalized = Webvis.normalize_config(config)
            self.assertEqual(normalized.cors_origins, 'https://a.com,https://b.com')
        finally:
            del os.environ['FILTER_CORS_ORIGINS']


class TestWebvisCreateApp(unittest.TestCase):
    """Test the Webvis.create_app() method."""

    def _make_webvis(self):
        webvis = object.__new__(Webvis)
        webvis.streams = {}
        webvis.enable_json = False
        webvis.sleep_interval = 1.0
        webvis.current_data = {}
        return webvis

    def test_create_app_returns_fastapi(self):
        from fastapi import FastAPI
        webvis = self._make_webvis()
        app = webvis.create_app()
        self.assertIsInstance(app, FastAPI)

    def test_create_app_with_auth_rejects_unauthenticated(self):
        from fastapi.testclient import TestClient
        webvis = self._make_webvis()
        app = webvis.create_app(auth_token='secret')
        client = TestClient(app)
        response = client.get('/')
        self.assertEqual(response.status_code, 401)

    def test_create_app_without_auth_does_not_reject(self):
        from fastapi import FastAPI
        webvis = self._make_webvis()
        app = webvis.create_app()
        # Without auth, app should have middleware but not reject
        self.assertIsInstance(app, FastAPI)
        self.assertTrue(len(app.user_middleware) >= 1)

    def test_create_app_with_cors_origins(self):
        from fastapi.testclient import TestClient
        webvis = self._make_webvis()
        app = webvis.create_app(cors_origins='https://portal.plainsight.tech')
        client = TestClient(app)
        response = client.options('/', headers={
            'Origin': 'https://portal.plainsight.tech',
            'Access-Control-Request-Method': 'GET',
        })
        self.assertEqual(
            response.headers.get('access-control-allow-origin'),
            'https://portal.plainsight.tech',
        )


if __name__ == '__main__':
    unittest.main()
