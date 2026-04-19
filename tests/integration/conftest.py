"""
Shared fixtures for openfilter integration tests.

Currently only provides the jaeger-all-in-one container lifecycle used by
the tracing export smoke test. Kept deliberately dependency-free — no
testcontainers-python, no docker-py — because the only thing we're doing
is starting a container, polling a port, tearing it down. subprocess +
urllib is enough for that.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterator

import pytest

JAEGER_IMAGE = "jaegertracing/all-in-one:1.65.0"
CONTAINER_STARTUP_TIMEOUT_SECS = 30


@dataclass
class JaegerContainer:
    """Handle to a running jaeger-all-in-one container.

    otlp_grpc_endpoint is a host:port string suitable for OTLPSpanExporter.
    query_base_url is the jaeger query API root (append /api/traces/<id>).
    """

    container_id: str
    otlp_grpc_endpoint: str
    query_base_url: str

    def fetch_trace_services(self, trace_id: str) -> list[str]:
        """Return the set of service.names that contributed spans to a trace.

        Returns an empty list if jaeger has not yet ingested the trace.
        """
        url = f"{self.query_base_url}/api/traces/{trace_id}"
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            # jaeger returns 404 when the trace doesn't exist yet.
            if exc.code == 404:
                return []
            raise
        except urllib.error.URLError:
            return []

        parsed = json.loads(body)
        data = parsed.get("data") or []
        if not data:
            return []
        processes = data[0].get("processes") or {}
        return sorted({p.get("serviceName", "") for p in processes.values() if p.get("serviceName")})

    def wait_for_trace(self, trace_id: str, timeout_secs: float = 10.0) -> list[str]:
        """Poll the query API for up to timeout_secs until the trace appears.

        Jaeger ingestion is fast but not zero — even on a laptop there's a
        100-500ms window between export and query visibility, and CI runners
        can be substantially slower.
        """
        deadline = time.monotonic() + timeout_secs
        last: list[str] = []
        while time.monotonic() < deadline:
            services = self.fetch_trace_services(trace_id)
            if services:
                return services
            last = services
            time.sleep(0.2)
        return last


def _docker_run_jaeger() -> JaegerContainer:
    # Publish both ports on random host ports so parallel test runs and any
    # pre-existing local jaeger don't conflict. docker run -p 0:<container>.
    out = subprocess.check_output(
        [
            "docker", "run", "--rm", "-d",
            "-p", "0:4317",
            "-p", "0:16686",
            "-e", "COLLECTOR_OTLP_ENABLED=true",
            JAEGER_IMAGE,
        ],
        text=True,
    )
    container_id = out.strip()

    def port(container_port: int) -> int:
        raw = subprocess.check_output(
            ["docker", "port", container_id, str(container_port)],
            text=True,
        ).strip().splitlines()
        # Output is like "0.0.0.0:32768\n[::]:32768" — take the IPv4 line.
        for line in raw:
            if line.startswith("0.0.0.0:"):
                return int(line.split(":")[1])
        raise RuntimeError(f"could not parse docker port for {container_port}: {raw!r}")

    otlp_port = port(4317)
    query_port = port(16686)

    jc = JaegerContainer(
        container_id=container_id,
        otlp_grpc_endpoint=f"localhost:{otlp_port}",
        query_base_url=f"http://localhost:{query_port}",
    )

    # Poll the query API until jaeger is ready to answer. The HTTP server
    # comes up slightly before the OTLP receiver, but the receiver is
    # always ready by the time this loop terminates.
    deadline = time.monotonic() + CONTAINER_STARTUP_TIMEOUT_SECS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{jc.query_base_url}/", timeout=1):
                return jc
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(0.2)
    # Didn't come up in time — grab logs for the failure message.
    logs = subprocess.run(
        ["docker", "logs", container_id], capture_output=True, text=True
    ).stdout[-2000:]
    subprocess.run(["docker", "stop", container_id], check=False, capture_output=True)
    raise RuntimeError(f"jaeger did not become ready in {CONTAINER_STARTUP_TIMEOUT_SECS}s\n{logs}")


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "info"], check=True, capture_output=True, timeout=5
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture(scope="module")
def jaeger() -> Iterator[JaegerContainer]:
    """Start jaeger-all-in-one once per test module.

    Skips the module if docker isn't reachable — the integration suite is
    a developer / CI tool, not a default unit test, so silently noop'ing
    in environments without docker is the polite behavior.
    """
    if os.environ.get("OPENFILTER_SKIP_INTEGRATION"):
        pytest.skip("OPENFILTER_SKIP_INTEGRATION set")
    if not _docker_available():
        pytest.skip("docker not available — integration tests require a running docker daemon")

    jc = _docker_run_jaeger()
    try:
        yield jc
    finally:
        subprocess.run(
            ["docker", "stop", jc.container_id],
            check=False,
            capture_output=True,
            timeout=15,
        )
