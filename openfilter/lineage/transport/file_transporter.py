"""
Factory for creating transport instances.
"""

from typing import Optional, Dict, Any
from openlineage.client.transport import Transport

def get_transport(mode: str = "console", **kwargs) -> Transport:
    """Get a transport instance based on the mode.
    
    Args:
        mode: The transport mode ("console", "http", or "file")
        **kwargs: Additional arguments for the transport
        
    Returns:
        Transport: The configured transport instance
        
    Raises:
        ValueError: If the mode is not supported
    """
    if mode == "console":
        from .console import get_console_transport
        return get_console_transport(**kwargs)
    elif mode == "http":
        from .http import get_http_transport
        return get_http_transport(**kwargs)
    elif mode == "file":
        from .file import get_file_transport
        return get_file_transport(**kwargs)
    else:
        raise ValueError(f"Unsupported transport mode: {mode}") 