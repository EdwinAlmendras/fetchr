from ..host_resolver import AbstractHostResolver
from ..types import DownloadInfo
import logging
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from fetchr.network import get_random_proxy
import aiohttp
logger = logging.getLogger("downloader.uploadee")

class UploadeeResolver(AbstractHostResolver):
    async def __aenter__(self):
        self.proxy = get_random_proxy()
        self.session = aiohttp.ClientSession(
            proxy=self.proxy
        )
    
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self
    
    async def get_download_info(self, url: str) -> DownloadInfo:
        logger.info(f"Processing {url}")
        async with self.session.get(url) as response:
            response.raise_for_status()
            html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        print("checking if file is found")
        if "There is no such file." in html:
            raise FileNotFoundError("File not found")
        anchor = soup.select_one("#d_l")
        print("found anchor")
        direct_url = anchor.get("href")
        async with self.session.head(direct_url) as reponse:
            reponse.raise_for_status()
            size = int(reponse.headers.get("Content-Length"))
            print(f"Size: {size}")
        filename = direct_url.split("/")[-1]
        download_info = DownloadInfo(download_url=direct_url, filename=filename, size=size, headers={})
        return download_info
        