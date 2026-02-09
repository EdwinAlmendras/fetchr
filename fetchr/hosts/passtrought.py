from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import aiohttp
import os
from fetchr.network import get_tor_client, get_aiohttp_proxy_connector, get_random_proxy
import logging
from urllib.parse import unquote
logger = logging.getLogger("downloader.passtrought")

def _env_proxy_hint():
    """Return a string if any proxy-related env var is set (for logging)."""
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        if os.environ.get(key):
            return f" (env {key} is set: {os.environ.get(key)[:50]}...)" if len(os.environ.get(key, "")) > 50 else f" (env {key}={os.environ.get(key)})"
    return ""


REDIRECT_HOSTS = [
    "sd2y3ekfioqfag45vmufbcezz44jfdz4ihefmogjfjih5sadmbmxzaid.onion", 
    "cpftwf66tdxnhrtau6t4hvm5sznlglv4r4ha5uxmc7ulhmcgry3mttyd",
    "gofilebzoq7kacpfve5sddz3o27ubclfqvnuxgb3yhoawon4w5tysgid.onion"
]


class PassThroughResolver(AbstractHostResolver):
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    async def __aenter__(self):
        # Use proxy session for all connections (except when explicitly using Tor)
        self.session = get_aiohttp_proxy_connector()
        hint = _env_proxy_hint()
        if hint:
            logger.info("PassThroughResolver: process has proxy env set%s", hint)
        logger.debug("PassThroughResolver: session created (with proxy)")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            logger.debug("PassThroughResolver: session closed")

    async def get_download_info(self, url: str, *args, **kwargs) -> DownloadInfo:
        use_tor = "onion" in url
        client = get_tor_client() if use_tor else self.session
        
        # Log which proxy we're using for non-Tor connections
        if not use_tor and hasattr(self.session, '_connector'):
            proxy_used = getattr(self.session._connector, 'proxy', None)
            client_type = "tor" if use_tor else f"proxy({proxy_used})"
        else:
            client_type = "tor" if use_tor else "direct"
            
        logger.info(
            "PassThroughResolver: url=%s client=%s",
            url,
            client_type,
        )
        if not client:
            logger.error("PassThroughResolver: client is None (session not ready?)")
            raise RuntimeError("PassThroughResolver: no HTTP client available")

        while True:
            logger.debug("PassThroughResolver: GET %s", url)
            response = await client.get(url, *args, **kwargs)
            logger.debug(
                "PassThroughResolver: response status=%s url=%s",
                response.status,
                response.url,
            )
            if response.status == 405:
                logger.warning("PassThroughResolver: 405 Method Not Allowed, retrying GET for %s", url)
                response = await client.get(url, *args, **kwargs)
                logger.debug("PassThroughResolver: retry response status=%s", response.status)
            if response.status == 200:
                final_url = str(response.url)
                if final_url != url:
                    logger.info("PassThroughResolver: redirect %s -> %s", url, final_url)
                url = final_url
                content_disp = response.headers.get("Content-Disposition")
                content_length = response.headers.get("Content-Length", "0")
                logger.info(
                    "PassThroughResolver: 200 OK final_url=%s Content-Length=%s Content-Disposition=%s",
                    url,
                    content_length,
                    content_disp or "(none)",
                )
                break
            logger.warning(
                "PassThroughResolver: unexpected status=%s for url=%s response_url=%s",
                response.status,
                url,
                response.url,
            )
            raise Exception(f"Failed to get download info, status code: {response.status}")

        filename = None
        if content_disp:
            cdl = content_disp.lower()
            # Prefer RFC 5987 filename* parameter, e.g. filename*=UTF-8''prasped.7z.004
            if "filename*=" in cdl:
                try:
                    # Extract the raw value after filename*=
                    raw_part = content_disp.split("filename*=", 1)[1].split(";", 1)[0].strip()
                    # Remove surrounding quotes if present
                    if raw_part.startswith('"') and raw_part.endswith('"'):
                        raw_part = raw_part[1:-1]
                    # Format: charset''urlencoded-filename
                    # Example: UTF-8''prasped.7z.004
                    if "''" in raw_part:
                        _, encoded_name = raw_part.split("''", 1)
                    else:
                        encoded_name = raw_part
                    filename = unquote(encoded_name)
                    logger.debug("PassThroughResolver: filename from filename*= %s", filename)
                except Exception as e:
                    logger.warning("PassThroughResolver: failed to parse filename* from Content-Disposition: %s", e)
                    filename = None
            # Fallback to simple filename=
            if not filename and "filename=" in cdl:
                try:
                    raw_part = content_disp.split("filename=", 1)[1].split(";", 1)[0].strip()
                    if raw_part.startswith('"') and raw_part.endswith('"'):
                        raw_part = raw_part[1:-1]
                    filename = raw_part
                    logger.debug("PassThroughResolver: filename from filename= %s", filename)
                except Exception as e:
                    logger.warning("PassThroughResolver: failed to parse filename from Content-Disposition: %s", e)
                    filename = None

        if not filename:
            filename = url.rstrip("/").split("/")[-1]
            logger.debug("PassThroughResolver: filename from URL path: %s", filename)

        size = int(response.headers.get("Content-Length", "0"))
        logger.info(
            "PassThroughResolver: returning DownloadInfo url=%s filename=%s size=%s",
            url,
            filename,
            size,
        )
        return DownloadInfo(url, filename, size, {})

    
