"""
Shared HTTP security utilities for filters that expose FastAPI services.

Provides token-based authentication and configurable CORS for webvis, REST,
and any future filter that serves HTTP.

Configuration (via filter config parameters, which support FILTER_* env vars):
    auth_token:   When set, all requests must include ?token=<value>
                  or Authorization: Bearer <value>. Returns 401 if
                  missing or invalid. When unset, no auth (backwards compatible).

    cors_origins: Comma-separated list of allowed origins for CORS.
                  When unset, defaults to '*' (allow all, backwards compatible).
                  Example: 'https://portal.plainsight.tech,https://localhost:5173'
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_cors_origins(cors_origins: Optional[str]) -> list[str]:
    """Parse a comma-separated CORS origins string. Returns ['*'] if empty/None."""
    if not cors_origins or not cors_origins.strip():
        return ['*']
    return [origin.strip() for origin in cors_origins.split(',') if origin.strip()]


def add_token_auth_middleware(app: 'FastAPI', token: str) -> None:
    """Add middleware that validates ?token= or Authorization: Bearer on every request."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class TokenAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Skip auth for CORS preflight requests
            if request.method == 'OPTIONS':
                return await call_next(request)

            # Check query parameter first
            request_token = request.query_params.get('token')

            # Fall back to Authorization header
            if not request_token:
                auth_header = request.headers.get('authorization', '')
                if auth_header.lower().startswith('bearer '):
                    request_token = auth_header[7:].strip()

            if request_token != token:
                return JSONResponse(
                    status_code=401,
                    content={'detail': 'Unauthorized'},
                )

            return await call_next(request)

    app.add_middleware(TokenAuthMiddleware)


def configure_http_security(
    app: 'FastAPI',
    auth_token: Optional[str] = None,
    cors_origins: Optional[str] = None,
) -> None:
    """Configure CORS and optional token auth on a FastAPI app.

    Call this instead of manually adding CORSMiddleware. Reads config from
    the filter's config parameters (auth_token, cors_origins).

    Args:
        app: The FastAPI application to configure.
        auth_token: When set, require this token on all requests.
        cors_origins: Comma-separated allowed origins. Defaults to '*'.
    """
    from fastapi.middleware.cors import CORSMiddleware

    origins = parse_cors_origins(cors_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    token = auth_token.strip() if auth_token else None
    if token:
        add_token_auth_middleware(app, token)
        logger.info('Token authentication enabled')
        if origins == ['*']:
            logger.warning('Auth is enabled but CORS allows all origins — consider setting cors_origins')
    else:
        logger.info('No auth token configured — serving without authentication')
