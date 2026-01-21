import aiohttp
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import asyncio
import time
import asyncio
import logging
from fetchr.network import get_random_proxy
from fetchr.config import DEBRID_GATEWAY


logger = logging.getLogger("downloader.krakenfiles")

BASE_URL = DEBRID_GATEWAY

class KrakenFilesResolver(AbstractHostResolver):
    host = "krakenfiles.com"
    
    def __init__(self):
        proxy = get_random_proxy()
        self.proxy = proxy
        self.session = aiohttp.ClientSession(proxy=proxy)
    
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    async def get_direct_link(self, url: str):
        endpoint = f"{BASE_URL}/resolve/?url={url}"
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, headers={
                    "ngrok-skip-browser-warning": "DONE"
                }) as response:
                response.raise_for_status()
                data = await response.json()
                reolved_url = data.get("url")
                if reolved_url:
                    print(f"Download url... {reolved_url}")
                    return reolved_url
                else:
                    raise Exception(f"Somethings wrong, {data.get('message')}")

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
        