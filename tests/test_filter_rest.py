#!/usr/bin/env python

import os
import unittest
from queue import Queue
from unittest.mock import patch

from openfilter.filter_runtime.filters.rest import REST, RESTConfig
from openfilter.filter_runtime.utils import adict


class TestRESTConfig(unittest.TestCase):
    """Test the RESTConfig class."""

    def test_default_config(self):
        config = RESTConfig()
        self.assertIsNone(config.host)
        self.assertIsNone(config.port)
        self.assertIsNone(config.auth_token)
        self.assertIsNone(config.cors_origins)

    def test_auth_token_config_param(self):
        config = RESTConfig()
        config.auth_token = 'my-secret'
        self.assertEqual(config.auth_token, 'my-secret')

    def test_cors_origins_config_param(self):
        config = RESTConfig()
        config.cors_origins = 'https://portal.plainsight.tech'
        self.assertEqual(config.cors_origins, 'https://portal.plainsight.tech')


class TestRESTCreateApp(unittest.TestCase):
    """Test the REST.create_app() method."""

    def _make_rest_app(self, auth_token=None, cors_origins=None):
        rest = object.__new__(REST)
        rest.queue = Queue(256)
        rest.id = 0
        config = RESTConfig()
        config.base_path = None
        config.endpoints = [adict(methods=['GET'], path=None, topic='main')]
        config.resource_path = None
        config.declared_fps = None
        config.auth_token = auth_token
        config.cors_origins = cors_origins
        return rest.create_app(config)

    def test_create_app_returns_fastapi(self):
        from fastapi import FastAPI
        app = self._make_rest_app()
        self.assertIsInstance(app, FastAPI)

    def test_create_app_without_auth_allows_request(self):
        from fastapi.testclient import TestClient
        app = self._make_rest_app()
        client = TestClient(app)
        response = client.get('/')
        # REST returns 204 on success, not 401
        self.assertNotEqual(response.status_code, 401)

    def test_create_app_with_auth_rejects_unauthenticated(self):
        from fastapi.testclient import TestClient
        app = self._make_rest_app(auth_token='secret')
        client = TestClient(app)
        response = client.get('/')
        self.assertEqual(response.status_code, 401)

    def test_create_app_with_auth_accepts_valid_token(self):
        from fastapi.testclient import TestClient
        app = self._make_rest_app(auth_token='secret')
        client = TestClient(app)
        response = client.get('/?token=secret')
        self.assertNotEqual(response.status_code, 401)

    def test_create_app_with_auth_accepts_bearer_header(self):
        from fastapi.testclient import TestClient
        app = self._make_rest_app(auth_token='secret')
        client = TestClient(app)
        response = client.get('/', headers={'Authorization': 'Bearer secret'})
        self.assertNotEqual(response.status_code, 401)

    def test_create_app_with_cors_origins(self):
        from fastapi.testclient import TestClient
        app = self._make_rest_app(cors_origins='https://portal.plainsight.tech')
        client = TestClient(app)
        response = client.options('/', headers={
            'Origin': 'https://portal.plainsight.tech',
            'Access-Control-Request-Method': 'GET',
        })
        self.assertEqual(
            response.headers.get('access-control-allow-origin'),
            'https://portal.plainsight.tech',
        )

    def test_create_app_with_cors_blocks_unknown_origin(self):
        from fastapi.testclient import TestClient
        app = self._make_rest_app(cors_origins='https://portal.plainsight.tech')
        client = TestClient(app)
        response = client.options('/', headers={
            'Origin': 'https://evil.com',
            'Access-Control-Request-Method': 'GET',
        })
        self.assertNotEqual(
            response.headers.get('access-control-allow-origin'),
            'https://evil.com',
        )

    def test_create_app_with_auth_and_cors(self):
        from fastapi.testclient import TestClient
        app = self._make_rest_app(auth_token='secret', cors_origins='https://portal.plainsight.tech')
        client = TestClient(app)
        # Auth blocks without token
        response = client.get('/')
        self.assertEqual(response.status_code, 401)
        # CORS preflight bypasses auth
        response = client.options('/', headers={
            'Origin': 'https://portal.plainsight.tech',
            'Access-Control-Request-Method': 'GET',
        })
        self.assertIn(response.status_code, (200, 204))


class TestRESTConfigEnvVars(unittest.TestCase):
    """Test that REST normalize_config reads config from FILTER_* env vars."""

    def _normalize(self, **env_vars):
        with patch.dict(os.environ, env_vars, clear=False):
            return REST.normalize_config({
                'sources': 'http://0.0.0.0:8000;>main',
                'outputs': 'tcp://localhost:5551',
            })

    def test_auth_token_from_env(self):
        config = self._normalize(FILTER_AUTH_TOKEN='rest-env-secret')
        self.assertEqual(config.auth_token, 'rest-env-secret')

    def test_cors_origins_from_env(self):
        config = self._normalize(FILTER_CORS_ORIGINS='https://a.com,https://b.com')
        self.assertEqual(config.cors_origins, 'https://a.com,https://b.com')

    def test_port_from_env(self):
        # When using sources, source URL overrides env var for host/port.
        # Use endpoints config to test env var directly.
        with patch.dict(os.environ, {'FILTER_PORT': '9090'}, clear=False):
            config = REST.normalize_config({
                'endpoints': [adict(methods=['GET'], path=None, topic='main')],
                'outputs': 'tcp://localhost:5551',
            })
        self.assertEqual(config.port, 9090)

    def test_declared_fps_from_env(self):
        config = self._normalize(FILTER_DECLARED_FPS='30.0')
        self.assertEqual(config.declared_fps, 30.0)

    def test_base_path_from_env(self):
        config = self._normalize(FILTER_BASE_PATH='api/v1')
        self.assertEqual(config.base_path, 'api/v1')

    def test_defaults_to_none_when_unset(self):
        for key in ('FILTER_AUTH_TOKEN', 'FILTER_CORS_ORIGINS', 'FILTER_PORT',
                     'FILTER_DECLARED_FPS', 'FILTER_BASE_PATH', 'FILTER_RESOURCE_PATH'):
            os.environ.pop(key, None)
        config = self._normalize()
        self.assertIsNone(config.auth_token)
        self.assertIsNone(config.cors_origins)


if __name__ == '__main__':
    unittest.main()
