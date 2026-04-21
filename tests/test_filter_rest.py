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
        app = rest.create_app(config)
        app._rest_queue = rest.queue  # expose for test assertions
        return app

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


    def test_auth_credentials_stripped_from_frame_data(self):
        """Auth token and Authorization header must not leak into frame data."""
        from fastapi.testclient import TestClient
        app = self._make_rest_app(auth_token='secret')
        client = TestClient(app)

        # Send request with both token query param and bearer header
        response = client.get('/?token=secret&other=keep',
                              headers={'Authorization': 'Bearer secret', 'X-Custom': 'visible'})
        self.assertNotEqual(response.status_code, 401)

        # Check the frame data in the queue
        topic, frame = app._rest_queue.get(timeout=1)
        http_data = frame.data['http']
        # Token should be stripped from query_params
        self.assertNotIn('token', http_data.get('query_params', {}))
        # Authorization header should be stripped
        self.assertNotIn('authorization', http_data.get('headers', {}))
        # Other params/headers should be preserved
        self.assertEqual(http_data['query_params']['other'], 'keep')
        self.assertEqual(http_data['headers']['x-custom'], 'visible')
        # URL should not contain token
        self.assertNotIn('token=secret', http_data['url'])
        self.assertIn('other=keep', http_data['url'])


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

    def test_declared_fps_from_env(self):
        config = self._normalize(FILTER_DECLARED_FPS='30.0')
        self.assertEqual(config.declared_fps, 30.0)

    def test_defaults_to_none_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            for key in ('FILTER_AUTH_TOKEN', 'FILTER_CORS_ORIGINS',
                         'FILTER_DECLARED_FPS', 'FILTER_RESOURCE_PATH'):
                os.environ.pop(key, None)
            config = self._normalize()
        self.assertIsNone(config.auth_token)
        self.assertIsNone(config.cors_origins)


if __name__ == '__main__':
    unittest.main()
