"""Tests for HTTP security middleware (auth token + CORS configuration)."""

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openfilter.filter_runtime.filters.http_security import (
    configure_http_security,
    parse_cors_origins,
)


def make_app(auth_token: str | None = None, cors_origins: str | None = None) -> FastAPI:
    """Create a minimal FastAPI app with security configured."""
    app = FastAPI()
    configure_http_security(app, auth_token=auth_token, cors_origins=cors_origins)

    @app.get('/test')
    def test_endpoint():
        return {'ok': True}

    return app


class TestParseCorsOrigins(unittest.TestCase):
    def test_returns_wildcard_when_none(self):
        self.assertEqual(parse_cors_origins(None), ['*'])

    def test_returns_wildcard_when_empty(self):
        self.assertEqual(parse_cors_origins(''), ['*'])

    def test_returns_wildcard_when_whitespace(self):
        self.assertEqual(parse_cors_origins('   '), ['*'])

    def test_returns_single_origin(self):
        self.assertEqual(parse_cors_origins('https://example.com'), ['https://example.com'])

    def test_returns_multiple_origins(self):
        self.assertEqual(
            parse_cors_origins('https://a.com, https://b.com'),
            ['https://a.com', 'https://b.com'],
        )

    def test_strips_whitespace(self):
        self.assertEqual(
            parse_cors_origins('  https://a.com ,  https://b.com  '),
            ['https://a.com', 'https://b.com'],
        )

    def test_ignores_empty_entries(self):
        self.assertEqual(
            parse_cors_origins('https://a.com,,https://b.com,'),
            ['https://a.com', 'https://b.com'],
        )

    def test_returns_wildcard_when_only_separators(self):
        self.assertEqual(parse_cors_origins(','), ['*'])
        self.assertEqual(parse_cors_origins(', , '), ['*'])

    def test_wildcard_mixed_with_origins_normalizes_to_wildcard(self):
        self.assertEqual(parse_cors_origins('*,https://example.com'), ['*'])
        self.assertEqual(parse_cors_origins('https://a.com, *, https://b.com'), ['*'])


class TestNoAuth(unittest.TestCase):
    """When auth_token is not set, requests should pass through."""

    def setUp(self):
        self.client = TestClient(make_app())

    def test_request_succeeds_without_token(self):
        response = self.client.get('/test')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})


class TestTokenAuthQueryParam(unittest.TestCase):
    """When auth_token is set, ?token= must match."""

    def setUp(self):
        self.client = TestClient(make_app(auth_token='secret123'))

    def test_valid_token_in_query_param(self):
        response = self.client.get('/test?token=secret123')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})

    def test_missing_token_returns_401(self):
        response = self.client.get('/test')
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_returns_401(self):
        response = self.client.get('/test?token=wrong')
        self.assertEqual(response.status_code, 401)

    def test_empty_token_returns_401(self):
        response = self.client.get('/test?token=')
        self.assertEqual(response.status_code, 401)


class TestTokenAuthNonASCII(unittest.TestCase):
    """Non-ASCII tokens must work without raising TypeError."""

    def test_non_ascii_token_accepted(self):
        client = TestClient(make_app(auth_token='sëcret🔑'))
        response = client.get('/test?token=sëcret🔑')
        self.assertEqual(response.status_code, 200)

    def test_non_ascii_token_wrong_returns_401(self):
        client = TestClient(make_app(auth_token='sëcret🔑'))
        response = client.get('/test?token=wrong')
        self.assertEqual(response.status_code, 401)


class TestTokenAuthBearerHeader(unittest.TestCase):
    """When auth_token is set, Authorization: Bearer must match."""

    def setUp(self):
        self.client = TestClient(make_app(auth_token='secret123'))

    def test_valid_bearer_token(self):
        response = self.client.get('/test', headers={'Authorization': 'Bearer secret123'})
        self.assertEqual(response.status_code, 200)

    def test_valid_bearer_token_case_insensitive(self):
        response = self.client.get('/test', headers={'Authorization': 'bearer secret123'})
        self.assertEqual(response.status_code, 200)

    def test_wrong_bearer_token_returns_401(self):
        response = self.client.get('/test', headers={'Authorization': 'Bearer wrong'})
        self.assertEqual(response.status_code, 401)

    def test_missing_bearer_prefix_returns_401(self):
        response = self.client.get('/test', headers={'Authorization': 'secret123'})
        self.assertEqual(response.status_code, 401)

    def test_query_param_takes_precedence_over_header(self):
        response = self.client.get(
            '/test?token=secret123',
            headers={'Authorization': 'Bearer wrong'},
        )
        self.assertEqual(response.status_code, 200)


class TestCorsConfiguration(unittest.TestCase):
    """CORS should be configurable via cors_origins parameter."""

    def test_default_cors_allows_all_origins(self):
        client = TestClient(make_app())
        response = client.options(
            '/test',
            headers={'Origin': 'https://evil.com', 'Access-Control-Request-Method': 'GET'},
        )
        # With wildcard origins we return '*' and credentials are disabled
        # (CORS spec forbids '*' + credentials=true).
        self.assertEqual(response.headers.get('access-control-allow-origin'), '*')
        self.assertIsNone(response.headers.get('access-control-allow-credentials'))

    def test_restricted_cors_enables_credentials(self):
        client = TestClient(make_app(cors_origins='https://portal.plainsight.tech'))
        response = client.options(
            '/test',
            headers={
                'Origin': 'https://portal.plainsight.tech',
                'Access-Control-Request-Method': 'GET',
            },
        )
        # When specific origins are configured, credentials are allowed.
        self.assertEqual(response.headers.get('access-control-allow-credentials'), 'true')

    def test_restricted_cors_allows_configured_origin(self):
        client = TestClient(make_app(cors_origins='https://portal.plainsight.tech'))
        response = client.options(
            '/test',
            headers={
                'Origin': 'https://portal.plainsight.tech',
                'Access-Control-Request-Method': 'GET',
            },
        )
        self.assertEqual(
            response.headers.get('access-control-allow-origin'),
            'https://portal.plainsight.tech',
        )

    def test_restricted_cors_blocks_unknown_origin(self):
        client = TestClient(make_app(cors_origins='https://portal.plainsight.tech'))
        response = client.options(
            '/test',
            headers={'Origin': 'https://evil.com', 'Access-Control-Request-Method': 'GET'},
        )
        self.assertNotEqual(
            response.headers.get('access-control-allow-origin'),
            'https://evil.com',
        )


class TestAuthAndCorsTogether(unittest.TestCase):
    """Auth and CORS should work together."""

    def test_cors_preflight_bypasses_auth(self):
        client = TestClient(make_app(
            auth_token='secret123',
            cors_origins='https://portal.plainsight.tech',
        ))
        response = client.options(
            '/test',
            headers={
                'Origin': 'https://portal.plainsight.tech',
                'Access-Control-Request-Method': 'GET',
            },
        )
        self.assertIn(response.status_code, (200, 204))

    def test_plain_options_without_cors_headers_requires_auth(self):
        client = TestClient(make_app(
            auth_token='secret123',
            cors_origins='https://portal.plainsight.tech',
        ))
        # OPTIONS without Origin/Access-Control-Request-Method is NOT a preflight
        response = client.options('/test')
        self.assertEqual(response.status_code, 401)

    def test_actual_request_requires_auth(self):
        client = TestClient(make_app(
            auth_token='secret123',
            cors_origins='https://portal.plainsight.tech',
        ))
        response = client.get('/test')
        self.assertEqual(response.status_code, 401)


class TestWhitespaceToken(unittest.TestCase):
    """Edge cases for auth_token parameter."""

    def test_whitespace_only_token_means_no_auth(self):
        client = TestClient(make_app(auth_token='   '))
        response = client.get('/test')
        self.assertEqual(response.status_code, 200)

    def test_empty_string_token_means_no_auth(self):
        client = TestClient(make_app(auth_token=''))
        response = client.get('/test')
        self.assertEqual(response.status_code, 200)


class TestWebvisIntegration(unittest.TestCase):
    """Verify webvis create_app() uses configure_http_security."""

    def _make_webvis(self):
        from openfilter.filter_runtime.filters.webvis import Webvis
        webvis = object.__new__(Webvis)
        webvis.streams = {}
        webvis.enable_json = False
        webvis.sleep_interval = 1.0
        webvis.current_data = {}
        return webvis

    def test_webvis_with_auth_blocks_without_token(self):
        webvis = self._make_webvis()
        app = webvis.create_app(auth_token='webvis-secret')
        client = TestClient(app)
        response = client.get('/')
        self.assertEqual(response.status_code, 401)

    def test_webvis_with_auth_returns_401_json(self):
        webvis = self._make_webvis()
        app = webvis.create_app(auth_token='webvis-secret')
        client = TestClient(app)
        response = client.get('/sometopic')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {'detail': 'Unauthorized'})

    def test_webvis_no_auth_has_cors_middleware(self):
        webvis = self._make_webvis()
        app = webvis.create_app()
        self.assertTrue(len(app.user_middleware) >= 1,
                        'Expected at least CORS middleware')

    def test_webvis_with_auth_has_two_middlewares(self):
        webvis = self._make_webvis()
        app = webvis.create_app(auth_token='secret')
        # CORS + TokenAuth
        self.assertTrue(len(app.user_middleware) >= 2,
                        'Expected CORS + TokenAuth middleware')

    def test_webvis_with_cors_origins(self):
        webvis = self._make_webvis()
        app = webvis.create_app(auth_token='secret', cors_origins='https://portal.plainsight.tech')
        client = TestClient(app)
        # Auth blocks without token
        response = client.get('/')
        self.assertEqual(response.status_code, 401)
        # CORS preflight works for allowed origin
        response = client.options('/', headers={
            'Origin': 'https://portal.plainsight.tech',
            'Access-Control-Request-Method': 'GET',
        })
        self.assertIn(response.status_code, (200, 204))


class TestRESTIntegration(unittest.TestCase):
    """Verify REST create_app() uses configure_http_security."""

    def _make_rest_app(self, auth_token=None, cors_origins=None):
        from queue import Queue
        from openfilter.filter_runtime.filters.rest import REST, RESTConfig
        from openfilter.filter_runtime.utils import adict
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

    def test_rest_no_auth_allows_request(self):
        app = self._make_rest_app()
        client = TestClient(app)
        response = client.get('/')
        self.assertNotEqual(response.status_code, 401)

    def test_rest_with_auth_blocks_without_token(self):
        app = self._make_rest_app(auth_token='rest-secret')
        client = TestClient(app)
        response = client.get('/')
        self.assertEqual(response.status_code, 401)

    def test_rest_with_auth_allows_with_token(self):
        app = self._make_rest_app(auth_token='rest-secret')
        client = TestClient(app)
        response = client.get('/?token=rest-secret')
        self.assertNotEqual(response.status_code, 401)

    def test_rest_with_cors_origins(self):
        app = self._make_rest_app(
            auth_token='secret',
            cors_origins='https://portal.plainsight.tech',
        )
        client = TestClient(app)
        response = client.options('/', headers={
            'Origin': 'https://portal.plainsight.tech',
            'Access-Control-Request-Method': 'GET',
        })
        self.assertIn(response.status_code, (200, 204))


class TestWebvisConfigEnvVars(unittest.TestCase):
    """Verify webvis normalize_config reads auth_token and cors_origins from FILTER_* env vars."""

    def test_auth_token_from_env(self):
        from openfilter.filter_runtime.filters.webvis import Webvis
        with patch.dict(os.environ, {'FILTER_AUTH_TOKEN': 'env-secret'}, clear=False):
            config = Webvis.normalize_config({'sources': 'tcp://localhost:5550'})
        self.assertEqual(config.auth_token, 'env-secret')

    def test_cors_origins_from_env(self):
        from openfilter.filter_runtime.filters.webvis import Webvis
        with patch.dict(os.environ, {'FILTER_CORS_ORIGINS': 'https://a.com,https://b.com'}, clear=False):
            config = Webvis.normalize_config({'sources': 'tcp://localhost:5550'})
        self.assertEqual(config.cors_origins, 'https://a.com,https://b.com')

    def test_defaults_to_none_when_unset(self):
        from openfilter.filter_runtime.filters.webvis import Webvis
        with patch.dict(os.environ, {}, clear=False):
            # Remove the env vars if set
            os.environ.pop('FILTER_AUTH_TOKEN', None)
            os.environ.pop('FILTER_CORS_ORIGINS', None)
            config = Webvis.normalize_config({'sources': 'tcp://localhost:5550'})
        self.assertIsNone(config.auth_token)
        self.assertIsNone(config.cors_origins)


if __name__ == '__main__':
    unittest.main()
