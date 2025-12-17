import aiohttp
import asyncio
import time
import re
import math
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable, Awaitable
from urllib.parse import urljoin, urlparse
from yarl import URL
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
from fetchr.network import get_aiohttp_proxy_connector
import logging
import os
import urllib.parse
logger = logging.getLogger(__name__)

class TimeoutSkipped(Exception):
    """Timeout skipped"""
    pass
class WrongCaptcha(Exception):
    """Wrong captcha"""
    pass


class AnonFileResolver(AbstractHostResolver):
    def __init__(self, timeout: int = 30):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.use_premium = os.getenv('ANONFILE_USE_PREMIUM', 'false').lower() == 'true'
        self.headers = {
            # Mirror browser-like headers as in test.sh
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
        }

    def _build_headers(self, referer_url: str | None = None) -> Dict[str, str]:
        headers = dict(self.headers)
        if referer_url:
            headers['Referer'] = referer_url
            try:
                parsed = urlparse(referer_url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                headers['Origin'] = origin
                headers['Host'] = parsed.netloc
            except Exception:
                pass
        return headers

    async def __aenter__(self):
        # Try to use proxy session; if proxies config/import fails, fall back to direct session
        try:
            self.session = get_aiohttp_proxy_connector()
        except Exception as e:
            logger.warning(f"Proxy session unavailable, using direct session: {e}")
            self.session = aiohttp.ClientSession(headers=self.headers, timeout=self.timeout)
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
        # Intenta capturar el valor del submit method_free exactamente como está en el formulario
        submit_btn = form.find('input', attrs={'name': 'method_free'})
        if submit_btn:
            form_data['method_free'] = submit_btn.get('value', 'Free Download >>')
        
        return form_data
    
    def _extract_captcha_image(self, soup: BeautifulSoup) -> str:
        captcha_image = soup.select_one('td img')
        if captcha_image:
            return captcha_image.get('src')
        return None
    
    def _extract_file_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        info = {}
        title_element = soup.find('h1', class_='download-title')
        if title_element:
            info['filename'] = title_element.get_text(strip=True)
        size_text = soup.get_text()
        size_match = re.search(r'size:\s*(\d+\.?\d*)\s*MB', size_text, re.IGNORECASE)
        if size_match:
            info['filesize_mb'] = float(size_match.group(1))
        return info
    
    def _check_link_element(self, link_element: BeautifulSoup, soup: BeautifulSoup) -> str:
        if not link_element:
            direct_div = soup.find('div', id='direct_link')
            if direct_div:
                link_element = direct_div.find('a')
        
        if not link_element:
            wrong_captcha = "Wrong captcha"
            skipped_timeout = "Skipped countdown"
            alert = soup.select_one('div.alert.alert-danger')
            if alert:
                error = alert.get_text().strip()
                if wrong_captcha in error:
                    raise WrongCaptcha("Wrong captcha")
                elif skipped_timeout in error:
                    raise TimeoutSkipped("Skipped countdown")
                else:
                    raise ValueError(error)
    
    def _extract_direct_link(self, soup: BeautifulSoup) -> tuple[str, int]:
        """Extrae el enlace directo y tiempo de expiración de la página final"""
        link_element = soup.find('a', class_='stretched-link')
        self._check_link_element(link_element, soup)
        direct_url = link_element.get('href')
        if not direct_url:
            raise ValueError("Enlace directo vacío")
        expires_match = re.search(r'next\s+(\d+)\s+hours?', soup.get_text())
        expires_hours = int(expires_match.group(1)) if expires_match else 8
        return direct_url, expires_hours
    
    def _extract_file_id_from_url(self, url: str) -> str:
        """Extrae el ID del archivo de la URL"""
        # Patrón: anonfile.de/FILEID o anonfile.de/FILEID/filename
        match = re.search(r'anonfile\.de/([a-zA-Z0-9]+)', url)
        return match.group(1) if match else 'unknown'
    
    async def get_download_info(self, anonfile_url: str, retry_no: int = 0) -> DownloadInfo:
        
        
        file_id = self._extract_file_id_from_url(anonfile_url)
        logger.info(f"Getting page from anonfile: {anonfile_url}")
        # Normalize to HTTPS to mirror browser flow
        if anonfile_url.startswith("http://"):
            anonfile_url = "https://" + anonfile_url[len("http://"):]

        if self.use_premium:
            return await self._premium_method(anonfile_url)
        else:
            await self._free_method(anonfile_url, retry_no)
    
    async def _free_method(self, anonfile_url: str, retry_no: int = 0) -> Dict[str, str]:
        from fetchr.hosts.axfc import captcha_solver, ErrorImageInvalid
        async with self.session.get(anonfile_url) as response:
            response.raise_for_status()
            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')
            current_url = str(response.url)
        form_data = self._extract_form_data(soup)
        form_data['usr_login'] = ''
        try:
            self.session.cookie_jar.update_cookies({'_pk_ses.1.b0a4': '1'}, response_url=URL(current_url))
        except Exception as e:
            logger.warning(f"Failed to inject _pk_ses.1.b0a4 cookie: {e}")
        post_headers = self._build_headers(current_url)
        async with self.session.post(
            current_url,
            data=form_data,
            headers=post_headers,
        ) as response:
            response.raise_for_status()
            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')
            current_url = str(response.url)
        
        file_info = self._extract_file_info(soup)
        form_data_2 = self._extract_form_data(soup)
        form_data_2['adblock_detected'] = '0'
        
        captcha_image = self._extract_captcha_image(soup)
        
        if not captcha_image:
            logger.error("No captcha image found")
            raise ValueError("No captcha image found")
        
        if captcha_image:
            try:
                logger.info("Solving captcha")
                code = await captcha_solver(self.session, captcha_image)
            except ErrorImageInvalid:
                logger.error("Error image invalid")
                if retry_no >= 3:
                    logger.error("Max retries reached for captcha")
                    raise ValueError("Max retries reached for captcha")
                return await self._free_method(anonfile_url, retry_no + 1)
            form_data_2['code'] = code
        logger.info("Waiting 17 seconds")
        await asyncio.sleep(17)
        direct_url = None
        async def send_form_data(url, data):
            second_headers = self._build_headers(current_url)
            async with self.session.post(
                url,
                data=data,
                headers=second_headers,
            ) as response:
                html_content = await response.text()
                soup = BeautifulSoup(html_content, 'html.parser')
            return soup
        
        
        while True:
            try:
                soup = await send_form_data(anonfile_url, form_data_2)
                direct_url, expires_hours = self._extract_direct_link(soup)
                if direct_url:
                    break
            except WrongCaptcha:
                if retry_no >= 3:
                    raise ValueError("Max retries reached for captcha")
                return await self.get_download_info(anonfile_url, retry_no + 1)
            except TimeoutSkipped:
                if retry_no >= 3:
                    raise ValueError("Max retries reached for captcha")
                await asyncio.sleep(retry_no)
                
        headers_info = {}
        async with self.session.head(direct_url) as response:
            headers_info = dict(response.headers)
            if 'Content-Length' in headers_info:
                filesize_bytes = int(headers_info['Content-Length'])
                file_info['filesize'] = filesize_bytes
    
        download_info = DownloadInfo(
            filename=file_info.get('filename'),
            size=file_info.get('filesize', filesize_bytes),
            download_url=direct_url,
            headers=headers_info,
        )
        return download_info
    
    async def _premium_method(self, anonfile_url: str) -> Dict[str, str]:
        # https://anonfile.de/FILEID or https://anonfile.de/FILEID/filename
        # Get file id (the part after the domain)
        parts = anonfile_url.rstrip("/").split("/")
        if len(parts) > 3:
            file_id = parts[3]
        elif len(parts) > 2:
            file_id = parts[2]
        else:
            file_id = None
        id = file_id
        data = {
            'op': 'download2',
            'id': id,
            'rand': '',
            'referer': '',
            'method_free': '',
            'method_premium': '1',
            'adblock_detected': '0',
        }
        cookies = {
            'login': os.getenv('ANONFILE_LOGIN_COOKIE'),
            'gdpr-cookie-consent': 'true',
            'lang': 'spanish',
            'xfss': os.getenv('ANONFILE_XFSS_COOKIE'),
        }
            
        async with self.session.post(anonfile_url, data=data, cookies=cookies) as response:
            response.raise_for_status()
            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')
            
        anchor = soup.find('a', class_='stretched-link')
        if not anchor:
            raise ValueError("Request failed, direct link not found")
        direct_url = anchor.get('href')
        headers_info = {}
        async with self.session.head(direct_url) as response:
            headers_info = dict(response.headers)
            if 'Content-Length' in headers_info:
                filesize_bytes = int(headers_info['Content-Length'])
    
        download_info = DownloadInfo(
            filename=urllib.parse.unquote(direct_url.split("/")[-1]),
            size=filesize_bytes,
            download_url=direct_url,
            headers={},
        )
        return download_info