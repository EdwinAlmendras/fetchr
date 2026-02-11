from ..host_resolver import AbstractHostResolver
from ..types import DownloadInfo
import logging
from bs4 import BeautifulSoup
from fetchr.network import get_random_proxy
import aiohttp

logger = logging.getLogger("downloader.uploadee")


class UploadeeResolver(AbstractHostResolver):
    async def __aenter__(self):
        self.proxy = get_random_proxy()
        self.session = aiohttp.ClientSession(proxy=self.proxy)
        logger.debug(f"UploadeeResolver: session created (proxy={self.proxy})")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            logger.debug("UploadeeResolver: session closed")
    
    async def get_download_info(self, url: str) -> DownloadInfo:
        logger.info(f"Processing {url}")
        
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                html = await response.text()
        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch page: {e}")
            raise Exception(f"Failed to fetch page for {url}: {e}")
        
        soup = BeautifulSoup(html, "html.parser")
        if "There is no such file." in html:
            logger.error("File not found on server")
            raise FileNotFoundError("File not found")
        
        anchor = soup.select_one("#d_l")
        if not anchor:
            logger.error(f"Could not find download anchor element #d_l on page")
            raise Exception(f"Failed to find download link on {url}")
        
        direct_url = anchor.get("href")
        if not direct_url:
            logger.error("Anchor element has no href attribute")
            raise Exception(f"Failed to get direct URL from {url}")
        
        try:
            async with self.session.head(direct_url) as resp:
                resp.raise_for_status()
                size = int(resp.headers.get("Content-Length", "0"))
                logger.debug(f"Uploadee: direct URL size={size}")
        except aiohttp.ClientError as e:
            logger.warning(f"Failed to get file size: {e}, using size=0")
            size = 0
        except ValueError as e:
            logger.warning(f"Invalid Content-Length header: {e}, using size=0")
            size = 0
        
        filename = direct_url.split("/")[-1]
        download_info = DownloadInfo(download_url=direct_url, filename=filename, size=size, headers={})
        return download_info
