import aiohttp
from fetchr.types import DownloadInfo
from fetchr.host_resolver import AbstractHostResolver
import logging
from fetchr.network import get_random_proxy
from fetchr.resolver import get_direct_link
from fetchr.utils import TimeLocker

logger = logging.getLogger(__name__)

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}

locker = TimeLocker(60)


class OneFichierResolver(AbstractHostResolver):
    
    def __init__(self):
        proxy = get_random_proxy()
        self.proxy = proxy
        self.session = aiohttp.ClientSession(headers=headers, proxy=proxy)
    
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    async def get_direct_link(self, url: str):
        await locker.wait()
        return await get_direct_link(url)

    async def get_download_info(self, url: str) -> DownloadInfo:
        direct_link = await self.get_direct_link(url)
        async with self.session.head(direct_link) as response:
            headers_info = dict(response.headers)
            if 'Content-Length' in headers_info:
                filesize_bytes = int(headers_info['Content-Length'])
                filesize = filesize_bytes
            if 'Content-Disposition' in headers_info:
                filename = headers_info['Content-Disposition'].split('filename=')[1].split(';')[0].strip('"')
        download_info = DownloadInfo(direct_link, filename, filesize, {})
        return download_info
        
         
    async def get_download_info_with_debrid(self, url: str) -> DownloadInfo:
        from fetchr.debrid import get_direct_link
        direct_link = await get_direct_link(url)
        filename = "unknown"
        filesize = 0
        async with self.session.head(direct_link) as response:
            headers_info = dict(response.headers)
            if 'Content-Length' in headers_info:
                filesize_bytes = int(headers_info['Content-Length'])
                filesize = filesize_bytes
            if 'Content-Disposition' in headers_info:
                filename = headers_info['Content-Disposition'].split('filename=')[1].split(';')[0].strip('"')
        if not filename:
            filename = direct_link.split('/')[-1]
        return DownloadInfo(direct_link, filename, filesize, {})
