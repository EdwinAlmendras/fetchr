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

logger = logging.getLogger("downloader.filemirage")


class FileMirageResolver(AbstractHostResolver):
    
    def __init__(self):
        self.session = aiohttp.ClientSession()
        
        # set headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_download_info(self, url: str) -> DownloadInfo:
        if not self.session:
            raise RuntimeError("Usar dentro de un context manager: async with AnonFileDownloader() as downloader:")
        
        print(f"🔍 Iniciando descarga de: {url}")
        
        # PASO 1: Obtener página inicial
        print("📄 Paso 1: Obteniendo página inicial...")
        response = await self.session.get(url)
        response.raise_for_status()
        html = await response.text()
        
        #mathc window.location.href = "https://filemirage.com/es/file/direct/19b26496-26b0-4689-a176-14c451d81489"
        match = re.search(r'window\.location\.href\s*=\s*"([^"]+)"', html)
        if match:
            url = match.group(1)
            response = await self.session.get(url, allow_redirects=False)
            redirect_url = response.headers.get("Location")
            response = await self.session.get(redirect_url)
            filename = response.headers.get("Content-Disposition").split("filename=")[1].split(";")[0].strip('"')
            size = response.headers.get("Content-Length")
            return DownloadInfo(
                filename=filename,
                size=size,
                download_url=redirect_url,
                headers=response.headers,
            )
        else:
            raise ValueError("No direct url found")
        
