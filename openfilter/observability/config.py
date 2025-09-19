"""
Configuration helpers for telemetry allowlist management.

This module provides utilities for reading and parsing the safe metrics allowlist
from environment variables or configuration files.
"""

import os
import yaml
from typing import Set, Dict, Optional


def read_allowlist() -> Set[str]:
    """Read the safe metrics allowlist from environment or file.
    
    Returns:
        Set of allowed metric names and patterns
    """
    # Try file first
    path = os.getenv("OF_SAFE_METRICS_FILE")
    if path:
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                return set(config.get("safe_metrics", []))
        except Exception as e:
            print(f"Warning: Failed to read allowlist from {path}: {e}")
    
    # Try environment variable
    env = os.getenv("OF_SAFE_METRICS")
    if env:
        return set(name.strip() for name in env.split(",") if name.strip())
    
    # Default: empty set (lock-down mode)
    return set()


def read_openlineage_config() -> Optional[Dict[str, str]]:
    """Read OpenLineage configuration from YAML file.
    
    Returns:
        Dictionary with OpenLineage configuration or None if not found
    """
    path = os.getenv("OF_SAFE_METRICS_FILE")
    if path:
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                ol_config = config.get("openlineage", {})
                if ol_config:
                    return {
                        "url": ol_config.get("url"),
                        "api_key": ol_config.get("api_key"), 
                        "heartbeat_interval": ol_config.get("heartbeat_interval", 10)
                    }
        except Exception as e:
            print(f"Warning: Failed to read OpenLineage config from {path}: {e}")
    
    return None


def read_otel_config() -> Optional[Dict[str, str]]:
    """Read OpenTelemetry configuration from YAML file or environment.
    
    Returns:
        Dictionary with OTEL configuration or None if not found
    """
    # Try YAML file first
    path = os.getenv("OF_SAFE_METRICS_FILE")
    if path:
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                otel_config = config.get("opentelemetry", {})
                if otel_config:
                    return {
                        "endpoint": otel_config.get("endpoint") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
                        "headers": otel_config.get("headers") or os.getenv("OTEL_EXPORTER_OTLP_HEADERS"),
                        "protocol": otel_config.get("protocol", "grpc"),
                        "export_interval": otel_config.get("export_interval", 30),
                        "enabled": otel_config.get("enabled", True)
                    }
        except Exception as e:
            print(f"Warning: Failed to read OTEL config from {path}: {e}")
    
    # Fallback to environment variables
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        return {
            "endpoint": endpoint,
            "headers": os.getenv("OTEL_EXPORTER_OTLP_HEADERS"),
            "protocol": os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
            "export_interval": int(os.getenv("OTEL_EXPORT_INTERVAL", "30")),
            "enabled": os.getenv("OTEL_ENABLED", "true").lower() in ("true", "1", "yes")
        }
    
    return None 