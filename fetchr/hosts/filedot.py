import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Dict
from ..types import DownloadInfo
from ..types import DownloadInfo
from .common import BaseFormHostResolver
from fetchr.captcha import solve_css_position_captcha

class FiledotResolver(BaseFormHostResolver):
    host = "file.dot"
    



    async def get_download_info(self, url: str) -> DownloadInfo:
        if not self.session:
            raise RuntimeError("Usar dentro de un context manager: async with AnonFileDownloader() as downloader:")
        
        print(f"🔍 Iniciando descarga de: {url}")
        
        # PASO 1: Obtener página inicial
        print("📄 Paso 1: Obteniendo página inicial...")
        response = await self.session.get(url)
        response.raise_for_status()
        html_content = await response.text()
        soup = BeautifulSoup(html_content, 'html.parser')
        form_data = self._extract_form_data(soup)
        form_data['method_free'] = 'Liberta Descarga'
        
        async with self.session.post(url, data=form_data, headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            }) as response:
            if response.status != 200:
                raise ValueError(f"Error en paso 2: {response.status}")
            
            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')
        
        captcha_div = soup.select_one("#commonId table tr td div")
        if not captcha_div:
            raise ValueError("No captcha div found")
        form_data = self._extract_form_data(soup)
        form_data['adblock_detected'] = '0'
        captcha_code = solve_css_position_captcha(captcha_div)
        form_data['code'] = str(captcha_code)

        # await 7 seconds
        await asyncio.sleep(7)
        
        async with self.session.post(url, data=form_data) as response:
            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')
            
        anchor = soup.select_one("table a")
        if not anchor:
             raise ValueError("Download link not found")
             
        direct_url = anchor.get("href")
        if not isinstance(direct_url, str):
             raise ValueError("Invalid download link")
             
        # extract filename from direct_url
        filename = direct_url.split("/")[-1]
        print(direct_url)
        filesize = 0
        async with self.session.head(direct_url, ssl=False) as response:
            if 'Content-Length' in response.headers:
                filesize_bytes = int(response.headers['Content-Length'])
                filesize = filesize_bytes
            else:
                raise ValueError("No filesize found")

        download_info = DownloadInfo(
            filename=filename,
            size=filesize,
            download_url=direct_url,
            headers={},
        )
        return download_info
    
