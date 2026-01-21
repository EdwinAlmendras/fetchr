import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Dict
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
from fetchr.network import get_aiohttp_proxy_connector
from fetchr.captcha import solve_css_position_captcha

class FiledotResolver(AbstractHostResolver):
    def __init__(self, timeout: int = 30):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    async def __aenter__(self):
        self.session = get_aiohttp_proxy_connector()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    def _extract_form_data(self, soup: BeautifulSoup, form_selector: str = 'form') -> Dict[str, str]:
        """Extrae datos de formularios ocultos"""
        form = soup.find('form')
        if not form:
            raise ValueError("No se encontró formulario en la página")
        
        form_data = {}
        for input_tag in form.find_all('input', type='hidden'):
            name = input_tag.get('name')
            value = input_tag.get('value', '')
            if name:
                form_data[name] = value
        
        return form_data
    



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
        form_data['code'] = int(captcha_code)

        # await 7 seconds
        await asyncio.sleep(7)
        
        async with self.session.post(url, data=form_data) as response:
            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')
            
        anchor = soup.select_one("table a")
        direct_url = anchor.get("href")
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
    
