"""
HTTP transport for lineage events.
"""

from typing import Optional, Dict, Any
from openlineage.client.transport.http import HttpTransport, HttpConfig

def get_http_transport(url: str = "http://localhost:5000",
                      endpoint: str = "api/v1/lineage",
                      **kwargs) -> HttpTransport:
    """Get an HTTP transport instance.
    
    Args:
        url: The base URL for the HTTP endpoint
        endpoint: The API endpoint path
        **kwargs: Additional configuration for the HTTP transport
        
    Returns:
        HttpTransport: The configured HTTP transport
    """
    config = HttpConfig(
        url=url,
        endpoint=endpoint,
        **kwargs
    )
    return HttpTransport(config) 