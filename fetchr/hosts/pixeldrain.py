import aiohttp
import asyncio
import time
import re
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable, Awaitable
from urllib.parse import urljoin
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver

class PixelDrainResolver(AbstractHostResolver):
    def __init__(self, timeout: int = 5):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Upgrade-Insecure-Requests': '1',
        }
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers=self.headers,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_download_info(self, url: str) -> DownloadInfo:
        if not self.session:
            raise RuntimeError("Usar dentro de un context manager: async with AnonFileDownloader() as downloader:")
        
        resp1 = await self.session.get(url)
        # replace /u/ to /api/
        url = url.replace("/u/", "/api/file/")
        async with self.session.head(url, timeout=5) as response:
            if 'Content-Length' in response.headers:
                filesize_bytes = int(response.headers['Content-Length'])
                filesize = filesize_bytes
            else:
                filesize = 0
            filename = response.headers['Content-Disposition'].split('filename=')[1].split(';')[0].strip('"') if 'Content-Disposition' in response.headers else ""
        
        download_info = DownloadInfo(
            filename=filename,
            size=filesize,
            download_url=url,
            headers=response.headers,
        )
        return download_info
    
