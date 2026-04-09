#!/usr/bin/env python

import logging
import os
import unittest
from queue import Queue

from openfilter.filter_runtime.filters.rest import REST, RESTConfig
from openfilter.filter_runtime.utils import adict

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))


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


if __name__ == '__main__':
    unittest.main()
