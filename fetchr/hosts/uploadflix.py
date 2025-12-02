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
import aiohttp
logger = logging.getLogger("downloader.uploadflix")

class UploadFlixResolver(AbstractHostResolver):
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_download_info(self, url: str) -> DownloadInfo:
        logger.info(f"Processing {url}")
        response = await self.session.get(url)
        html = await response.text()
        if "404 NOT FOUND" in html:
            raise FileNotFoundError("File not found")
        
        if "File does not exist on this server." in html:
            raise FileNotFoundError("File not found")
        
        match = re.search(r'document\.location\s*=\s*"([^"]+)"', html)
        if match:
            logger.info(f"Found download url: {match.group(1)}")
            download_url = match.group(1)
            logger.info(f"Getting download info for {download_url}")
            
            
            # document.querySelector(".dfile").firstChild.textContent.trim()
            
            soup = BeautifulSoup(html, "html.parser")
            
            # if "404 NOT FOUND" in html, raise ValueError

            
            filename = soup.select_one(".dfile").contents[0].strip()
            # document.querySelector("div.filepanel.lft > div:nth-child(3) > span:nth-child(2)").innerText
            async with self.session.head(download_url, ssl=False) as response:
                response.raise_for_status()
                file_size = response.headers["Content-Length"]
            return DownloadInfo(download_url, filename, int(file_size), {})
        else:
            raise ValueError("No direct url found")

