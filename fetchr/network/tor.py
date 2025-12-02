"""
Tor client utilities for fetchr
"""
import aiohttp
from aiohttp_socks import ProxyConnector
from fetchr.config import TOR_PORT

_tor_client = None


def get_tor_client(
    headers: dict | None = None,
    cookies: dict | None = None,
    tor_port: int = None
):
    """Get or create a Tor-proxied aiohttp session."""
    global _tor_client
    
    port = tor_port or TOR_PORT
    
    if _tor_client and not _tor_client.closed:
        return _tor_client
    
    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{port}")
    
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0 Safari/537.36"
    }
    if headers:
        default_headers.update(headers)

    session = aiohttp.ClientSession(
        connector=connector,
        headers=default_headers,
        cookies=cookies or {}
    )
    _tor_client = session
    return session
