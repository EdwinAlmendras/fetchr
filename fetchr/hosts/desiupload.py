import logging
import asyncio
from bs4 import BeautifulSoup
from ..types import DownloadInfo
from .common import BaseFormHostResolver
from fetchr.captcha import solve_css_position_captcha

logger = logging.getLogger(__file__)

class DesiUploadResolver(BaseFormHostResolver):
    host = "desiupload.co"
    async def get_download_info(self, url: str) -> DownloadInfo:
        if not self.session:
            raise RuntimeError("Usar dentro de un context manager: async with AnonFileDownloader() as downloader:")
        logger.info(f"Starting downloading url {url}")
        async with self.session.get(url) as response:
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
            with open('filedot_countdown.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            soup = BeautifulSoup(html_content, 'html.parser')
        
        
        
        
        
        
        # get captcha
        
        captcha_div = soup.select_one("#commonId table tr td div")
        if not captcha_div:
            raise ValueError("No captcha div found")
        form_data = self._extract_form_data(soup)
        form_data['adblock_detected'] = '0'
        captcha_code = solve_css_position_captcha(captcha_div)
        form_data['code'] = str(captcha_code)

        # await 7 seconds
        await asyncio.sleep(15)
        
        async with self.session.post(url, data=form_data) as response:
            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # save html
            with open('filedot_download.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
        
        anchor = soup.select_one("#direct_link a")
        if not anchor:
             raise ValueError("Download link not found")
             
        direct_url = anchor.get("href")
        if not isinstance(direct_url, str):
             raise ValueError("Invalid download link")
             
        # extract filename from direct_url
        filename = direct_url.split("/")[-1]
        print(direct_url)
        filesize = 0
        async with self.session.head(direct_url) as response:
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
    
