"""Small OTLP helper shared by the tracing and metrics exporter factories.

Kept deliberately tiny so that ``observability.tracing`` (which pulls in the
OTel SDK trace stack) and ``filter_runtime.open_telemetry`` (which pulls in
the OTel SDK metrics stack) can both depend on it without importing each
other's heavy modules.
"""

from typing import Optional
from urllib.parse import urlparse


def infer_otlp_insecure(endpoint: Optional[str]) -> bool:
    """Infer the OTLP gRPC ``insecure`` flag from the endpoint URL scheme.

    ``http://`` is plaintext; ``https://`` is TLS; bare ``host:port`` is
    treated as TLS (secure default, matches the OTel SDK). Uses
    :func:`urllib.parse.urlparse` so the scheme comparison handles case
    normalization without pattern matching.

    Returns ``False`` (TLS) for ``None`` or empty input, on the principle
    that an unset endpoint will fall through to the OTel SDK's own default
    and we should err on the side of TLS rather than silently downgrade.
    """
    if not endpoint:
        return False
    return urlparse(endpoint).scheme == "http"
