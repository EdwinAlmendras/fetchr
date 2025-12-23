import logging
import aiohttp
from fetchr.types import DownloadInfo
from fetchr.host_resolver import AbstractHostResolver
from fetchr.resolver import get_direct_link
from fetchr.network.proxy import get_aiohttp_proxy_connector
logger = logging.getLogger("fetchr.hosts.pixeldrain")

class PixelDrainResolver(AbstractHostResolver):
    def __init__(self, timeout: int = 5):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Upgrade-Insecure-Requests': '1',
        }
    async def __aenter__(self):
        self.session = get_aiohttp_proxy_connector()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_download_info(self, url: str) -> DownloadInfo:
        if not self.session:
            await self.__aenter__()
            
        api_url = url.replace("/u/", "/api/file/")
        logger.info(f"[pixeldrain] Resolving: {url}")
        logger.debug(f"[pixeldrain] API URL: {api_url}")
        
        logger.info(f"[pixeldrain] Step 1: Fetching API info...")
        async with self.session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status != 200:
                try:
                    data = await response.json()
                    error_msg = data.get('message', f"HTTP {response.status}")
                except Exception:
                    error_msg = f"HTTP {response.status}"
                logger.error(f"Pixeldrain API error for {url}: {error_msg}")
                raise Exception(f"Pixeldrain API error: {error_msg}")
            
            try:
                data = await response.json()
                if not data.get('success', True):
                    message = data.get('message', 'Unknown error')
                    if message == "file_rate_limited_captcha_required":
                        direct_link = await get_direct_link(url)
                    else:
                        logger.error(f"Pixeldrain API error for {url}: {message}")
                        raise Exception(f"Pixeldrain API error: {message}")
                else:
                    direct_link = url
            except aiohttp.ContentTypeError:
                direct_link = url
        
        logger.info(f"[pixeldrain] Step 1 complete. Direct link: {direct_link}")
        logger.info(f"[pixeldrain] Step 2: Fetching headers via HEAD request...")
        async with self.session.head(direct_link, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            headers_info = dict(response.headers)
            if 'Content-Length' not in headers_info:
                logger.error(f"Missing Content-Length header for {url}")
                raise Exception(f"Missing Content-Length header for {url}")
            filesize = int(headers_info['Content-Length'])
            
            if 'Content-Disposition' not in headers_info:
                logger.error(f"Missing Content-Disposition header for {url}")
                raise Exception(f"Missing Content-Disposition header for {url}")
            try:
                filename = headers_info['Content-Disposition'].split('filename=')[1].split(';')[0].strip('"')
            except (IndexError, KeyError) as e:
                logger.error(f"Failed to parse filename from Content-Disposition for {url}")
                raise Exception(f"Failed to parse filename from Content-Disposition for {url}") from e
        
        logger.info(f"[pixeldrain] Step 2 complete. Filename: {filename}, Size: {filesize}")
        download_info = DownloadInfo(
            filename=filename,
            size=filesize,
            download_url=direct_link,
            headers={},
        )

        logger.info(f"[pixeldrain] Resolved successfully: {filename} ({filesize} bytes)")
        return download_info
    
