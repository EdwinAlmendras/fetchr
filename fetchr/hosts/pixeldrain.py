import logging
import aiohttp
from fetchr.types import DownloadInfo
from fetchr.host_resolver import AbstractHostResolver
from fetchr.resolver import get_direct_link
from fetchr.network.proxy import get_aiohttp_proxy_connector
logger = logging.getLogger("fetchr.hosts.pixeldrain")

class PixelDrainResolver(AbstractHostResolver):
    host = "pixeldrain.com"
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
            
        direct_link = url.replace("/u/", "/api/file/")
        async with self.session.head(direct_link, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            headers_info = dict(response.headers)
            if 'Content-Length' not in headers_info:
                raise Exception(f"Missing Content-Length header for {url}")
            filesize = int(headers_info['Content-Length'])
            
            if 'Content-Disposition' not in headers_info:
                raise Exception(f"Missing Content-Disposition header for {url}")
            try:
                filename = headers_info['Content-Disposition'].split('filename=')[1].split(';')[0].strip('"')
            except (IndexError, KeyError) as e:
                raise Exception(f"Failed to parse filename from Content-Disposition for {url}") from e
        
        download_info = DownloadInfo(
            filename=filename,
            size=filesize,
            download_url=direct_link,
            headers={},
        )

        return download_info
    
