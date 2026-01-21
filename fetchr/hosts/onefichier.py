import os
import aiohttp
from fetchr.types import DownloadInfo
from fetchr.host_resolver import AbstractHostResolver
import logging
from fetchr.network import get_random_proxy
from fetchr.resolver import get_direct_link
from fetchr.utils import TimeLocker
from fetchr.config import REALDEBRID_BEARER_TOKEN

logger = logging.getLogger(__name__)

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}

locker = TimeLocker(60)


class OneFichierResolver(AbstractHostResolver):
    host = "1fichier.com"

    def __init__(self):
        proxy = get_random_proxy()
        self.proxy = proxy
        self.session = aiohttp.ClientSession(headers=headers, proxy=proxy)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
    
    async def _unrestrict_with_realdebrid(self, url: str) -> tuple[str, str, int]:
        api_url = "https://api.real-debrid.com/rest/1.0/unrestrict/link"
        api_headers = {
            "Authorization": f"Bearer {REALDEBRID_BEARER_TOKEN}",
        }
        data = {"link": url}
        
        async with self.session.post(api_url, headers=api_headers, data=data) as resp:
            resp.raise_for_status()
            result = await resp.json()
            return result.get("download"), result.get("filename", "unknown"), result.get("filesize", 0)
    
    async def get_direct_link(self, url: str):
        if REALDEBRID_BEARER_TOKEN:
            try:
                direct_link, _, _ = await self._unrestrict_with_realdebrid(url)
                return direct_link
            except Exception as e:
                logger.warning(f"Real-Debrid failed: {e}, falling back to standard resolver")
        
        await locker.wait()
        return await get_direct_link(url)

    async def get_download_info(self, url: str) -> DownloadInfo:
        if REALDEBRID_BEARER_TOKEN:
            try:
                direct_link, filename, filesize = await self._unrestrict_with_realdebrid(url)
                return DownloadInfo(direct_link, filename, filesize, {})
            except Exception as e:
                logger.warning(f"Real-Debrid failed: {e}, falling back to standard resolver")
        
        direct_link = await self.get_direct_link(url)
        filename = "unknown"
        filesize = 0
        
        async with self.session.head(direct_link) as response:
            headers_info = dict(response.headers)
            if 'Content-Length' in headers_info:
                filesize = int(headers_info['Content-Length'])
            if 'Content-Disposition' in headers_info:
                filename = headers_info['Content-Disposition'].split('filename=')[1].split(';')[0].strip('"')
        
        return DownloadInfo(direct_link, filename, filesize, {})
