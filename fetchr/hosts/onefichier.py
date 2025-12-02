import aiohttp
import re
from dataclasses import dataclass
from typing import Optional
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
from .passtrought import PassThroughResolver
import asyncio
import logging
from bs4 import BeautifulSoup
from fetchr.network import get_random_proxy
from fetchr.config import DEBRID_GATEWAY


logger = logging.getLogger("downloader.onefichier")

headers = {
    "authority": "1fichier.com",
    "scheme": "https",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "es-ES,es;q=0.9",
    "cache-control": "no-cache",
    "origin": "https://1fichier.com",
    "pragma": "no-cache",
    "priority": "u=0, i",
    "sec-ch-ua": "\"Google Chrome\";v=\"141\", \"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"141\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}
BASE_URL = DEBRID_GATEWAY
import asyncio
import time

class TimeLocker:
    def __init__(self, interval: float):
        self.interval = interval
        self._last_time = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        """Espera hasta que haya pasado `interval` desde la última ejecución."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_time
            remaining = self.interval - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_time = time.monotonic()


locker = TimeLocker(60)


# ?af=5006637
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
        
         
    async def get_download_info_with_debrid(self, url: str) -> DownloadInfo:
        from ..debrid import get_direct_link
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

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    async def main():
        resolver = OneFichierResolver()
        async with resolver as resolver:
            download_info = await resolver.get_download_info("https://1fichier.com/?eibod5rra2qjr5drix3t")
            print(download_info)
    asyncio.run(main())